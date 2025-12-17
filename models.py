from sqlalchemy import Column, Integer, Numeric, String, Boolean, DateTime, Float, ForeignKey, Text, Date, Enum, Unicode, JSON, UnicodeText
from sqlalchemy.orm import relationship, sessionmaker, Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.dialects.mssql import NVARCHAR
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

class UnitType(str, enum.Enum):
    GROUP = "GROUP"           # Tập đoàn
    BLOCK = "BLOCK"           # Khối
    BOARD = "BOARD"           # Ban
    SUBSIDIARY = "SUBSIDIARY" # Công ty con
    DEPARTMENT = "DEPARTMENT" # Phòng

class AssignmentType(str, enum.Enum):
    MAIN = "MAIN"       # Xử lý chính
    SUPPORT = "SUPPORT" # Phối hợp
    REVIEW = "REVIEW"   # Duyệt

# Cập nhật lại TaskStatus theo yêu cầu 3.1
class TaskStatus(str, enum.Enum):
    OPEN = "OPEN"             # Chưa ai nhận
    ASSIGNED = "ASSIGNED"     # Đã giao (có người/đơn vị cụ thể)
    IN_PROGRESS = "IN_PROGRESS"
    PENDING_REVIEW = "PENDING_REVIEW"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    
class SecurityLevel(int, enum.Enum):
    PUBLIC = 1          # Công khai / Nhân viên thường
    INTERNAL = 2        # Nội bộ phòng ban
    CONFIDENTIAL = 3    # Mật (Cấp quản lý/Trưởng ban)
    SECRET = 4          # Tối mật (Lãnh đạo cấp cao)
    
# --- ENUMS CHO ABAC ---
class PolicyEffect(str, enum.Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"

class AttributeType(str, enum.Enum):
    STRING = "STRING"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    DECIMAL = "DECIMAL"
    LIST = "LIST"  # Dùng cho trường hợp so sánh danh sách (VD: user.roles in [...])
    
class AbacAction(str, enum.Enum):
    VIEW = "VIEW"           # Xem chi tiết
    LIST = "LIST"           # Xem danh sách
    CREATE = "CREATE"       # Tạo mới
    UPDATE = "UPDATE"       # Cập nhật thông thường
    DELETE = "DELETE"       # Xóa
    APPROVE = "APPROVE"     # Phê duyệt (Action đặc biệt)
    REJECT = "REJECT"       # Từ chối
    ASSIGN = "ASSIGN"       # Giao việc
# ==========================================
# 1. PHÂN HỆ TỔ CHỨC & QUẢN TRỊ (ORGANIZATION & ADMIN)
# ==========================================

class User(Base):
    __tablename__ = "users"
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column((String), nullable=False)
    full_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.ENGINEER, nullable=False)
    status: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # --- CÁC TRƯỜNG MỚI CHO ABAC ---
    org_unit_id: Mapped[Optional[int]] = mapped_column(ForeignKey("organizational_units.unit_id"))
    job_title: Mapped[Optional[str]] = mapped_column(Unicode(100)) # VD: Chuyên viên chính
    security_clearance: Mapped[SecurityLevel] = mapped_column(
        Enum(SecurityLevel), 
        default=SecurityLevel.PUBLIC,
        nullable=False
    )

    # Relationships
    org_unit: Mapped[Optional["OrganizationalUnit"]] = relationship(foreign_keys=[org_unit_id], back_populates="members")
    audit_logs = relationship("AuditLog", back_populates="user")

