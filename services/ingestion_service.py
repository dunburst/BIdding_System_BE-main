import os
import traceback
from services.ai_pipeline.llama_service import llama_service
from services.ai_pipeline.ingest_advanced import process_hierarchical_chunks
from services.chroma_service import get_chroma_service
from minio_client import minio_handler
from typing import Optional

# Biến toàn cục lưu trạng thái task (Thay thế Redis Backend của Celery)
# Format: { "task_id": { "status": "PROCESSING", "message": "...", "result": ... } }
ingestion_status_tracker = {}

def update_task_status(task_id: str, status: str, message: Optional[str] = None, result:Optional[dict] = None):
    """Hàm cập nhật trạng thái task vào RAM"""
    if task_id not in ingestion_status_tracker:
        ingestion_status_tracker[task_id] = {}
    
    ingestion_status_tracker[task_id]["status"] = status
    if message:
        ingestion_status_tracker[task_id]["message"] = message
    if result:
        ingestion_status_tracker[task_id]["result"] = result

def process_minio_document_background(task_id: str, minio_object_name: str, original_filename: str):
    """
    Logic xử lý chạy ngầm (thay thế process_document_task của Celery).
    """
    print(f"🚀 Bắt đầu xử lý background task: {task_id}")
    update_task_status(task_id, "PROGRESS", "Đang tải file từ MinIO...")
    
    local_path = f"temp_{task_id}_{original_filename}"
    
    try:
        # 1. Tải file từ MinIO
        minio_handler.download_file(minio_object_name, local_path)
        
        # 2. Parse PDF bằng Llama
        update_task_status(task_id, "PROGRESS", "Đang đọc nội dung PDF (LlamaParse)...")
        markdown_text = llama_service.parse_pdf_to_markdown(local_path)
        
        if not markdown_text:
            raise ValueError("LlamaParse trả về nội dung rỗng.")

        # 3. Chunking (Hierarchical)
        update_task_status(task_id, "PROGRESS", "Đang chia nhỏ văn bản (Chunking)...")
        chunks = process_hierarchical_chunks(markdown_text, original_filename)
        
        # 4. Save to Chroma
        update_task_status(task_id, "PROGRESS", "Đang lưu vào Vector DB...")
        chroma = get_chroma_service()
        chroma.save_hierarchical_chunks(chunks, original_filename)
        
        # 5. Hoàn thành
        result_msg = f"Đã xử lý xong {len(chunks)} đoạn văn bản."
        update_task_status(task_id, "SUCCESS", result_msg, {"chunks_count": len(chunks)})
        print(f"✅ Task {task_id} hoàn thành!")

    except Exception as e:
        error_msg = str(e)
        print(f"❌ Task {task_id} lỗi: {error_msg}")
        traceback.print_exc()
        update_task_status(task_id, "FAILURE", f"Lỗi: {error_msg}")
        
    finally:
        # Dọn dẹp file tạm
        if os.path.exists(local_path):
            os.remove(local_path)