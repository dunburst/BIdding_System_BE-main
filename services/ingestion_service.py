import os
import traceback
from services.ai_pipeline.llama_service import llama_service
from services.ai_pipeline.ingest_advanced import process_hierarchical_chunks
from services.chroma_service import get_chroma_service
from minio_client import minio_handler
from typing import Optional
from sqlalchemy.orm import Session
from models import DocumentRegistry
from datetime import datetime
from database import SessionLocal

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
        
# [CHANGE] Thêm tham số collection_name vào hàm
def upsert_document_metadata(db: Session, metadata: dict, status="SUCCESS", total_chunks=0, collection_name="legal_docs"):
    """
    Lưu hoặc cập nhật thông tin file vào SQL.
    """
    source_file = metadata.get('source_file', 'unknown_file')
    
    # Tìm xem file đã tồn tại chưa
    db_doc = db.query(DocumentRegistry).filter(DocumentRegistry.source_file == source_file).first()

    save_target = None

    if db_doc:
        # UPDATE: Nếu có rồi thì cập nhật lại thông tin
        db_doc.legal_level = str(metadata.get('legal_level') or 'unknown')
        db_doc.legal_priority = int(metadata.get('legal_priority') or 0)
        db_doc.promulgation_year = int(metadata.get('promulgation_year') or 0)
        
        # [CHANGE] Cập nhật collection_name
        db_doc.collection_name = collection_name 
        
        db_doc.ingest_status = status
        db_doc.total_chunks = total_chunks
        db_doc.created_at = datetime.now() 
        
        save_target = db_doc
        print(f"🔄 Đã cập nhật SQL: {source_file}")
    else:
        # INSERT: Nếu chưa có thì tạo mới
        new_doc = DocumentRegistry(
            source_file=source_file,
            legal_level=str(metadata.get('legal_level') or 'unknown'),
            legal_priority=int(metadata.get('legal_priority') or 0),
            promulgation_year=int(metadata.get('promulgation_year') or 0),
            
            # [CHANGE] Thêm collection_name khi tạo mới
            collection_name=collection_name,
            
            ingest_status=status,
            total_chunks=total_chunks
        )
        db.add(new_doc)
        save_target = new_doc
        print(f"➕ Đã thêm mới vào SQL: {source_file}")

    # Commit và Refresh
    db.commit()
    db.refresh(save_target)
    return save_target

# [CHANGE] Thêm tham số manual_metadata vào định nghĩa hàm
def process_minio_document_background(
    task_id: str, 
    minio_object_name: str, 
    original_filename: str,
    manual_metadata: dict = {} # <--- Param mới
):
    """
    Logic xử lý chạy ngầm: Tải MinIO -> LlamaParse -> Chunking -> ChromaDB -> SQL.
    """
    print(f"🚀 Bắt đầu xử lý background task: {task_id}")
    collection_name = manual_metadata.get("collection_name", "legal_docs") # Lấy tên collection
    
    update_task_status(task_id, "PROGRESS", "Đang tải file từ MinIO...")
    
    local_path = f"temp_{task_id}_{original_filename}"
    
    try:
        # 1. Tải file từ MinIO
        minio_handler.download_file(minio_object_name, local_path)
        
        # 2. Parse PDF bằng LlamaParse
        update_task_status(task_id, "PROGRESS", "Đang đọc nội dung PDF (LlamaParse)...")
        markdown_text = llama_service.parse_pdf_to_markdown(local_path)
        
        if not markdown_text:
            raise ValueError("LlamaParse trả về nội dung rỗng.")

        # 3. Chunking & Extract Metadata
        update_task_status(task_id, "PROGRESS", "Đang chia nhỏ văn bản & Xử lý Meta...")
        
        # [CHANGE] Truyền manual_metadata vào hàm chunking để override thông tin tự động
        chunks, file_metadata = process_hierarchical_chunks(
            markdown_text, 
            original_filename,
            manual_metadata=manual_metadata # <--- Truyền vào đây
        )
        
        # 4. Save to Chroma (Vector DB)
        update_task_status(task_id, "PROGRESS", f"Đang lưu vào Vector DB ({collection_name})...")
        chroma = get_chroma_service()
        
        print(f"🧹 Đang dọn dẹp dữ liệu cũ của: {original_filename} trong {collection_name}")
        # [CHANGE] Truyền collection_name để xóa và lưu đúng chỗ
        chroma.delete_document_vectors(original_filename, collection_name=collection_name)
        chroma.save_hierarchical_chunks(chunks, original_filename, collection_name=collection_name)
        
        # 5. Save to SQL Database
        update_task_status(task_id, "PROGRESS", "Đang lưu metadata vào SQL...")
        
        db = SessionLocal()
        try:
            upsert_document_metadata(
                db=db, 
                metadata=file_metadata, # Metadata này đã được cập nhật thông tin thủ công ở bước 3
                status="SUCCESS", 
                total_chunks=len(chunks),
                collection_name=collection_name
            )
        except Exception as db_err:
            print(f"⚠️ Lỗi lưu SQL: {db_err}")
        finally:
            db.close()

        # 6. Hoàn thành
        result_msg = f"Đã xử lý xong {len(chunks)} đoạn vào collection '{collection_name}'."
        update_task_status(task_id, "SUCCESS", result_msg, {"chunks_count": len(chunks), "metadata": file_metadata})
        print(f"✅ Task {task_id} hoàn thành!")

    except Exception as e:
        error_msg = str(e)
        print(f"❌ Task {task_id} lỗi: {error_msg}")
        traceback.print_exc()
        
        # Cập nhật trạng thái lỗi vào SQL nếu có thể
        try:
            db_fail = SessionLocal()
            upsert_document_metadata(
                db=db_fail,
                metadata={"source_file": original_filename}, # Chỉ cần tên file để update status
                status="FAILED"
            )
            db_fail.close()
        except:
            pass

        update_task_status(task_id, "FAILURE", f"Lỗi: {error_msg}")
        
    finally:
        # Dọn dẹp file tạm
        if os.path.exists(local_path):
            os.remove(local_path)