# 1.1. Bảng Mới: Cơ cấu tổ chức
class OrganizationalUnit(Base):
    __tablename__ = "organizational_units"

    unit_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    unit_name: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    unit_code: Mapped[str] = mapped_column(String(50), unique=True, index=True) # VD: BLOCK_ENERGY
    
    # Self-referencing FK: Đơn vị cha
    parent_unit_id: Mapped[Optional[int]] = mapped_column(ForeignKey("organizational_units.unit_id"))
    
    unit_type: Mapped[UnitType] = mapped_column(Enum(UnitType), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(UnicodeText)
    
    # Người đứng đầu (Trưởng ban/GĐ Khối)
    manager_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.user_id"), nullable=True)

    # Relationships
    parent: Mapped[Optional["OrganizationalUnit"]] = relationship(remote_side=[unit_id], back_populates="children")
    children: Mapped[List["OrganizationalUnit"]] = relationship(back_populates="parent")
    
    manager: Mapped[Optional["User"]] = relationship(foreign_keys=[manager_id])
    members: Mapped[List["User"]] = relationship(foreign_keys="[User.org_unit_id]", back_populates="org_unit")
    
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
    
# ==========================================
# 2. CẤU HÌNH CÀO DỮ LIỆU (CRAWLER CONFIGURATION)
# ==========================================
class CrawlSchedule(Base):
    __tablename__ = "crawl_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # ID của nguồn (VD: Muasamcong, DauThauInfo...)
    source_url: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    
    # Chuỗi Cron chuẩn (VD: "0 */2 * * *" - Chạy 2 tiếng/lần)
    cron_expression: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Mô tả (VD: "Quét dạo ban đêm")
    description: Mapped[Optional[str]] = mapped_column(NVARCHAR(None), nullable=True)
    
    # Trạng thái bật/tắt
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

# 2. Bảng Luật tìm kiếm (Thay thế cho keywords/exclude_keywords cũ)
class CrawlRule(Base):
    __tablename__ = "crawl_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Tên luật (VD: "Săn gói thầu Trạm biến áp > 100 tỷ")
    rule_name: Mapped[str] = mapped_column(UnicodeText(255), nullable=False)
    
    # Lĩnh vực (Mới thêm vào)
    business_field: Mapped[Optional[str]] = mapped_column(UnicodeText(100), nullable=True)
    
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
    
class CrawlLog(Base):
    __tablename__ = "crawl_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[Optional[int]] = mapped_column(ForeignKey("crawl_rules.id"))
    
    # Thời gian bắt đầu và kết thúc
    start_time: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Kết quả
    status: Mapped[str] = mapped_column(String(50)) # "SUCCESS", "FAILED", "RUNNING"
    packages_found: Mapped[int] = mapped_column(Integer, default=0) # Số gói tìm thấy
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    packages_failed: Mapped[int] = mapped_column(Integer, default=0) # Số lượng thất bại
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # Lưu JSON chi tiết lỗi
    
    # Quan hệ
    rule: Mapped["CrawlRule"] = relationship()
# ==========================================
# 3. PHÂN HỆ ĐẦU VÀO (INPUT & HSMT) [cite: 44, 46]
# ==========================================
class BiddingPackage(Base):
    __tablename__ = "bidding_packages"
    
    hsmt_id : Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bidding_project.id"))
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
    
    # 1. Quan hệ n-1 với Dự án (Project)
    project: Mapped["BiddingProject"] = relationship(back_populates="packages")
    
    # 2. Quan hệ 1-n với File đính kèm
    files: Mapped[List["BiddingPackageFile"]] = relationship(back_populates="package", cascade="all, delete-orphan")
    
    # 3. Quan hệ 1-n với Nhà thầu tham gia (TenderContractor)
    contractors: Mapped[List["TenderContractor"]] = relationship(back_populates="package", cascade="all, delete-orphan")
    
class BiddingPackageFile(Base): # [cite: 183]
    __tablename__ = "bidding_package_files"
    
    file_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hsmt_id: Mapped[int] = mapped_column(Integer, ForeignKey("bidding_packages.hsmt_id"))
    file_name: Mapped[str] = mapped_column(Unicode(255)) # Tên file gốc
    file_type: Mapped[str] = mapped_column(String(100)) # HSMT, Phụ lục, Bản vẽ...
    upload_date: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    file_path: Mapped[str] = mapped_column(String(500)) # Đường dẫn lưu trữ file
    package: Mapped["BiddingPackage"] = relationship(back_populates="files")


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
    
    project_template: Mapped["BiddingProjectTemplate"] = relationship()
    task_template: Mapped["BiddingTaskTemplate"] = relationship()
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
    # --- BỔ SUNG RELATIONSHIPS MỚI ---
    # 1. Quan hệ với User (Người chủ trì)
    host: Mapped["User"] = relationship(foreign_keys=[host_id])
    
    # 2. Quan hệ với User (Trưởng nhóm thầu)
    team_leader: Mapped[Optional["User"]] = relationship(foreign_keys=[bid_team_leader_id])
    
    # 3. Quan hệ với Log nộp thầu (BidSubmitLog)
    submit_logs: Mapped[List["BidSubmitLog"]] = relationship(back_populates="project")



class BidSubmitLog(Base):
    __tablename__ = "bid_submit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bidding_project_id: Mapped[int] = mapped_column(ForeignKey("bidding_project.id"))
    snapshot_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    snapshot_data: Mapped[Optional[dict]] = mapped_column(JSON) # Log lại data lúc submit
    archive_file_path: Mapped[Optional[str]] = mapped_column(Unicode(500))
    file_checksum: Mapped[Optional[str]] = mapped_column(String(64)) # MD5/SHA256 checksum của file nộp
    
    # --- BỔ SUNG RELATIONSHIP ---
    project: Mapped["BiddingProject"] = relationship(back_populates="submit_logs")
class TenderContractor(Base):
    __tablename__ = "tender_contractor" # Bảng này nằm góc dưới bên phải
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hsmt_id: Mapped[int] = mapped_column(Integer, ForeignKey("bidding_packages.hsmt_id"))
    
    contractor_name: Mapped[Optional[str]] = mapped_column(Unicode(255))
    financial_requirements: Mapped[Optional[str]] = mapped_column(NVARCHAR(None)) # Yêu cầu tài chính
    technical_requirements: Mapped[Optional[str]] = mapped_column(NVARCHAR(None)) # Yêu cầu kỹ thuật
    experience_requirements: Mapped[Optional[str]] = mapped_column(NVARCHAR(None)) # Yêu cầu kinh nghiệm
    ai_score: Mapped[Optional[Float]] = mapped_column(Float, nullable=True) # Điểm đánh giá AI
    status: Mapped[Optional[str]] = mapped_column(String(50))

    package: Mapped["BiddingPackage"] = relationship(back_populates="contractors")
    
# ==========================================
# QUẢN LÝ CÔNG VIỆC & PHÂN QUYỀN (TASK & ASSIGNMENT)
# ==========================================

# 3.2. Bảng Mới: Task Assignments (Quy tắc giao việc)
class TaskAssignment(Base):
    __tablename__ = "task_assignments"

    assignment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("bidding_task.id"), nullable=False)
    
    # Giao cho Đơn vị (Phòng/Ban)
    assigned_unit_id: Mapped[Optional[int]] = mapped_column(ForeignKey("organizational_units.unit_id"))
    
    # Giao đích danh User (Ghi đè unit nếu có)
    assigned_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.user_id"))
    
    # Các luật ABAC để lọc người nhận
    required_role: Mapped[Optional[str]] = mapped_column(String(50)) # VD: 'MANAGER'
    required_min_security: Mapped[SecurityLevel] = mapped_column(
        Enum(SecurityLevel), 
        default=SecurityLevel.PUBLIC,
        nullable=False
    )
    assignment_type: Mapped[AssignmentType] = mapped_column(Enum(AssignmentType), default=AssignmentType.MAIN)
    is_accepted: Mapped[bool] = mapped_column(Boolean, default=False) # User đã bấm nhận việc chưa

    # Relationships
    task: Mapped["BiddingTask"] = relationship(back_populates="assignments")
    unit: Mapped[Optional["OrganizationalUnit"]] = relationship()
    user: Mapped[Optional["User"]] = relationship()
    
