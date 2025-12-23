# services/ai_service.py
import os
import uuid
import logging
import re
from sqlalchemy.orm import Session
from urllib.parse import unquote, urlparse

# Import modules nội bộ
from models import BiddingPackage, BiddingPackageFile, BiddingReqFinancialAdmin, BiddingReqPersonnel, BiddingReqEquipment
from minio_client import minio_handler, MINIO_BUCKET
from services.ai_pipeline.ingest import parse_pdf_to_markdown, chunk_by_chapters
from services.ai_pipeline.extract import prepare_context, extract_bid_info

# Setup Logger
logger = logging.getLogger(__name__)

async def analyze_bidding_package(hsmt_id: int, db: Session):
    """
    Quy trình phân tích hồ sơ thầu:
    1. Tải file PDF từ MinIO
    2. Parse PDF -> Markdown -> Text Chunks
    3. Gửi cho AI Extract thông tin
    4. Mapping và lưu vào Database
    """
    temp_path = None
    try:
        # 1. KIỂM TRA DỮ LIỆU ĐẦU VÀO
        package = db.query(BiddingPackage).filter(BiddingPackage.hsmt_id == hsmt_id).first()
        if not package:
            raise ValueError(f"Không tìm thấy gói thầu ID: {hsmt_id}")

        # Lấy file PDF (ưu tiên file E-HSMT)
        file_record = db.query(BiddingPackageFile)\
            .filter(BiddingPackageFile.hsmt_id == hsmt_id)\
            .filter(BiddingPackageFile.file_path.like('%.pdf'))\
            .first()
        
        if not file_record:
            raise ValueError(f"Không tìm thấy file PDF cho gói thầu ID: {hsmt_id}")

        # 2. DOWNLOAD FILE TỪ MINIO
        # Xử lý URL để lấy object_name sạch
        file_url = file_record.file_path
        if MINIO_BUCKET in file_url:
            # Tách lấy phần sau tên bucket
            object_name = file_url.split(f"/{MINIO_BUCKET}/")[1]
        else:
            object_name = urlparse(file_url).path.lstrip('/')
        
        object_name = unquote(object_name) # Giải mã URL (%20 -> Space)
        
        # Tạo tên file tạm ngẫu nhiên để tránh xung đột
        temp_path = f"temp_{uuid.uuid4()}.pdf"
        
        logger.info(f"⬇️ Đang tải file: {object_name}")
        if not minio_handler.download_file(object_name, temp_path):
             raise ValueError("Lỗi tải file từ MinIO (Check lại log MinIO)")

        # 3. CHẠY PIPELINE AI
        logger.info("🤖 Bắt đầu xử lý AI...")
        
        # Bước A: Ingest
        md_text = parse_pdf_to_markdown(temp_path)
        chunks = chunk_by_chapters(md_text)
        
        # Bước B: Extract
        context_text = prepare_context(chunks)
        ai_data = extract_bid_info(context_text) # Trả về Pydantic Model (BiddingData)

        # 4. LƯU DATABASE (QUAN TRỌNG)
        logger.info("💾 Đang lưu kết quả vào Database...")

        # --- Chiến thuật: XÓA CŨ - THÊM MỚI (Để tránh duplicate khi chạy lại) ---
        db.query(BiddingReqFinancialAdmin).filter_by(hsmt_id=hsmt_id).delete()
        db.query(BiddingReqPersonnel).filter_by(hsmt_id=hsmt_id).delete()
        db.query(BiddingReqEquipment).filter_by(hsmt_id=hsmt_id).delete()
        
        def clean_money(value):
            """
            Chuyển đổi chuỗi tiền tệ (VD: '160.000.000 VND') thành số thực (160000000.0)
            """
            if value is None:
                return None
            
            # Nếu đã là số (int/float) thì trả về luôn
            if isinstance(value, (int, float)):
                return value
                
            # Nếu là chuỗi: Xóa hết các ký tự không phải số (trừ dấu chấm thập phân nếu cần)
            # Ở VN thường dùng dấu chấm để ngăn cách hàng nghìn, nên ta xóa dấu chấm đi
            # VD: "160.000.000" -> "160000000"
            clean_str = re.sub(r'[^\d]', '', str(value))
            
            if not clean_str:
                return None
                
            try:
                return float(clean_str)
            except ValueError:
                return None
        
        # A. Lưu bảng Financial & Admin (Gộp mục 2 & 3)
        admin_section = ai_data.section_2_admin
        finance_section = ai_data.section_3_financial

        req_fin_admin = BiddingReqFinancialAdmin(
            hsmt_id=hsmt_id,
            # Mapping Admin Requirements
            bid_validity_days=admin_section.bid_validity_days,
            bid_security_value=clean_money(admin_section.bid_security_value),
            bid_security_duration=admin_section.bid_security_duration,
            submission_fee=clean_money(admin_section.submission_fee),
            contract_duration_text=admin_section.contract_duration,
            
            # Mapping Financial Requirements
            req_revenue_avg=clean_money(finance_section.avg_revenue),
            req_working_capital=clean_money(finance_section.working_capital),
            req_similar_contract_qty=finance_section.similar_contract_qty,
            req_similar_contract_value=clean_money(finance_section.min_contract_value),
            req_similar_contract_desc=finance_section.similar_contract_desc,
        )
        db.add(req_fin_admin)

        # B. Lưu bảng Nhân sự (Personnel) - SỬA LẠI VÒNG LẶP
        # Dùng enumerate để lấy số thứ tự (i bắt đầu từ 1)
        for i, p in enumerate(ai_data.section_4_personnel, start=1):
            req_personnel = BiddingReqPersonnel(
                hsmt_id=hsmt_id,
                stt=i,  # <--- Gán số thứ tự vào đây
                position_name=p.position,
                quantity=p.quantity,
                min_exp_years=p.experience_years,
                qualification_req=p.qualification,
                similar_project_exp=p.similar_project_exp
            )
            db.add(req_personnel)

        # C. Lưu bảng Thiết bị (Equipment) - SỬA LẠI VÒNG LẶP
        for i, e in enumerate(ai_data.section_5_equipment, start=1):
            req_equipment = BiddingReqEquipment(
                hsmt_id=hsmt_id,
                stt=i,  # <--- Gán số thứ tự vào đây
                equipment_name=e.name,
                quantity=e.quantity,
                specifications=e.specs
            )
            db.add(req_equipment)

        # Commit Transaction
        db.commit()
        logger.info(f"✅ Phân tích xong gói thầu {hsmt_id}!")

        # Trả về kết quả để hiển thị Frontend (nếu cần)
        return {
            "status": "success", 
            "message": "Phân tích hoàn tất", 
            "data": ai_data.model_dump() # Pydantic v2 dùng model_dump(), v1 dùng dict()
        }

    except Exception as e:
        db.rollback() # Hoàn tác nếu lỗi database
        logger.error(f"❌ Lỗi trong quá trình phân tích: {str(e)}")
        raise e
        
    finally:
        # 5. Cleanup file tạm
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
            logger.info("🧹 Đã dọn dẹp file tạm.")