from sqlalchemy import Column, Integer, Numeric, String, Boolean, DateTime, Float, ForeignKey, Text, Date, Enum, Unicode, JSON, UnicodeText
from sqlalchemy.orm import relationship, sessionmaker, Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.ext.hybrid import hybrid_property
import enum
from decimal import Decimal
from typing import Optional, List
from database import Base
from datetime import date, datetime

# --- ENUMS (Định nghĩa các trạng thái nghiệp vụ) [cite: 64, 140, 150] ---
class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"             # Lãnh đạo
    BID_MANAGER = "BID_MANAGER"     # Trưởng phòng / Chủ trì
    SPECIALIST = "SPECIALIST"       # Chuyên viên
    ENGINEER = "ENGINEER"           # Kỹ sư
    
class PackageStatus(str, enum.Enum):
    NEW = "NEW"
    INTERESTED = "INTERESTED" # Quan tâm
    NO_GO = "NO_GO" # Không dự thầu
    BIDDING = "BIDDING" # Dự thầu
    SUBMITTED = "SUBMITTED" # Đã nộp
    CLOSED = "CLOSED"

class TaskStatus(str, enum.Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    PENDING_REVIEW = "PENDING_REVIEW" # Chờ duyệt
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"

# ==========================================
# 1. PHÂN HỆ QUẢN TRỊ (ADMIN) [cite: 40, 199]
# ==========================================

class User(Base):
    __tablename__ = "users"
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column((String), nullable=False)
    full_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.ENGINEER, nullable=False)
    status: Mapped[bool] = mapped_column(Boolean, default=True)

<<<<<<< HEAD
class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.user_id"))
    action: Mapped[str] = mapped_column(Unicode(255))
    entity_table: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[Optional[int]] = mapped_column(Integer)
    old_value: Mapped[Optional[dict]] = mapped_column(JSON) # Hỗ trợ lưu JSON log
    new_value: Mapped[Optional[dict]] = mapped_column(JSON)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="audit_logs")
    
=======
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
class CrawlSchedule(Base):
    __tablename__ = "crawl_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # ID của nguồn (VD: Muasamcong, DauThauInfo...)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Chuỗi Cron chuẩn (VD: "0 */2 * * *" - Chạy 2 tiếng/lần)
    cron_expression: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Mô tả (VD: "Quét dạo ban đêm")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Trạng thái bật/tắt
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

# 2. Bảng Luật tìm kiếm (Thay thế cho keywords/exclude_keywords cũ)
class CrawlRule(Base):
    __tablename__ = "crawl_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Tên luật (VD: "Săn gói thầu Trạm biến áp > 100 tỷ")
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Lĩnh vực (Mới thêm vào)
    business_field: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Mảng từ khóa BẮT BUỘC (Lưu dưới dạng JSON List trong DB)
    keywords_include: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=True)
    
    # Mảng từ khóa LOẠI TRỪ
    keywords_exclude: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=True)
    
    # Giá gói thầu (Dùng Numeric để chính xác tiền tệ)
    min_budget: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 0), nullable=True)
    max_budget: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 0), nullable=True)
    
    # Khu vực (JSON List)
    locations: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=True)
    
    # Độ ưu tiên
    priority: Mapped[int] = mapped_column(Integer, default=1, nullable=True)
    