# 3.1. Sửa Bảng: BiddingTask
class BiddingTask(Base):
    __tablename__ = "bidding_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bidding_project_id: Mapped[int] = mapped_column(ForeignKey("bidding_project.id"))
    parent_task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bidding_task.id"))
    template_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bidding_task_templates.id"))
    
    task_name: Mapped[str] = mapped_column(Unicode(255))
    
    # assignee_id cũ vẫn giữ để lưu người đang thực thi chính (sau khi accept assignment)
    assignee_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.user_id"), nullable=True) 
    reviewer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Cập nhật Enum status mới
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.OPEN)
    
    is_milestone: Mapped[bool] = mapped_column(Boolean, default=False)
    source_type: Mapped[Optional[str]] = mapped_column(String(50))
    ai_reasoning: Mapped[Optional[dict]] = mapped_column(JSON)
    hsmt_ref_page: Mapped[Optional[int]] = mapped_column(Integer)

    # Relationships
    project: Mapped["BiddingProject"] = relationship(back_populates="tasks")
    
    # Quan hệ với bảng Assignments mới
    assignments: Mapped[List["TaskAssignment"]] = relationship(back_populates="task", cascade="all, delete-orphan")

    # Self-referential relationships
    parent: Mapped[Optional["BiddingTask"]] = relationship(remote_side=[id], back_populates="sub_tasks")
    sub_tasks: Mapped[List["BiddingTask"]] = relationship(back_populates="parent", cascade="all, delete-orphan")

    assignee: Mapped[Optional["User"]] = relationship(foreign_keys=[assignee_id])
    reviewer: Mapped[Optional["User"]] = relationship(foreign_keys=[reviewer_id])
    template: Mapped[Optional["BiddingTaskTemplate"]] = relationship()

