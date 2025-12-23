# services/ai_service.py
import os
import uuid
import logging
from urllib.parse import unquote, urlparse
from sqlalchemy.orm import Session
from sqlalchemy import text

# Import Models chuẩn từ file models.py của bạn
from models import (
    BiddingPackage,
    BiddingPackageFile,
    BiddingReqFinancialAdmin,
    BiddingReqPersonnel,
    BiddingReqEquipment
)
from minio_client import minio_handler, MINIO_BUCKET
from services.ai_pipeline.ingest import parse_pdf_to_markdown, chunk_by_chapters
from services.ai_pipeline.extract import prepare_context, extract_bid_info

# Setup logger
logger = logging.getLogger(__name__)

async def analyze_bidding_package(hsmt_id: int, db: Session):
    """
    Service phân tích gói thầu: 
    1. Tải PDF từ MinIO
    2. Gọi AI Ingest & Extract
    3. Lưu vào các bảng BiddingReq...
    """
    
    # 1. Lấy thông tin gói thầu (Dùng hsmt_id làm khóa chính)
    package = db.query(BiddingPackage).filter(BiddingPackage.hsmt_id == hsmt_id).first()
    if not package:
        raise ValueError(f"Không tìm thấy gói thầu với hsmt_id={hsmt_id}")

    # 2. Tìm file PDF trong bảng bidding_package_files
    # Lọc lấy file có đuôi .pdf
    file_record = db.query(BiddingPackageFile)\
        .filter(BiddingPackageFile.hsmt_id == hsmt_id)\
        .filter(BiddingPackageFile.file_path.like('%.pdf'))\
        .first()
    
    if not file_record:
        raise ValueError("Chưa có file PDF nào được upload cho gói thầu này")

    # 3. Xử lý đường dẫn MinIO để download
    # DB lưu: http://host:9000/bucket/path/file.pdf HOẶC path/file.pdf
    file_url = file_record.file_path
    object_name = ""
    
    if MINIO_BUCKET in file_url:
        try:
            # Cắt lấy phần sau tên bucket
            object_name = file_url.split(f"/{MINIO_BUCKET}/")[1]
        except IndexError:
            parsed = urlparse(file_url)
            object_name = parsed.path.lstrip('/')
            # Nếu path vẫn chứa bucket ở đầu thì cắt bỏ
            if object_name.startswith(f"{MINIO_BUCKET}/"):
                 object_name = object_name[len(MINIO_BUCKET)+1:]
    else:
        object_name = file_url

    object_name = unquote(object_name) # Decode ký tự đặc biệt (VD: %20 -> space)

    # Tạo thư mục tạm để chứa file download
    os.makedirs("temp_processing", exist_ok=True)
    temp_filename = f"temp_{uuid.uuid4()}.pdf"
    temp_path = os.path.join("temp_processing", temp_filename)
    
    try:
        print(f"⬇️ [AI Service] Đang tải file từ MinIO: {object_name}")
        success = minio_handler.download_file(object_name, temp_path)
        
        # Fallback: Nếu download thất bại, thử bỏ prefix bucket nếu có
        if not success and object_name.startswith(f"{MINIO_BUCKET}/"):
             retry_name = object_name[len(MINIO_BUCKET)+1:]
             print(f"⚠️ [AI Service] Thử tải lại với path: {retry_name}")
             if minio_handler.download_file(retry_name, temp_path):
                 success = True
        
        if not success:
            raise ValueError(f"Không thể tải file từ MinIO. Path: {object_name}")

        print(f"🚀 [AI Service] Bắt đầu xử lý file: {temp_path}")
        
        # 4. CHẠY PIPELINE AI
        # Bước A: Ingest (PDF -> Markdown -> Chunks)
        md_text = parse_pdf_to_markdown(temp_path)
        chunks = chunk_by_chapters(md_text)
        
        # Bước B: Extract (Chunks -> JSON Object)
        context_text = prepare_context(chunks)
        data = extract_bid_info(context_text)

        # 5. LƯU VÀO DATABASE
        # Xóa dữ liệu cũ của gói thầu này (nếu có) để tránh duplicate
        db.query(BiddingReqFinancialAdmin).filter(BiddingReqFinancialAdmin.hsmt_id == hsmt_id).delete()
        db.query(BiddingReqPersonnel).filter(BiddingReqPersonnel.hsmt_id == hsmt_id).delete()
        db.query(BiddingReqEquipment).filter(BiddingReqEquipment.hsmt_id == hsmt_id).delete()
        db.flush() 

        # --- Helper: Hàm clean tiền tệ ---
        def parse_money(val):
            if not val: return None
            if isinstance(val, (int, float)): return float(val)
            # Clean string: "94.000.000 VND" -> 94000000.0
            clean = str(val).replace('.', '').replace(',', '').replace(' VND', '').replace(' đ', '').strip()
            try:
                return float(clean)
            except:
                return 0.0

        # --- Lưu Tài chính & Thủ tục ---
        fin_data = data.section_2_admin
        fin_req = data.section_3_financial

        fin_record = BiddingReqFinancialAdmin(
            hsmt_id=hsmt_id,
            # Mapping từ Pydantic model sang SQLAlchemy model
            bid_security_value=parse_money(fin_data.bid_security_value),
            bid_validity_days=fin_data.bid_validity_days,
            submission_fee=parse_money(fin_data.submission_fee),
            contract_duration_text=fin_data.contract_duration, # Lưu text gốc (vd: 45 ngày)
            
            req_revenue_avg=parse_money(fin_req.avg_revenue),
            req_working_capital=parse_money(fin_req.working_capital),
            req_similar_contract_value=parse_money(fin_req.min_contract_value),
            req_similar_contract_desc=fin_req.similar_contract_desc
        )
        db.add(fin_record)

        # --- Lưu Nhân sự ---
        if data.section_4_personnel:
            for i, p in enumerate(data.section_4_personnel, 1):
                per_record = BiddingReqPersonnel(
                    hsmt_id=hsmt_id,
                    stt=i,
                    position_name=p.position,
                    quantity=p.quantity,
                    qualification_req=p.qualification,
                    min_exp_years=p.experience_years
                )
                db.add(per_record)

        # --- Lưu Thiết bị ---
        if data.section_5_equipment:
            for i, e in enumerate(data.section_5_equipment, 1):
                eq_record = BiddingReqEquipment(
                    hsmt_id=hsmt_id,
                    stt=i,
                    equipment_name=e.name,
                    quantity=e.quantity,
                    specifications=e.specs
                )
                db.add(eq_record)

        db.commit()
        print(f"✅ [AI Service] Đã lưu kết quả thành công cho gói thầu {hsmt_id}")
        
        # Trả về data raw để FE hiển thị ngay nếu cần
        return {"status": "success", "data": data.dict()}

    except Exception as e:
        db.rollback()
        print(f"❌ [AI Service] Lỗi: {e}")
        raise e
    finally:
        # 6. Cleanup: Xóa file tạm
        if os.path.exists(temp_path):
            os.remove(temp_path)
            print("🧹 [AI Service] Đã xóa file tạm.")