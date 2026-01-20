import asyncio
from typing import Optional, List
from fastapi.responses import StreamingResponse
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, BackgroundTasks, Depends, Query
import shutil
import os
import uuid
import io
from database import get_db, engine, Base
from models import DocumentRegistry
from sqlalchemy.orm import Session
from services.ingestion_service import process_minio_document_background, ingestion_status_tracker
from celery.result import AsyncResult
from celery import Celery
# [CHANGE] Thư viện OpenAI
from openai import OpenAI 
from minio_client import minio_handler
from services.chapter1_agent import Chapter1Agent

# --- IMPORT CÁC SERVICES ĐÃ TẠO ---
from services.ai_pipeline.llama_service import llama_service
from services.requirement_service import RequirementService, get_req_service
from services.drafting_bot import DraftingBot, get_drafting_bot
from services.chroma_service import ChromaService, get_chroma_service
from services.retrieval_service import RetrievalService, get_retrieval_service

# [NEW] Import Visual Service (LitePali)
from services.visual_retrieval_service import VisualRetrievalService, get_visual_service

from fastapi.responses import HTMLResponse 
import markdown 
from services.construction_agent import ConstructionDraftingAgent # Import Agent
from pydantic import BaseModel
# --- IMPORT HÀM TIỆN ÍCH (CHUNKING) ---
from services.ai_pipeline.ingest import chunk_by_chapters 

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
celery_app = Celery('bidding_sender', broker=CELERY_BROKER_URL)

router = APIRouter(
    prefix="/ai-bidding",
    tags=["AI Bidding (RAG)"],
    responses={404: {"description": "Not found"}},
)

# --- BỘ NHỚ TẠM (Dùng RAM) ---
current_session_context = {} 

# Đảm bảo thư mục tạm tồn tại
TEMP_DIR = "temp_uploads"
os.makedirs(TEMP_DIR, exist_ok=True)

# ==============================================================================
# [MODIFIED] KHỞI TẠO OPENAI AGENT
# ==============================================================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

class OpenAIAgent:
    def __init__(self):
        if not OPENAI_API_KEY:
            print("⚠️ Cảnh báo: Chưa cấu hình OPENAI_API_KEY trong file .env")
        # [THÊM MỚI] Lấy base_url từ env
        base_url = os.getenv("OPENAI_API_BASE")

        self.client = OpenAI(api_key=OPENAI_API_KEY, base_url=base_url)
        # Sử dụng model gpt-4o (tốt nhất) hoặc gpt-4o-mini (tiết kiệm)
        self.model_name = "gpt-4o" 

    def chat(self, prompt: str, system_role: Optional[str] = None) -> str:
        try:
            messages = []
            
            # 1. System Prompt (Định hình tính cách bot)
            if system_role:
                messages.append({"role": "system", "content": system_role})
            else:
                default_system = """
                Bạn là một Chuyên gia Tư vấn Đấu thầu (Bidding Expert AI).
                Nhiệm vụ: Trả lời câu hỏi dựa trên văn bản pháp luật/hồ sơ được cung cấp.
                Phong cách: Chuyên nghiệp, chính xác, luôn trích dẫn nguồn (Điều khoản, Tên văn bản).
                """
                messages.append({"role": "system", "content": default_system})

            # 2. User Prompt
            messages.append({"role": "user", "content": prompt})

            # 3. Gọi API
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.1, # Giữ nhiệt độ thấp để bot trung thực với dữ liệu
                max_tokens=2000
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            return f"❌ Lỗi OpenAI: {str(e)}"
        

# Khởi tạo instance
openai_agent = OpenAIAgent()

