from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, BackgroundTasks
import shutil
import os
import uuid

# --- IMPORT CÁC SERVICES ĐÃ TẠO ---
from services.ai_pipeline.llama_service import llama_service
from services.chroma_service import chroma_service
from services.drafting_bot import drafting_bot
from services.requirement_service import req_service # Nếu bạn đã tách service này, nếu chưa thì dùng llama_service trực tiếp
from fastapi.responses import HTMLResponse # <--- Import cái này
import markdown # <--- Import thư viện chuyển đổi
# --- IMPORT HÀM TIỆN ÍCH (CHUNKING) ---
# Giả sử bạn để hàm chunk_by_chapters trong utils/chunking.py
# Nếu chưa có file này, bạn có thể copy hàm chunk_by_chapters vào cuối file này cũng được
from services.ai_pipeline.ingest import chunk_by_chapters 

router = APIRouter(
    prefix="/ai-bidding",
    tags=["AI Bidding (RAG)"],
    responses={404: {"description": "Not found"}},
)

# --- BỘ NHỚ TẠM (Dùng RAM) ---
# Lưu ý: Khi restart server dữ liệu này sẽ mất. 
# Trong thực tế nên dùng Redis hoặc Database để lưu theo UserID/SessionID.
current_session_context = {} 

# Đảm bảo thư mục tạm tồn tại
TEMP_DIR = "temp_uploads"
os.makedirs(TEMP_DIR, exist_ok=True)

# --- HÀM XỬ LÝ NGẦM (WORKER) ---
def process_large_document_background(file_path: str, original_filename: str):
    """
    Hàm này sẽ chạy ngầm, không bắt người dùng phải đợi.
    """
    try:
        print(f"🚀 [Background] Bắt đầu xử lý file lớn: {original_filename}...")
        
        # 1. Gọi LlamaParse (Bước này lâu nhất - tốn 5-15 phút cho 400 trang)
        markdown_text = llama_service.parse_pdf_to_markdown(file_path)
        
        if not markdown_text:
            print(f"❌ [Background] Lỗi: Không đọc được nội dung file {original_filename}")
            return

        # 2. Cắt nhỏ (Chunking)
        chunks = chunk_by_chapters(markdown_text)
        print(f"✂️ [Background] Đã cắt thành {len(chunks)} chương.")

        # 3. Lưu vào DB
        chroma_service.save_chunks_to_db(chunks, source_filename=original_filename)
        
        print(f"✅ [Background] Hoàn tất xử lý file {original_filename}!")

    except Exception as e:
        print(f"❌ [Background] Lỗi nghiêm trọng: {str(e)}")
    
    finally:
        # Dọn dẹp file tạm dù thành công hay thất bại
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"🧹 Đã xóa file tạm: {file_path}")

# ==============================================================================
# 1. API: DẠY BOT (LEARN / INGESTION)
# ==============================================================================
# --- API ENDPOINT ---
@router.post("/learn-sample-document")
async def learn_document_async(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """
    API nhận file và đẩy vào hàng đợi xử lý ngầm.
    """
    # Tạo tên file duy nhất
    # [FIX] Đảm bảo filename luôn là chuỗi string
    safe_filename = file.filename or "unknown_document.pdf"
    
    file_path = os.path.join(TEMP_DIR, f"bg_{uuid.uuid4()}_{safe_filename}")
    
    try:
        # 1. Lưu file xuống ổ cứng trước
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 2. Giao việc cho Background Task
        # [FIX] Truyền safe_filename thay vì file.filename
        background_tasks.add_task(process_large_document_background, file_path, safe_filename)
        
        # 3. Trả về kết quả ngay
        return {
            "status": "processing",
            "message": f"Đã tiếp nhận file {safe_filename} (400 trang). Hệ thống đang xử lý ngầm.",
            "note": "Vui lòng đợi khoảng 10-15 phút. Check log server để xem tiến độ."
        }

    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Lỗi tiếp nhận file: {str(e)}")


# ==============================================================================
# 2. API: ĐỌC YÊU CẦU ĐẦU VÀO (INPUT REQUIREMENT)
# ==============================================================================
@router.post("/upload-requirement", summary="Upload HSMT để lấy dữ liệu đầu vào")
async def upload_requirement(file: UploadFile = File(...)):
    
    # [FIX 3] Xử lý trường hợp filename bị None
    safe_filename = file.filename or "unknown_requirement.pdf"
    
    file_path = os.path.join(TEMP_DIR, f"req_{uuid.uuid4()}_{safe_filename}")
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        print(f"📖 Đang đọc yêu cầu từ: {safe_filename}")

        # Truyền safe_filename (chắc chắn là str) vào hàm
        requirement_text = req_service.process_requirement_file(file_path, safe_filename)
        
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
):

    try:
        # 2. Gọi Bot viết bài (như cũ)
        generated_markdown = drafting_bot.draft_with_rag(topic)
        
        # [FIX LỖI] Nếu bot trả về None, thay thế bằng chuỗi rỗng "" hoặc thông báo lỗi
        if generated_markdown is None:
            generated_markdown = "⚠️ Lỗi: Bot không trả về nội dung nào."

        # 3. Chuyển Markdown sang HTML
        # Bây giờ generated_markdown chắc chắn là str
        html_content = markdown.markdown(generated_markdown)

        # 4. Trang trí thêm chút CSS cho đẹp (giống trang A4)
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
        
        # 5. Trả về HTMLResponse
        return HTMLResponse(content=full_html, status_code=200)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==============================================================================
# 4. API: KIỂM TRA TRẠNG THÁI (DEBUG)
# ==============================================================================
@router.get("/status", summary="Kiểm tra trạng thái ngữ cảnh hiện tại")
async def get_status():
    """Kiểm tra xem Bot đang nhớ file yêu cầu nào"""
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
async def reset_session():
    """
    Gọi API này khi bạn muốn Bot quên hết các file cũ đi để bắt đầu nạp file cho dự án thầu MỚI.
    """
    try:
        chroma_service.clear_current_requirements()
        # Reset cả bộ nhớ tạm trên RAM nếu cần
        global current_session_context
        current_session_context = {}
        
        return {
            "status": "success",
            "message": "🧹 Đã dọn sạch bộ nhớ! Sẵn sàng cho dự án mới."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))