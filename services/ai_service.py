# services/ai_service.py
import os
import uuid
import logging
import re
from sqlalchemy.orm import Session
from urllib.parse import unquote, urlparse
from sqlalchemy.orm import Session
from sqlalchemy import text

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

# import os
# import uuid
# import logging
# import re
# from sqlalchemy.orm import Session
# from urllib.parse import unquote, urlparse

# # Import Models
# from models import BiddingPackage, BiddingPackageFile, BiddingReqFinancialAdmin, BiddingReqPersonnel, BiddingReqEquipment
# from minio_client import minio_handler, MINIO_BUCKET

# # Import Pipeline
# from services.ai_pipeline.ingest import parse_pdf_to_markdown, chunk_by_chapters
# from services.ai_pipeline.extract import extract_bid_info
# from services.ai_pipeline.extract import BiddingData

# # Setup Logger
# logger = logging.getLogger(__name__)

# async def analyze_bidding_package(hsmt_id: int, db: Session):
#     temp_path = None
#     try:
#         # 1. SETUP & DOWNLOAD FILE (Giữ nguyên logic cũ của bạn)
#         package = db.query(BiddingPackage).filter(BiddingPackage.hsmt_id == hsmt_id).first()
#         if not package: raise ValueError(f"Không tìm thấy gói thầu ID: {hsmt_id}")

#         file_record = db.query(BiddingPackageFile)\
#             .filter(BiddingPackageFile.hsmt_id == hsmt_id)\
#             .filter(BiddingPackageFile.file_path.like('%.pdf'))\
#             .first()
#         if not file_record: raise ValueError(f"Không tìm thấy file PDF")

#         # Xử lý URL & Download
#         file_url = file_record.file_path
#         if MINIO_BUCKET in file_url:
#             object_name = file_url.split(f"/{MINIO_BUCKET}/")[1]
#         else:
#             object_name = urlparse(file_url).path.lstrip('/')
#         object_name = unquote(object_name)
        
#         temp_path = f"temp_{uuid.uuid4()}.pdf"
#         logger.info(f"⬇️ Downloading: {object_name}")
#         if not minio_handler.download_file(object_name, temp_path):
#              raise ValueError("Lỗi tải file MinIO")

#         # 2. INGESTION (Đọc & Chia nhỏ)
#         logger.info("📄 Đang đọc và phân tách file...")
#         md_text = parse_pdf_to_markdown(temp_path)
#         chunks = chunk_by_chapters(md_text) # Hàm này bạn đã có trong code cũ

#         # 3. CHIẾN THUẬT: CHIA ĐỂ TRỊ (SPLIT & MERGE)
#         # Thay vì gửi tất cả, ta lọc chunk theo chủ đề để AI tập trung
        
#         # Nhóm A: Tài chính & Admin
#         finance_chunks = [c['full_content'] for c in chunks if c['category'] in ['financial', 'admin', 'evaluation_criteria', 'general']]
#         context_fin = "\n".join(finance_chunks)
        
#         # Nhóm B: Nhân sự (Quan trọng nhất)
#         personnel_chunks = [c['full_content'] for c in chunks if c['category'] in ['personnel', 'evaluation_criteria']]
#         context_per = "\n".join(personnel_chunks)

#         # Nhóm C: Thiết bị & Kỹ thuật
#         equipment_chunks = [c['full_content'] for c in chunks if c['category'] in ['equipment', 'technical_requirements']]
#         context_eq = "\n".join(equipment_chunks)

#         # 4. GỌI AI TUẦN TỰ
#         logger.info("🤖 1/3: Trích xuất Tài chính & Admin...")
#         data_fin = extract_bid_info(context_fin)

#         logger.info("🤖 2/3: Trích xuất Nhân sự...")
#         # Debug nhẹ để yên tâm
#         if "Chỉ huy trưởng" in context_per or "Nhân sự" in context_per:
#             logger.info("   -> Đã tìm thấy từ khóa nhân sự trong context gửi đi.")
#         else:
#             logger.warning("   -> ⚠️ Cảnh báo: Context nhân sự có vẻ thiếu dữ liệu!")
#         data_per = extract_bid_info(context_per)

#         logger.info("🤖 3/3: Trích xuất Thiết bị...")
#         data_eq = extract_bid_info(context_eq)

#         # 5. LƯU DATABASE
#         logger.info("💾 Đang lưu vào DB...")
        
#         # Clean cũ
#         db.query(BiddingReqFinancialAdmin).filter_by(hsmt_id=hsmt_id).delete()
#         db.query(BiddingReqPersonnel).filter_by(hsmt_id=hsmt_id).delete()
#         db.query(BiddingReqEquipment).filter_by(hsmt_id=hsmt_id).delete()

#         # Helper clean tiền
#         def clean_money(val):
#             if val is None: return None
#             if isinstance(val, (int, float)): return float(val)
#             s = re.sub(r'[^\d]', '', str(val))
#             return float(s) if s else None

#         # A. Lưu Tài chính (Lấy từ data_fin)
#         req_fin = BiddingReqFinancialAdmin(
#             hsmt_id=hsmt_id,
#             bid_validity_days=data_fin.section_2_admin.bid_validity_days,
#             bid_security_value=clean_money(data_fin.section_2_admin.bid_security_value),
#             bid_security_duration=data_fin.section_2_admin.bid_security_duration,
#             submission_fee=clean_money(data_fin.section_2_admin.submission_fee),
#             contract_duration_text=data_fin.section_2_admin.contract_duration,
            
#             req_revenue_avg=clean_money(data_fin.section_3_financial.avg_revenue),
#             req_working_capital=clean_money(data_fin.section_3_financial.working_capital),
#             req_similar_contract_qty=data_fin.section_3_financial.similar_contract_qty,
#             req_similar_contract_value=clean_money(data_fin.section_3_financial.min_contract_value),
#             req_similar_contract_desc=data_fin.section_3_financial.similar_contract_desc
#         )
#         db.add(req_fin)

#         # B. Lưu Nhân sự (Lấy từ data_per)
#         # Lưu ý: data_per.section_4_personnel mới là nơi chứa dữ liệu đúng
#         for i, p in enumerate(data_per.section_4_personnel, 1):
#             db.add(BiddingReqPersonnel(
#                 hsmt_id=hsmt_id,
#                 stt=i,
#                 position_name=p.position, # Giờ đây sẽ là tiếng Việt chuẩn
#                 quantity=p.quantity,
#                 min_exp_years=p.experience_years,
#                 qualification_req=p.qualification,
#                 similar_project_exp=p.similar_project_exp
#             ))

#         # C. Lưu Thiết bị (Lấy từ data_eq)
#         for i, e in enumerate(data_eq.section_5_equipment, 1):
#             db.add(BiddingReqEquipment(
#                 hsmt_id=hsmt_id,
#                 stt=i,
#                 equipment_name=e.name,
#                 quantity=e.quantity,
#                 specifications=e.specs
#             ))

#         db.commit()
#         logger.info(f"✅ Hoàn tất! Đã lưu {len(data_per.section_4_personnel)} nhân sự và {len(data_eq.section_5_equipment)} thiết bị.")
        
#         return {"status": "success", "personnel_count": len(data_per.section_4_personnel)}

#     except Exception as e:
#         db.rollback()
#         logger.error(f"❌ ERROR: {str(e)}")
#         raise e
#     finally:
#         if temp_path and os.path.exists(temp_path):
#             os.remove(temp_path)