# ==============================================================================
# 1. API: DẠY BOT (LEARN / INGESTION)
# ==============================================================================
@router.post("/learn-sample-document")
async def learn_document_async(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    service: RequirementService = Depends(get_req_service)
):
    """
    API nhận file và đẩy vào hàng đợi xử lý ngầm.
    """
    safe_filename = file.filename or "unknown_document.pdf"
    file_path = os.path.join(TEMP_DIR, f"bg_{uuid.uuid4()}_{safe_filename}")
    
    try:
        # 1. Lưu file xuống ổ cứng trước
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 2. Giao việc cho Service chạy ngầm
        background_tasks.add_task(
            service.process_large_document_background, 
            file_path, 
            safe_filename
        )
        # 3. Trả về kết quả ngay
        return {
            "status": "processing",
            "message": f"Đã tiếp nhận file {safe_filename}. Hệ thống đang xử lý ngầm.",
            "note": "Vui lòng đợi 10-15 phút. Check log server để xem tiến độ."
        }

    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Lỗi tiếp nhận file: {str(e)}")


# ==============================================================================
# 2. API: ĐỌC YÊU CẦU ĐẦU VÀO (INPUT REQUIREMENT)
# ==============================================================================
# 2. CẬP NHẬT API UPLOAD REQUIREMENT
@router.post("/upload-requirement", summary="Upload HSMT gán vào Dự Án cụ thể")
async def upload_requirement(
    file: UploadFile = File(...), 
    project_name: str = Form(..., description="Tên định danh dự án (VD: du_an_benh_vien_x)"), # <--- Thêm field này
    service: RequirementService = Depends(get_req_service)
):
    safe_filename = file.filename or "unknown_req.pdf"
    file_path = os.path.join(TEMP_DIR, f"req_{uuid.uuid4()}_{safe_filename}")
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Truyền project_name vào service
        requirement_text = service.process_requirement_file(file_path, safe_filename, project_name)
        
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
# 3. API: VIẾT BÀI (GENERATION)
# ==============================================================================
@router.post("/generate-section", summary="Viết bài và Xem ngay (HTML)")
async def generate_section_view(
    topic: str = Form(..., description="Chủ đề cần viết"),
    drafting_bot: DraftingBot = Depends(get_drafting_bot)
):
    try:
        # Gọi Bot viết bài (Lưu ý: Bạn cũng cần sửa file services/drafting_bot.py sang OpenAI nếu muốn đồng bộ hoàn toàn)
        generated_markdown = drafting_bot.draft_with_rag(topic)
        
        if generated_markdown is None:
            generated_markdown = "⚠️ Lỗi: Bot không trả về nội dung nào."

        html_content = markdown.markdown(generated_markdown)

        full_html = f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    max_width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f4f4f4;
                }}
                .paper {{
                    background: white;
                    padding: 40px;
                    box-shadow: 0 0 10px rgba(0,0,0,0.1);
                    border-radius: 8px;
                }}
                h1, h2, h3 {{ color: #2c3e50; }}
            </style>
        </head>
        <body>
            <div class="paper">
                {html_content}
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=full_html, status_code=200)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==============================================================================
# 4. API: KIỂM TRA TRẠNG THÁI (DEBUG)
# ==============================================================================
@router.get("/status", summary="Kiểm tra trạng thái ngữ cảnh hiện tại")
async def get_status():
    if "filename" in current_session_context:
        return {
            "status": "ready",
            "current_requirement_file": current_session_context["filename"],
            "data_length": len(current_session_context["content"])
        }
    else:
        return {
            "status": "empty",
            "message": "Chưa có file yêu cầu nào được nạp."
        }
        
@router.post("/reset-session", summary="Xóa sạch bộ nhớ để làm dự án mới")
async def reset_session(chroma_service: ChromaService = Depends(get_chroma_service)):
    try:
        chroma_service.clear_current_requirements()
        global current_session_context
        current_session_context = {}
        
        return {
            "status": "success",
            "message": "🧹 Đã dọn sạch bộ nhớ! Sẵn sàng cho dự án mới."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# ==============================================================================
# 5. API: UPLOAD FILE & XỬ LÝ NGẦM
# ==============================================================================
@router.post("/ingest-async", summary="Upload tài liệu kèm thông tin Metadata thủ công")
async def ingest_document_async(
    background_tasks: BackgroundTasks, 
    file: UploadFile = File(...),
    # [NEW] Thêm các trường nhập liệu thủ công
    legal_level: Optional[str] = Form(None, description="Cấp độ pháp lý (law, decree, circular...)"),
    promulgation_year: Optional[int] = Form(None, description="Năm ban hành"),
    collection_name: str = Form("legal_docs", description="Tên Collection lưu trữ Vector")
):
    safe_filename = file.filename or "unknown.pdf"
    minio_path = f"raw_inputs/{safe_filename}"
    task_id = str(uuid.uuid4())
    
    # Gom metadata thủ công vào dict
    manual_metadata = {
        "legal_level": legal_level,
        "promulgation_year": promulgation_year,
        "collection_name": collection_name
    }

    try:
        # BƯỚC 1: UPLOAD LÊN MINIO TỪ RAM
        file_content = await file.read()
        file_size = len(file_content)
        file_stream = io.BytesIO(file_content)
        
        minio_url = minio_handler.upload_file_obj(
            file_data=file_stream,
            length=file_size,
            object_name=minio_path,
            content_type=file.content_type or "application/octet-stream"
        )
        
        if not minio_url:
            raise HTTPException(status_code=500, detail="Lỗi upload MinIO")

        # BƯỚC 2: GIAO VIỆC CHO BACKGROUND TASKS
        # [CHANGE] Truyền thêm manual_metadata vào hàm xử lý
        background_tasks.add_task(
            process_minio_document_background, 
            task_id, 
            minio_path, 
            safe_filename,
            manual_metadata # <--- Truyền tham số mới
        )
                
        return {
            "status": "queued",
            "task_id": task_id,
            "minio_path": minio_path,
            "metadata_received": manual_metadata,
            "message": "File đang được xử lý ngầm với thông tin bạn cung cấp."
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi: {str(e)}")

@router.post("/ingest/template", summary="Upload file mẫu vào kho tri thức (bidding_docs)")
async def ingest_template_doc(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    # Không cần category/doc_type phức tạp nữa, chỉ cần file thôi
):
    """
    Dùng để upload các file mẫu BPTC, TCVN.
    Sẽ lưu vào collection 'bidding_docs'.
    """
    safe_filename = file.filename or "template.pdf"
    minio_path = f"templates/{safe_filename}" 
    task_id = str(uuid.uuid4())

    # Metadata đơn giản
    manual_metadata = {
        "collection_name": "bidding_docs", # CỐ ĐỊNH
        "is_template": True,
        "source": safe_filename # Dùng tên file làm nguồn tham chiếu
    }

    return await _handle_ingest(background_tasks, file, minio_path, task_id, manual_metadata)


# --- API 5.2: Upload Yêu Cầu HSMT (Vào current_requirements) ---
@router.post("/ingest/requirement", summary="Upload HSMT cho Dự án cụ thể")
async def ingest_requirement_doc(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    project_name: str = Form(..., description="Tên định danh dự án (VD: du_an_vinh_yen)"),
):
    """
    Dùng để upload HSMT. BẮT BUỘC phải có project_name để lọc.
    Sẽ lưu vào collection 'current_requirements'.
    """
    safe_filename = file.filename or "requirement.pdf"
    # Lưu MinIO theo folder dự án để dễ quản lý
    minio_path = f"projects/{project_name}/{safe_filename}" 
    task_id = str(uuid.uuid4())

    # Metadata quan trọng nhất là project_name
    manual_metadata = {
        "collection_name": "current_requirements", # CỐ ĐỊNH
        "project_name": project_name,              # ĐỂ LỌC
        "is_template": False,
        "source": safe_filename
    }

    return await _handle_ingest(background_tasks, file, minio_path, task_id, manual_metadata)


# --- Hàm xử lý chung (Helper để tránh lặp code) ---
async def _handle_ingest(background_tasks, file, minio_path, task_id, metadata):
    try:
        # Đọc file vào RAM
        file_content = await file.read()
        file_size = len(file_content)
        file_stream = io.BytesIO(file_content)
        
        # 1. Upload MinIO
        minio_url = minio_handler.upload_file_obj(
            file_data=file_stream,
            length=file_size,
            object_name=minio_path,
            content_type=file.content_type or "application/pdf"
        )
        
        if not minio_url:
            raise HTTPException(status_code=500, detail="Lỗi upload MinIO")

        # 2. Đẩy vào Background Task (Docling + LitePali)
        background_tasks.add_task(
            process_minio_document_background, 
            task_id, 
            minio_path, 
            file.filename, # Original Name
            metadata # Metadata đã được cấu hình chuẩn
        )
        
        return {
            "status": "queued",
            "task_id": task_id,
            "minio_path": minio_path,
            "metadata_received": metadata,
            "message": "Đang xử lý ngầm (Text + Visual)."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}", summary="Kiểm tra trạng thái xử lý file")
async def get_task_status(task_id: str):
    task_info = ingestion_status_tracker.get(task_id)
    
    if not task_info:
        return {
            "task_id": task_id,
            "status": "PENDING",
            "message": "Task đang chờ khởi động..."
        }
    
    return {
        "task_id": task_id,
        "status": task_info.get("status"), 
        "progress": {
            "message": task_info.get("message"),
        },
        "result": task_info.get("result")
    }

# ==============================================================================
# [MODIFIED] API SEARCH DÙNG OPENAI
# ==============================================================================
@router.post("/search")
async def search_knowledge(query: str, retrieval_service: RetrievalService = Depends(get_retrieval_service)):
    
    # 1. Tìm kiếm dữ liệu (Phần này nhanh, khoảng 1-3s)
    # filters = {"year": {"$gte": 2014}} 
    filters = None 
    
    results = retrieval_service.search_legal_docs(query, filters=filters)
    
    # Nếu không tìm thấy, trả về text bình thường (nhanh)
    if not results:
        return "Xin lỗi, tôi không tìm thấy văn bản nào trong cơ sở dữ liệu."

    # 2. Tạo Context String
    context_str = "\n\n".join([
        f"--- TÀI LIỆU: {r['source']} (Năm {r['year']}) ---\n{r['parent_content']}" 
        for r in results
    ])
    
    # 3. Tạo Prompt
    full_prompt = f"""
    Dưới đây là các văn bản pháp luật được trích xuất từ cơ sở dữ liệu:
    ---------------------
    {context_str}
    ---------------------

    CÂU HỎI: "{query}"

    YÊU CẦU:
    1. Trả lời trực tiếp vào câu hỏi, không vòng vo.
    2. BẮT BUỘC phải trích dẫn nguồn gốc (Theo Khoản..., Điều..., Văn bản nào?).
    3. Nếu các văn bản trên không chứa đủ thông tin để trả lời, hãy nói rõ: "Thông tin không có trong tài liệu được cung cấp".
    """
    
    # 4. [QUAN TRỌNG] Tạo hàm Generator để Stream dữ liệu
    async def response_generator():
        # Gọi trực tiếp client của openai_agent để dùng chế độ stream
        stream = openai_agent.client.chat.completions.create(
            model="gpt-4o", # Hoặc model bạn đang cấu hình
            messages=[
                {"role": "system", "content": "Bạn là trợ lý pháp lý chuyên nghiệp."},
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.1,
            stream=True  # <--- BẬT CHẾ ĐỘ STREAMING
        )

        # Lặp qua từng mảnh dữ liệu (chunk) được trả về
        for chunk in stream:
            if chunk.choices[0].delta.content:
                # Yield từng chữ ra socket ngay lập tức
                yield chunk.choices[0].delta.content

    # 5. Trả về StreamingResponse thay vì return string
    # media_type="text/event-stream" giúp Frontend hiểu đây là dòng dữ liệu
    return StreamingResponse(response_generator(), media_type="text/event-stream")

@router.get("/documents", summary="Lấy danh sách file (Từ SQL Database)")
async def get_documents_from_sql(db: Session = Depends(get_db)):
    """
    Lấy danh sách tài liệu đã ingest từ bảng SQL.
    """
    docs = db.query(DocumentRegistry).order_by(DocumentRegistry.created_at.desc()).all()
    
    return {
        "count": len(docs),
        "data": docs
    }
    
@router.delete("/documents/{filename}", summary="Xóa tài liệu (Cơ chế mềm - Không lỗi 404)")
async def delete_document(
    filename: str,
    collection_name: Optional[str] = Query(None, description="Tên collection cần xóa vector (VD: legal_docs, current_requirements)"),
    db: Session = Depends(get_db),
    chroma_service: ChromaService = Depends(get_chroma_service)
):
    """
    API xóa dữ liệu liên quan đến 1 file.
    Cơ chế: Nếu không tìm thấy ở SQL, vẫn tiếp tục thử xóa ở Chroma và MinIO.
    """
    deleted_status = {
        "sql": "Not Found (Skipped)",
        "chroma": "Processed",
        "minio": "Processed"
    }

    # 1. Kiểm tra file có trong SQL không
    doc_record = db.query(DocumentRegistry).filter(DocumentRegistry.source_file == filename).first()
    
    # [LOGIC MỚI] Xác định collection mục tiêu
    # Nếu doc_record tồn tại thì lấy từ DB, nếu không thì ưu tiên user nhập, cuối cùng fallback về 'legal_docs'
    target_collection = "legal_docs" # Default fallback
    
    if collection_name:
        target_collection = collection_name
    elif doc_record and hasattr(doc_record, "collection_name") and doc_record.collection_name:
        target_collection = doc_record.collection_name
        
    print(f"🎯 Xác định mục tiêu xóa: File '{filename}' trong Collection '{target_collection}'")

    try:
        # --- BƯỚC 1: XÓA SQL (NẾU CÓ) ---
        if doc_record:
            db.delete(doc_record)
            db.commit()
            print(f"✅ Đã xóa metadata trong SQL: {filename}")
            deleted_status["sql"] = "Deleted"
        else:
            print(f"ℹ️ Không tìm thấy '{filename}' trong SQL -> Bỏ qua bước SQL.")

        # --- BƯỚC 2: XÓA CHROMA VECTOR (LUÔN CHẠY) ---
        # Hàm này bên dưới service đã có try/except nên rất an toàn, cứ gọi là chạy
        chroma_service.delete_document_vectors(filename, collection_name=target_collection)

        # --- BƯỚC 3: XÓA FILE GỐC TRÊN MINIO (LUÔN CHẠY) ---
        minio_path = f"raw_inputs/{filename}"
        try:
            # minio_handler.delete_file(minio_path) 
            print(f"✅ (Giả lập) Đã xóa file gốc trên MinIO: {minio_path}")
            deleted_status["minio"] = "Deleted (Attempted)"
        except Exception as e:
            print(f"⚠️ Lỗi nhẹ khi xóa MinIO (có thể file không tồn tại): {e}")
            deleted_status["minio"] = f"Error: {str(e)}"

        return {
            "status": "success", 
            "message": f"Đã thực hiện quy trình xóa cho file: {filename}",
            "details": deleted_status,
            "target_collection": target_collection
        }

    except Exception as e:
        db.rollback()
        # Vẫn trả về lỗi 500 nếu là lỗi hệ thống nghiêm trọng (DB connection die, v.v.)
        raise HTTPException(status_code=500, detail=f"Lỗi hệ thống khi xóa tài liệu: {str(e)}")
    
@router.get("/collections", summary="Lấy danh sách Collection (Từ Chroma & SQL)")
async def get_all_collections(
    chroma_service: ChromaService = Depends(get_chroma_service),
    db: Session = Depends(get_db)
):
    """
    API này trả về 2 danh sách:
    1. active_in_chroma: Các collection thực tế đang có trong Vector DB.
    2. used_in_sql: Các collection được ghi nhận trong SQL (đang chứa file).
    """
    
    # 1. Lấy từ ChromaDB (Thực tế vật lý)
    chroma_cols = chroma_service.list_all_collections()
    
    # 2. Lấy từ SQL (Dữ liệu quản lý)
    # Query này tương đương: SELECT DISTINCT collection_name FROM document_registry
    sql_cols_query = db.query(DocumentRegistry.collection_name).distinct().all()
    # Kết quả trả về là list các tuple [('name1',), ('name2',)], cần flatten ra
    sql_cols = [row[0] for row in sql_cols_query if row[0]]

    return {
        "active_in_chroma": chroma_cols,
        "used_in_sql": sql_cols,
        "count_chroma": len(chroma_cols),
        "count_sql": len(sql_cols)
    }
    
# 1. API LIST FILES TRONG COLLECTION
@router.get("/collection/{collection_name}/files", summary="Lấy danh sách file trong 1 Collection")
async def list_collection_files(
    collection_name: str,
    chroma_service: ChromaService = Depends(get_chroma_service)
):
    """
    Trả về danh sách các tên file duy nhất đang có trong collection vector.
    """
    files = chroma_service.list_files_in_collection(collection_name)
    return {
        "collection": collection_name,
        "total_files": len(files),
        "files": files
    }
    

@router.post("/agent/generate-chapter-1", summary="Agent viết Chương 1 (Có chọn file mẫu)")
async def generate_chapter_1(
    project_name: str = Form(..., description="Tên đầy đủ của dự án/gói thầu"),
    reference_doc: Optional[str] = Form(None, description="Tên file mẫu trong bidding_docs (Chọn từ API list-template-docs)"),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
):
    try:
        # 1. Khởi tạo OpenAI Client
        openai_client = OpenAI() 
        
        # 2. Khởi tạo Agent
        agent = Chapter1Agent(retrieval_service, openai_client)
        
        # 3. Thực thi (Truyền reference_doc vào)
        print(f"🚀 Bắt đầu tạo Chương 1. Dự án: {project_name}. File mẫu: {reference_doc}")
        
        content = agent.write(project_name, reference_doc=reference_doc)
        
        return {
            "status": "success",
            "project": project_name,
            "used_template": reference_doc if reference_doc else "Auto (Best match)",
            "data": content
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi Agent: {str(e)}")
    
# Tìm đến đoạn class DraftingRequest và endpoint draft_full_proposal cũ, thay thế bằng đoạn này:

# [MODIFIED] Class Request mới hỗ trợ HITL
class DraftingRequest(BaseModel):
    project_name: str
    reference_file: Optional[str] = None
    thread_id: Optional[str] = None         # Nếu null -> Tạo mới. Nếu có -> Resume.
    approved_outline: Optional[List[dict]] = None # Nếu có -> User đã duyệt dàn ý này.

@router.post("/agent/draft-full-proposal")
async def draft_full_proposal(
    req: DraftingRequest,
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    # [FIX] Inject Visual Service để Agent có thể "nhìn"
    visual_service: VisualRetrievalService = Depends(get_visual_service)
):
    try:
        # 1. Tạo hoặc lấy thread_id
        thread_id = req.thread_id or str(uuid.uuid4())
        
        # 2. Khởi tạo Agent với cả 2 service (Text + Visual)
        agent = ConstructionDraftingAgent(retrieval_service, visual_service)
        
        # 3. Chạy Agent (Hàm run mới đã handle logic Start/Resume)
        result = agent.run(
            thread_id=thread_id,
            project_name=req.project_name,
            reference_doc=req.reference_file,
            user_feedback_outline=req.approved_outline
        )
        
        return {
            "success": True,
            "thread_id": thread_id,         # Frontend cần lưu cái này để gọi lần 2
            "status": result["status"],     # "paused" (hiện dàn ý) hoặc "completed" (hiện văn bản)
            "data_type": result["type"],    # "outline_review" hoặc "full_document"
            "content": result["content"]
        }
        
    except Exception as e:
        # In lỗi ra console server để dễ debug
        print(f"❌ Error in draft_full_proposal: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))