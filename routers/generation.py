from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
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

# --- IMPORT CÁC SERVICES ĐÃ TẠO ---
from services.ai_pipeline.llama_service import llama_service
from services.requirement_service import RequirementService, get_req_service
from services.drafting_bot import DraftingBot, get_drafting_bot
from services.chroma_service import ChromaService, get_chroma_service
from services.retrieval_service import RetrievalService, get_retrieval_service
from fastapi.responses import HTMLResponse 
import markdown 

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
@router.post("/upload-requirement", summary="Upload HSMT để lấy dữ liệu đầu vào")
async def upload_requirement(file: UploadFile = File(...), service: RequirementService = Depends(get_req_service)):
    
    safe_filename = file.filename or "unknown_requirement.pdf"
    file_path = os.path.join(TEMP_DIR, f"req_{uuid.uuid4()}_{safe_filename}")
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        print(f"📖 Đang đọc yêu cầu từ: {safe_filename}")

        requirement_text = service.process_requirement_file(file_path, safe_filename)
        
        return {
            "status": "success",
            "message": "Đã đọc và lưu yêu cầu thành công!",
            "file_name": safe_filename,
            "content_preview": requirement_text[:200] + "..." 
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi: {str(e)}")
    
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
    
@router.delete("/documents/{filename}", summary="Xóa tài liệu (SQL + Vector + MinIO)")
async def delete_document(
    filename: str,
    db: Session = Depends(get_db),
    chroma_service: ChromaService = Depends(get_chroma_service)
):
    """
    API xóa toàn bộ dữ liệu liên quan đến 1 file:
    1. Xóa trong SQL Database (DocumentRegistry).
    2. Xóa Vectors trong ChromaDB.
    3. (Option) Xóa file gốc trên MinIO.
    """
    
    # 1. Kiểm tra file có trong SQL không
    doc_record = db.query(DocumentRegistry).filter(DocumentRegistry.source_file == filename).first()
    
    if not doc_record:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy file '{filename}' trong hệ thống.")

    try:
        # --- BƯỚC 1: XÓA SQL ---
        db.delete(doc_record)
        db.commit()
        print(f"✅ Đã xóa metadata trong SQL: {filename}")

        # --- BƯỚC 2: XÓA CHROMA VECTOR ---
        # Gọi hàm vừa viết ở Bước 1
        chroma_service.delete_document_vectors(filename)

        # --- BƯỚC 3: XÓA FILE GỐC TRÊN MINIO (Khuyên dùng) ---
        # Đường dẫn MinIO lưu lúc upload là "raw_inputs/{filename}"
        minio_path = f"raw_inputs/{filename}"
        try:
            minio_handler.delete_file(minio_path) # Giả sử minio_handler có hàm delete_file hoặc remove_object
            # Nếu dùng thư viện minio gốc: minio_handler.client.remove_object("bucket_name", minio_path)
            print(f"✅ Đã xóa file gốc trên MinIO: {minio_path}")
        except Exception as e:
            print(f"⚠️ Không xóa được file trên MinIO (có thể file không tồn tại): {e}")

        return {
            "status": "success", 
            "message": f"Đã xóa hoàn toàn tài liệu: {filename}",
            "deleted_layers": ["SQL Metadata", "Chroma Vectors", "MinIO File"]
        }

    except Exception as e:
        db.rollback() # Hoàn tác nếu lỗi SQL
        raise HTTPException(status_code=500, detail=f"Lỗi khi xóa tài liệu: {str(e)}")
    
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