# ==========================================
# 2. PHÂN HỆ ĐẦU VÀO (INPUT & HSMT) [cite: 44, 46]
# ==========================================
class BiddingPackage(Base):
    __tablename__ = "bidding_packages"
    
    hsmt_id : Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    #thông tin cơ bản
    ma_tbmt:Mapped[str] = mapped_column(String(50), unique=True, index=True) # Mã TBMT để check trùng 
    phien_ban_thay_doi: Mapped[str] = mapped_column(String(10), default='00')
    ngay_dang_tai: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True) # 05/12/2025 11:23
    #thông tin chung của KHLCNT
    ma_khlcnt: Mapped[str] = mapped_column(String(20),)     # Mã KHLCNT (PL24...)
    phan_loai_khlcnt: Mapped[Optional[str]] = mapped_column(Unicode(100), nullable=True) # Chi thường xuyên
    ten_du_an:Mapped[str] = mapped_column(Unicode(500))   # Tên dự toán mua sắm
    #thông tin gói thầu
    quy_trinh_ap_dung: Mapped[Optional[str]] = mapped_column(Unicode(255), nullable=True) # Quy trình áp dụng (Luật Đấu thầu...)
    ten_goi_thau:Mapped[str] = mapped_column(Unicode(500), nullable=False) # Tên gói thầu
    chu_dau_tu:Mapped[str] = mapped_column(Unicode(255)) # Bên mời thầu, chủ đầu tư
    chi_tiet_nguon_von: Mapped[Optional[str]] = mapped_column(UnicodeText, nullable=True) # Chi tiết nguồn vốn (Ngân sách xã)
    linh_vuc:Mapped[str] = mapped_column(Unicode(50)) # Lĩnh vực: Xây lắp, Hàng hóa...
    hinh_thuc_lua_chon_nha_thau: Mapped[Optional[str]] = mapped_column(Unicode(255), nullable=True) # Chào hàng cạnh tranh
    loai_hop_dong: Mapped[Optional[str]] = mapped_column(Unicode(100), nullable=True) # Trọn gói
    trong_nuoc_hoac_quoc_te: Mapped[Optional[str]] = mapped_column(Unicode(255), nullable =True) # Trong nước
    phuong_thuc_lua_chon_nha_thau: Mapped[Optional[str]] = mapped_column(Unicode(255), nullable=True) # Một giai đoạn một túi hồ sơ
    thoi_gian_thuc_hien_goi_thau: Mapped[Optional[str]] = mapped_column(Unicode(100), nullable=True) # 10 ngày
    goi_thau_co_nhieu_phan_lo: Mapped[Optional[str]] = mapped_column(Unicode(255), nullable= True) # Gói thầu có nhiều phần/lô (Không)
     # --- Cách thức dự thầu ---
    hinh_thuc_du_thau: Mapped[Optional[str]] = mapped_column(Unicode(100), nullable=True) # Qua mạng
    dia_diem_phat_hanh_e_hsmt: Mapped[Optional[str]] = mapped_column(UnicodeText, nullable=True) # Địa điểm phát hành e-HSMT
    chi_phi_nop: Mapped[Optional[float]] = mapped_column(Numeric(30, 2), nullable=True) # 220.000 VND
    dia_diem_nhan_e_hsdt: Mapped[Optional[str]] = mapped_column(UnicodeText, nullable=True) # Địa điểm nhận e-HSDT
    dia_diem_thuc_hien_goi_thau: Mapped[Optional[str]] = mapped_column(UnicodeText, nullable=True) # Xã Thanh Liêm, Tỉnh Ninh Bình
    
    # --- Thông tin dự thầu (Thời gian & Đảm bảo) ---
    thoi_diem_dong_thau: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True) # 16/12/2025 09:00
    thoi_diem_mo_thau: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    dia_diem_mo_thau: Mapped[Optional[str]] = mapped_column(UnicodeText, nullable=True)

    hieu_luc_hsdt: Mapped[Optional[str]] = mapped_column(Unicode(100), nullable=True) # 120 ngày
    so_tien_dam_bao_du_thau: Mapped[Optional[float]] = mapped_column(Numeric(30, 2), nullable=True) # 10.000.000 VND
    hinh_thuc_dam_bao_du_thau: Mapped[Optional[str]] = mapped_column(UnicodeText, nullable=True) # Cam kết
    loai_cong_trinh: Mapped[Optional[str]] = mapped_column(UnicodeText, nullable=True) # (Công trình xây dựng dân dụng)

    # --- Quyết định phê duyệt (Của TBMT) ---
    so_quyet_dinh_phe_duyet: Mapped[Optional[str]] = mapped_column(String(100), nullable=True) # 16-QĐ/VPĐU
    ngay_phe_duyet: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True) # 05/12/2025
    co_quan_ban_hanh_quyet_dinh: Mapped[Optional[str]] = mapped_column(Unicode(255), nullable=True)
    quyet_dinh_phe_duyet: Mapped[Optional[str]] = mapped_column(UnicodeText, nullable=True)
    
    duong_dan_goi_thau: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # Link gói thầu trên cổng TBMT
    trang_thai: Mapped[PackageStatus] = mapped_column(Enum(PackageStatus), default=PackageStatus.NEW, nullable=False)
    
    created_at:Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
