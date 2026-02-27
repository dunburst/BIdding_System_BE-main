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
from app.modules.bidding.requirement.model import BiddingReqFinancialAdmin, BiddingReqPersonnel, BiddingReqEquipment
from app.modules.bidding.package.model import BiddingPackage, BiddingPackageFile
from app.infrastructure.storage.minio_client import minio_handler, MINIO_BUCKET
from app.integrations.ai.pipeline.ingest import parse_pdf_to_markdown, chunk_by_chapters
from app.integrations.ai.pipeline.extract import prepare_context, extract_bid_info

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
# # Đảm bảo hàm này là hàm đã sửa dùng DeepSeek API
# from services.ai_pipeline.extract import extract_bid_info, BiddingData, extract_list_from_large_context

# # Setup Logger
# logger = logging.getLogger(__name__)

# # --- HELPER CLASSES ---
# class SafeObject:
#     """Class giả lập để tránh lỗi Attribute Error khi truy cập vào None"""
#     def __getattr__(self, name):
#         return None

# def ensure_obj(obj):
#     """Nếu object bị None, trả về SafeObject để code không bị crash"""
#     return obj if obj else SafeObject()

# def clean_money(val):
#     """Chuyển đổi chuỗi tiền tệ sang số float an toàn"""
#     if val is None or val == "": return None
#     if isinstance(val, (int, float)): return float(val)
#     # Xử lý chuỗi: "1,000,000" -> 1000000, "1.5 tỷ" -> 1.5 (DeepSeek thường đã xử lý tỷ rồi)
#     val_str = str(val).replace(',', '').replace('_', '')
#     # Regex tìm số (hỗ trợ số thực và số nguyên)
#     s = re.search(r'-?\d+(\.\d+)?', val_str)
#     if s:
#         return float(s.group())
#     return None

# # --- MAIN FUNCTION ---
# async def analyze_bidding_package(hsmt_id: int, db: Session):
#     temp_path = None
#     try:
#         # 1. SETUP & DOWNLOAD FILE
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
#         logger.info(f"⬇️ [IO] Downloading PDF: {object_name}")
#         if not minio_handler.download_file(object_name, temp_path):
#              raise ValueError("Lỗi tải file từ MinIO")

#         # 2. INGESTION (Đọc & Chia nhỏ)
#         logger.info("📄 [Parse] Đang đọc PDF và chuyển sang Markdown...")
#         md_text = parse_pdf_to_markdown(temp_path)
        
#         logger.info("✂️ [Chunk] Đang phân tách chương mục...")
#         chunks = chunk_by_chapters(md_text) 

#         # 3. CHIẾN THUẬT: CHIA ĐỂ TRỊ
#         # Gom nhóm context
#         finance_chunks = [c['full_content'] for c in chunks if c['category'] in ['financial', 'admin', 'evaluation_criteria', 'general']]
#         context_fin = "\n---\n".join(finance_chunks)
        
#         personnel_chunks = [c['full_content'] for c in chunks if c['category'] in ['personnel', 'evaluation_criteria']]
#         context_per = "\n---\n".join(personnel_chunks)

#         equipment_chunks = [c['full_content'] for c in chunks if c['category'] in ['equipment', 'technical_requirements']]
#         context_eq = "\n---\n".join(equipment_chunks)

#         # 4. GỌI DEEPSEEK API
        
#         # --- PHASE 1: TÀI CHÍNH ---
#         # Tài chính thường nằm tập trung ở đầu, không cần cắt nhỏ, dùng truncate là đủ
#         if len(context_fin) > 50:
#             logger.info(f"🚀 1/3: DeepSeek đọc TÀI CHÍNH...")
#             # Vẫn dùng safe_truncate cho Tài chính vì nó chỉ cần lấy số liệu tổng quan
#             data_fin = extract_list_from_large_context(context_fin, data_type="financial")
#         else:
#             data_fin = BiddingData() #type: ignore

