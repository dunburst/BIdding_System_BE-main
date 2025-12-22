# services/ai_service.py
import os
import uuid
from sqlalchemy.orm import Session
from urllib.parse import unquote, urlparse

# Import modules nội bộ
from models import BiddingPackage, BiddingPackageFile, BiddingReqFinancialAdmin, BiddingReqPersonnel, BiddingHealthCheckResult
from minio_client import minio_handler, MINIO_BUCKET
from services.ai_pipeline.ingest import parse_pdf_to_markdown, chunk_by_chapters
from services.ai_pipeline.extract import prepare_context, extract_bid_info

async def analyze_bidding_package(hsmt_id: int, db: Session):
    # 1. Lấy thông tin file từ DB
    package = db.query(BiddingPackage).filter(BiddingPackage.id == hsmt_id).first()
    if not package:
        raise ValueError("Không tìm thấy gói thầu")

    file_record = db.query(BiddingPackageFile)\
        .filter(BiddingPackageFile.hsmt_id == hsmt_id)\
        .filter(BiddingPackageFile.file_path.like('%.pdf'))\
        .first()
    
    if not file_record:
        raise ValueError("Không tìm thấy file PDF")

    # 2. Download file từ MinIO về thư mục tạm
    # Xử lý URL để lấy object_name
    file_url = file_record.file_path
    if MINIO_BUCKET in file_url:
        object_name = file_url.split(f"/{MINIO_BUCKET}/")[1]
    else:
        object_name = urlparse(file_url).path.lstrip('/')
    object_name = unquote(object_name)

    temp_path = f"temp_{uuid.uuid4()}.pdf"
    
    try:
        print(f"⬇️ Downloading: {object_name}")
        if not minio_handler.download_file(object_name, temp_path):
             raise ValueError("Lỗi tải file từ MinIO")

        # 3. CHẠY PIPELINE AI
        # Bước A: Ingest (PDF -> Markdown -> Chunks)
        md_text = parse_pdf_to_markdown(temp_path)
        chunks = chunk_by_chapters(md_text)
        
        # Bước B: Extract (Chunks -> JSON Object)
        context_text = prepare_context(chunks)
        data = extract_bid_info(context_text)

        # 4. LƯU DATABASE (SQLAlchemy)
        # (Map data từ object `data` vào các model `BiddingReq...` như đã hướng dẫn trước đó)
        # Ví dụ:
        # admin_req = BiddingReqFinancialAdmin(hsmt_id=package.id, ...)
        # db.add(admin_req)
        # ...
        
        # db.commit()
        
        return {"status": "success", "data": data.dict()}

    except Exception as e:
        print(f"❌ AI Error: {e}")
        raise e
    finally:
        # 5. Cleanup
        if os.path.exists(temp_path):
            os.remove(temp_path)