class BiddingPackageFile(Base): # [cite: 183]
    __tablename__ = "bidding_package_files"
    
    file_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hsmt_id: Mapped[int] = mapped_column(Integer, ForeignKey("bidding_packages.hsmt_id"))
    file_name: Mapped[str] = mapped_column(Unicode(255)) # Tên file gốc
    file_type: Mapped[str] = mapped_column(String(100)) # HSMT, Phụ lục, Bản vẽ...
    upload_date: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    file_path: Mapped[str] = mapped_column(String(500)) # Đường dẫn lưu trữ file


<<<<<<< HEAD
# ==========================================
# GROUP 2: TEMPLATES (Mẫu dự án/công việc)
# ==========================================

class BiddingProjectTemplate(Base):
    __tablename__ = "bidding_project_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_name: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    template_file: Mapped[Optional[str]] = mapped_column(Unicode(500))


class BiddingTaskTemplate(Base):
    __tablename__ = "bidding_task_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_name: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Unicode(1000))


class TemplateStructure(Base):
    __tablename__ = "template_structure"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_template_id: Mapped[int] = mapped_column(ForeignKey("bidding_project_templates.id"))
    task_template_id: Mapped[int] = mapped_column(ForeignKey("bidding_task_templates.id"))
    default_order: Mapped[int] = mapped_column(Integer, default=0)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
# ==========================================
# GROUP 3: INTERNAL PROJECT MANAGEMENT (Quản lý dự án nội bộ)
# ==========================================
class BiddingProject(Base):
    __tablename__ = "bidding_project"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("users.user_id")) # Người chủ trì
    bid_team_leader_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.user_id")) # Trưởng nhóm thầu
    name: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    status: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, onupdate=func.now())
    
    # Quan hệ với gói thầu (One-to-Many hoặc One-to-One tùy nghiệp vụ)
    packages: Mapped[List["BiddingPackage"]] = relationship(back_populates="project")
    tasks: Mapped[List["BiddingTask"]] = relationship(back_populates="project")


class BiddingTask(Base):
    __tablename__ = "bidding_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bidding_project_id: Mapped[int] = mapped_column(ForeignKey("bidding_project.id"))
    parent_task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bidding_task.id")) # Self-referential
    template_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bidding_task_templates.id"))
    
    task_name: Mapped[str] = mapped_column(Unicode(255))
    assignee_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.user_id"))
    reviewer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.user_id"))
    
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[Optional[str]] = mapped_column(String(50))
    is_milestone: Mapped[bool] = mapped_column(Boolean, default=False)

    project: Mapped["BiddingProject"] = relationship(back_populates="tasks")
    sub_tasks: Mapped[List["BiddingTask"]] = relationship("BiddingTask")


class BidSubmitLog(Base):
    __tablename__ = "bid_submit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bidding_project_id: Mapped[int] = mapped_column(ForeignKey("bidding_project.id"))
    snapshot_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    snapshot_data: Mapped[Optional[dict]] = mapped_column(JSON) # Log lại data lúc submit
    archive_file_path: Mapped[Optional[str]] = mapped_column(Unicode(500))
    
class TenderContractor(Base):
    __tablename__ = "tender_contractor" # Bảng này nằm góc dưới bên phải
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hsmt_id: Mapped[int] = mapped_column(Integer, ForeignKey("bidding_packages.hsmt_id"))
    
    contractor_name: Mapped[Optional[str]] = mapped_column(Unicode(255))
    financial_requirements: Mapped[Optional[str]] = mapped_column(Unicode(1000)) # Yêu cầu tài chính
    technical_requirements: Mapped[Optional[str]] = mapped_column(Unicode(1000)) # Yêu cầu kỹ thuật
    experience_requirements: Mapped[Optional[str]] = mapped_column(Unicode(1000))
    
    status: Mapped[Optional[str]] = mapped_column(String(50))

    package: Mapped["BiddingPackage"] = relationship(back_populates="contractors")
=======
class BiddingTask(Base):
    __tablename__ = "bidding_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hsmt_id: Mapped[int] = mapped_column(Integer, ForeignKey("bidding_packages.hsmt_id"))
    task_name: Mapped[str] = mapped_column(String(255), nullable=False)



>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
