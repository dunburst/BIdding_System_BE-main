import uuid
import io
import logging
import os
import shutil
import markdown # <--- Cần cài: pip install markdown
from typing import Optional, List, Dict, Any

from fastapi import UploadFile, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session

# --- INTERNAL LIBS ---
from app.infrastructure.storage.minio_client import minio_handler
from app.modules.drafting.model import DocumentRegistry
from app.modules.ai_bidding.schema import DraftingRequest

# --- AI SERVICES ---
from app.integrations.ai.provider.openai_service import openai_service
from app.integrations.ai.data_processing.ingestion_service import process_minio_document_background, ingestion_status_tracker
from app.integrations.ai.data_processing.chroma_service import ChromaService
from app.integrations.ai.data_processing.retrieval_service import RetrievalService
from app.integrations.ai.data_processing.visual_retrieval_service import VisualRetrievalService
from app.integrations.ai.data_processing.requirement_service import RequirementService

# --- AGENTS ---
from app.integrations.ai.agent.chapter1 import Chapter1Agent
from app.integrations.ai.agent.construction import ConstructionDraftingAgent
from app.integrations.ai.agent.bid_preparation import DraftingBot

logger = logging.getLogger(__name__)

# [RESTORE] Biến toàn cục lưu session tạm (cho API upload-requirement cũ)
PROJECT_ROOT = os.getcwd()
TEMP_DIR = os.path.join(
    PROJECT_ROOT, 
    "app", "infrastructure", "temp_storage", "temp_uploads"
)

# [RESTORE] Biến toàn cục lưu session tạm
current_session_context = {}

# 3. Tạo thư mục (bao gồm cả các thư mục cha nếu chưa có)
os.makedirs(TEMP_DIR, exist_ok=True)
# current_session_context = {}
# TEMP_DIR = "temp_uploads"
# os.makedirs(TEMP_DIR, exist_ok=True)

# ==============================================================================
# 1. LOGIC INGESTION (Cũ & Mới)
# ==============================================================================
async def ingest_file_logic(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    minio_folder: str,
    metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """Hàm xử lý upload MinIO chuẩn (Dùng cho cả learn-sample-document mới)"""
    safe_filename = file.filename or f"unknown_{uuid.uuid4()}.pdf"
    minio_path = f"{minio_folder}/{safe_filename}"
    task_id = str(uuid.uuid4())

    try:
        file_content = await file.read()
        file_stream = io.BytesIO(file_content)
        
        minio_url = minio_handler.upload_file_obj(
            file_data=file_stream,
            length=len(file_content),
            object_name=minio_path,
            content_type=file.content_type or "application/pdf"
        )
        
        if not minio_url:
            raise Exception("Thất bại khi upload lên MinIO")

        background_tasks.add_task(
            process_minio_document_background, 
            task_id, minio_path, safe_filename, metadata
        )
        
        return {
            "status": "queued",
            "task_id": task_id,
            "minio_path": minio_path,
            "message": "File đã được tiếp nhận và đang xử lý ngầm."
        }
    except Exception as e:
        logger.error(f"Ingestion Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý file: {str(e)}")

# [RESTORE] Logic xử lý upload requirement (Lưu local tạm rồi process ngay)
def process_requirement_sync_logic(
    file: UploadFile,
    project_name: str,
    service: RequirementService
):
    safe_filename = file.filename or "unknown_req.pdf"
    file_path = os.path.join(TEMP_DIR, f"req_{uuid.uuid4()}_{safe_filename}")
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Gọi service xử lý đồng bộ (đọc text ngay)
        requirement_text = service.process_requirement_file(file_path, safe_filename, project_name)
        
        # Cập nhật context toàn cục
        global current_session_context
        current_session_context["filename"] = safe_filename
        current_session_context["content"] = requirement_text
        
        return {
            "status": "success",
            "message": f"Đã thêm tài liệu vào dự án '{project_name}'",
            "project": project_name,
            "file": safe_filename
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

# ==============================================================================
# 2. LOGIC GENERATION (HTML & Agent)
# ==============================================================================
# [RESTORE] Logic tạo HTML đơn giản
def generate_simple_html_logic(topic: str, drafting_bot: DraftingBot) -> str:
    generated_markdown = drafting_bot.draft_with_rag(topic)
    
    if generated_markdown is None:
        generated_markdown = "⚠️ Lỗi: Bot không trả về nội dung nào."

    html_content = markdown.markdown(generated_markdown)
    
    # Wrap HTML cho đẹp
    full_html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; max_width: 800px; margin: 0 auto; padding: 20px; background-color: #f4f4f4; }}
            .paper {{ background: white; padding: 40px; box-shadow: 0 0 10px rgba(0,0,0,0.1); border-radius: 8px; }}
            h1, h2, h3 {{ color: #2c3e50; }}
        </style>
    </head>
    <body>
        <div class="paper">{html_content}</div>
    </body>
    </html>
    """
    return full_html

# Logic Search Streaming (Đã có)
async def generate_search_stream(query: str, retrieval_service: RetrievalService):
    results = retrieval_service.search_legal_docs(query)
    if not results:
        yield "Không tìm thấy thông tin."
        return

    context_str = "\n\n".join([f"Source: {r['source']}\n{r['parent_content']}" for r in results])
    full_prompt = f"Context:\n{context_str}\n\nQuestion: {query}"

    stream = openai_service.client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": full_prompt}],
        temperature=0.1,
        stream=True
    )
    for chunk in stream:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content

# Logic Agent (Đã có)
def run_drafting_agent_logic(req: DraftingRequest, retrieval_service: RetrievalService, visual_service: VisualRetrievalService):
    thread_id = req.thread_id or str(uuid.uuid4())
    agent = ConstructionDraftingAgent(retrieval_service, visual_service)
    result = agent.run(thread_id, req.project_name, req.reference_file, req.approved_outline or [])
    return {"success": True, "thread_id": thread_id, "status": result["status"], "content": result["content"], "data_type": result["type"]}

# ==============================================================================
# 3. UTILS & STATUS
# ==============================================================================
# [RESTORE] Logic get status task
def get_task_status_logic(task_id: str):
    task_info = ingestion_status_tracker.get(task_id)
    if not task_info:
        return {"task_id": task_id, "status": "PENDING", "message": "Task not found or pending"}
    return {"task_id": task_id, "status": task_info.get("status"), "result": task_info.get("result")}

# [RESTORE] Logic Session Status
def get_session_status_logic():
    if "filename" in current_session_context:
        return {"status": "ready", "current_file": current_session_context["filename"]}
    return {"status": "empty", "message": "No file loaded"}

# [RESTORE] Logic Reset Session
def reset_session_logic(chroma_service: ChromaService):
    chroma_service.clear_current_requirements()
    global current_session_context
    current_session_context = {}
    return {"status": "success", "message": "Memory cleared."}

# [RESTORE] Logic Delete Document
def delete_document_logic(filename: str, collection_name: Optional[str], db: Session, chroma_service: ChromaService):
    doc_record = db.query(DocumentRegistry).filter(DocumentRegistry.source_file == filename).first()
    target_collection = collection_name or (doc_record.collection_name if doc_record else "legal_docs")
    
    if doc_record:
        db.delete(doc_record)
        db.commit()
    
    chroma_service.delete_document_vectors(filename, collection_name=target_collection)
    return {"status": "success", "deleted": filename, "collection": target_collection}