# ==========================================
# 4. PHÂN HỆ BẢO MẬT & ABAC (SECURITY POLICIES)
# ==========================================

class AbacAttribute(Base):
    """
    Bảng từ điển thuộc tính (Dictionary):
    Giúp Admin biết có những biến nào để viết luật.
    VD: user.department_id, resource.total_amount
    """
    __tablename__ = "attributes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Tên biến dùng trong JSON (VD: user.org_unit_id)
    attr_key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    
    # Kiểu dữ liệu để Parser biết cách so sánh
    attr_type: Mapped[AttributeType] = mapped_column(Enum(AttributeType), default=AttributeType.STRING, nullable=False)
    
    # Nguồn dữ liệu (VD: users, bidding_packages) - Dùng để document
    source_table: Mapped[Optional[str]] = mapped_column(String(50))
    
    # Mô tả chi tiết (VD: "ID phòng ban của người dùng hiện tại")
    description: Mapped[Optional[str]] = mapped_column(Unicode(255))


class AbacPolicy(Base):
    """
    Bảng chứa các luật truy cập (Policies).
    Đây là trái tim của hệ thống phân quyền động.
    """
    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Tên chính sách (VD: "Trưởng phòng duyệt bài nội bộ")
    name: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    
    # Mô tả chi tiết mục đích của policy
    description: Mapped[Optional[str]] = mapped_column(UnicodeText)
    
    # Đối tượng chịu tác động (VD: bidding_task, bidding_package)
    # Có thể index trường này để query policy nhanh hơn theo resource
    target_resource: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    # Hành động (VD: VIEW, UPDATE, APPROVE, DELETE)
    # --- THAY ĐỔI QUAN TRỌNG Ở ĐÂY ---
    # 1. Dùng kiểu JSON của SQLAlchemy
    # 2. Python type là List[str]
    # 3. Mặc định là list rỗng []
    action: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    
    # Kết quả: ALLOW (Cho phép) hoặc DENY (Chặn)
    effect: Mapped[PolicyEffect] = mapped_column(Enum(PolicyEffect), default=PolicyEffect.ALLOW, nullable=False)
    
    # Độ ưu tiên: Số càng lớn càng ưu tiên (Giải quyết xung đột nếu có 2 luật trái ngược)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    
    # Điều kiện logic (Lõi ABAC)
    # Lưu cấu trúc logic. Ví dụ:
    # {
    #   "condition": "AND",
    #   "rules": [
    #       {"field": "user.role", "operator": "eq", "value": "MANAGER"},
    #       {"field": "user.org_unit_id", "operator": "eq", "value": "resource.unit_id"}
    #   ]
    # }
    condition_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    
    # Trạng thái bật tắt policy
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime,server_default=func.now(), onupdate=func.now())