#         # --- PHASE 2: NHÂN SỰ (Dùng hàm mới: Chia nhỏ & Tìm kiếm) ---
#         if len(context_per) > 50:
#             logger.info(f"🚀 2/3: DeepSeek quét toàn bộ NHÂN SỰ ({len(context_per)} chars)...")
#             # KHÔNG truncate nữa, mà dùng hàm chia nhỏ
#             data_per = extract_list_from_large_context(context_per, data_type="personnel")
#         else:
#             data_per = BiddingData() #type: ignore

#         # --- PHASE 3: THIẾT BỊ (Dùng hàm mới: Chia nhỏ & Tìm kiếm) ---
#         if len(context_eq) > 50:
#             logger.info(f"🚀 3/3: DeepSeek quét toàn bộ THIẾT BỊ ({len(context_eq)} chars)...")
#             # KHÔNG truncate nữa, mà dùng hàm chia nhỏ
#             data_eq = extract_list_from_large_context(context_eq, data_type="equipment")
#         else:
#             data_eq = BiddingData() #type: ignore  

#         # 5. LƯU DATABASE & CLEANING
#         logger.info("💾 Đang lưu kết quả vào Database...")
        
#         # Clean dữ liệu cũ
#         db.query(BiddingReqFinancialAdmin).filter_by(hsmt_id=hsmt_id).delete()
#         db.query(BiddingReqPersonnel).filter_by(hsmt_id=hsmt_id).delete()
#         db.query(BiddingReqEquipment).filter_by(hsmt_id=hsmt_id).delete()

#         # A. Lưu Tài chính
#         # Sử dụng hàm ensure_obj giúp code gọn hơn rất nhiều so với type('obj'...) cũ
#         admin = ensure_obj(data_fin.section_2_admin)
#         fin = ensure_obj(data_fin.section_3_financial)

#         # Kiểm tra xem có dữ liệu không trước khi add (tránh add dòng trống trơn)
#         if data_fin.section_2_admin or data_fin.section_3_financial:
#             req_fin = BiddingReqFinancialAdmin(
#                 hsmt_id=hsmt_id,
#                 bid_validity_days=admin.bid_validity_days,
#                 bid_security_value=clean_money(admin.bid_security_value),
#                 bid_security_duration=admin.bid_security_duration,
#                 submission_fee=clean_money(admin.submission_fee),
#                 contract_duration_text=admin.contract_duration,
                
#                 req_revenue_avg=clean_money(fin.avg_revenue),
#                 req_working_capital=clean_money(fin.working_capital),
#                 req_similar_contract_qty=fin.similar_contract_qty,
#                 req_similar_contract_value=clean_money(fin.min_contract_value),
#                 req_similar_contract_desc=fin.similar_contract_desc
#             )
#             db.add(req_fin)

#         # B. Lưu Nhân sự
#         if data_per.section_4_personnel:
#             for i, p in enumerate(data_per.section_4_personnel, 1):
#                 db.add(BiddingReqPersonnel(
#                     hsmt_id=hsmt_id,
#                     stt=i,
#                     position_name=p.position,
#                     quantity=p.quantity,
#                     min_exp_years=p.experience_years,
#                     qualification_req=p.qualification,
#                     similar_project_exp=p.similar_project_exp
#                 ))

#         # C. Lưu Thiết bị
#         if data_eq.section_5_equipment:
#             for i, e in enumerate(data_eq.section_5_equipment, 1):
#                 db.add(BiddingReqEquipment(
#                     hsmt_id=hsmt_id,
#                     stt=i,
#                     equipment_name=e.name,
#                     quantity=e.quantity,
#                     specifications=e.specs
#                 ))

#         db.commit()
        
#         count_p = len(data_per.section_4_personnel) if data_per.section_4_personnel else 0
#         count_e = len(data_eq.section_5_equipment) if data_eq.section_5_equipment else 0
        
#         logger.info(f"✅ [SUCCESS] Đã lưu {count_p} nhân sự và {count_e} thiết bị.")
        
#         return {
#             "status": "success", 
#             "personnel_count": count_p,
#             "equipment_count": count_e
#         }

#     except Exception as e:
#         db.rollback()
#         logger.error(f"❌ ERROR analyze_bidding_package: {str(e)}", exc_info=True)
#         raise e
#     finally:
#         if temp_path and os.path.exists(temp_path):
#             try:
#                 os.remove(temp_path)
#             except:
#                 pass