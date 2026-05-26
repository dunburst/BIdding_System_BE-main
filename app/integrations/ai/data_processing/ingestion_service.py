import os
import traceback
import uuid
from typing import Optional
from sqlalchemy.orm import Session
from datetime import datetime

# Import Database Models
from app.infrastructure.database.database import SessionLocal
from app.modules.drafting.model import DocumentRegistry

# Import MinIO
from app.infrastructure.storage.minio_client import minio_handler

# [NEW] Import Services mới
from app.integrations.ai.provider.docling_service import get_docling_service
from app.integrations.ai.data_processing.visual_retrieval_service import get_visual_service
from app.integrations.ai.data_processing.chroma_service import get_chroma_service

# Biến toàn cục lưu trạng thái task (Thay thế Redis Backend của Celery)
ingestion_status_tracker = {}

def update_task_status(task_id: str, status: str, message: Optional[str] = None, result: Optional[dict] = None):
    """Hàm cập nhật trạng thái task vào RAM"""
    if task_id not in ingestion_status_tracker:
        ingestion_status_tracker[task_id] = {}
    
    ingestion_status_tracker[task_id]["status"] = status
    if message:
        ingestion_status_tracker[task_id]["message"] = message
    if result:
        ingestion_status_tracker[task_id]["result"] = result

def upsert_document_metadata(db: Session, metadata: dict, status="SUCCESS", total_chunks=0, collection_name="legal_docs"):
    """
    Lưu hoặc cập nhật thông tin file vào SQL.
    """
    source_file = metadata.get('source_file', 'unknown_file')
    
    # Tìm xem file đã tồn tại chưa
    db_doc = db.query(DocumentRegistry).filter(DocumentRegistry.source_file == source_file).first()

    save_target = None

    if db_doc:
        # UPDATE
        db_doc.legal_level = str(metadata.get('legal_level') or 'unknown')
        db_doc.legal_priority = int(metadata.get('legal_priority') or 0)
        db_doc.promulgation_year = int(metadata.get('promulgation_year') or 0)
        db_doc.collection_name = collection_name 
        db_doc.ingest_status = status
        db_doc.total_chunks = total_chunks
        db_doc.created_at = datetime.now() 
        save_target = db_doc
        print(f"🔄 Đã cập nhật SQL: {source_file}")
    else:
        # INSERT
        new_doc = DocumentRegistry(
            source_file=source_file,
            legal_level=str(metadata.get('legal_level') or 'unknown'),
            legal_priority=int(metadata.get('legal_priority') or 0),
            promulgation_year=int(metadata.get('promulgation_year') or 0),
            collection_name=collection_name,
            ingest_status=status,
            total_chunks=total_chunks
        )
        db.add(new_doc)
        save_target = new_doc
        print(f"➕ Đã thêm mới vào SQL: {source_file}")

    db.commit()
    db.refresh(save_target)
    return save_target

def process_minio_document_background(
    task_id: str, 
    minio_object_name: str, 
    original_filename: str,
    manual_metadata: dict = {} 
):
    """
    Logic xử lý chạy ngầm MỚI: 
    MinIO -> Docling (Text/Markdown) -> ChromaDB
          -> LitePali (Visual/Image) -> Visual Index
          -> SQL Metadata
    """
    print(f"🚀 Bắt đầu xử lý background task: {task_id}")
    
    # Lấy các service instance
    docling_service = get_docling_service()
    visual_service = get_visual_service()
    chroma_service = get_chroma_service()

    collection_name = manual_metadata.get("collection_name", "legal_docs")
    local_path = f"temp_{task_id}_{original_filename}"
    
    try:
        # 1. Tải file từ MinIO
        update_task_status(task_id, "PROGRESS", "Đang tải file từ MinIO...")
        minio_handler.download_file(minio_object_name, local_path)
        
        # --- LUỒNG 1: XỬ LÝ TEXT VỚI DOCLING ---
        update_task_status(task_id, "PROGRESS", "Đang xử lý cấu trúc văn bản (Docling)...")
        
        # Convert PDF -> Markdown
        markdown_text = docling_service.process_pdf_to_markdown(local_path)
        if not markdown_text:
            raise ValueError("Docling không thể trích xuất nội dung văn bản.")

        # Chunking thông minh theo Header
        chunks = docling_service.chunk_markdown(markdown_text)
        
        # Chuẩn bị dữ liệu cho Chroma
        texts = []
        metadatas = []
        ids = []
        
        # Merge metadata thủ công vào từng chunk
        base_metadata = manual_metadata.copy()
        base_metadata.update({
            "source": original_filename,
            "source_file": original_filename, # Để khớp với hàm SQL upsert
            "processed_by": "docling"
        })

        for i, chunk in enumerate(chunks):
            texts.append(chunk.page_content)
            # Kết hợp metadata từ Docling (header path) và metadata thủ công
            meta = chunk.metadata.copy() 
            meta.update(base_metadata)
            metadatas.append(meta)
            ids.append(f"{task_id}_{i}")

        # Lưu vào ChromaDB
        update_task_status(task_id, "PROGRESS", f"Đang lưu {len(texts)} chunks vào Vector DB...")
        
        # Xóa dữ liệu cũ nếu có
        chroma_service.delete_document_vectors(original_filename, collection_name=collection_name)
        
        # Lưu mới
        chroma_service.add_documents(
            collection_name=collection_name,
            documents=texts,
            metadatas=metadatas,
            ids=ids
        )

        # --- LUỒNG 2: XỬ LÝ HÌNH ẢNH VỚI LITEPALI ---
        update_task_status(task_id, "PROGRESS", "Đang xử lý hình ảnh/bản vẽ (LitePali)...")
        try:
            # Tạo doc_id an toàn từ filename
            doc_id = original_filename.replace(".", "_").replace(" ", "_")
            
            # [QUAN TRỌNG] Truyền Metadata vào Visual Service luôn
            visual_service.ingest_images_from_pdf(local_path, doc_id, metadata=base_metadata)
            
        except Exception as visual_error:
            print(f"⚠️ Cảnh báo Visual Ingest: {visual_error}")
            # Không raise lỗi chết chương trình, chỉ log warning vì Text quan trọng hơn

        # --- LUỒNG 3: LƯU METADATA VÀO SQL ---
        update_task_status(task_id, "PROGRESS", "Đang lưu metadata vào SQL...")
        
        db = SessionLocal()
        try:
            upsert_document_metadata(
                db=db, 
                metadata=base_metadata, 
                status="SUCCESS", 
                total_chunks=len(texts),
                collection_name=collection_name
            )
        except Exception as db_err:
            print(f"⚠️ Lỗi lưu SQL: {db_err}")
        finally:
            db.close()

        # 6. Hoàn thành
        result_msg = f"Đã xử lý xong. Text: {len(texts)} chunks. Visual: LitePali Indexed."
        update_task_status(task_id, "SUCCESS", result_msg, {"chunks_count": len(texts), "metadata": base_metadata})
        print(f"✅ Task {task_id} hoàn thành!")

    except Exception as e:
        error_msg = str(e)
        print(f"❌ Task {task_id} lỗi: {error_msg}")
        traceback.print_exc()
        
        # Cập nhật trạng thái lỗi vào SQL
        try:
            db_fail = SessionLocal()
            upsert_document_metadata(
                db=db_fail,
                metadata={"source_file": original_filename},
                status="FAILED"
            )
            db_fail.close()
        except:
            pass

        update_task_status(task_id, "FAILURE", f"Lỗi: {error_msg}")
        
    finally:
        # Dọn dẹp file tạm
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except:
                pass