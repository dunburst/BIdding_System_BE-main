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

# ==========================================
# 0. ENUMS (Định nghĩa các trạng thái nghiệp vụ)
# ==========================================
class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"             # Lãnh đạo
    BID_MANAGER = "BID_MANAGER"     # Trưởng phòng / Chủ trì
    SPECIALIST = "SPECIALIST"       # Chuyên viên
    ENGINEER = "ENGINEER"           # Kỹ sư
    JKAN = "JKAN"                   # Thành viên dự án nào cũng có
    
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

class TaskStatus(str, enum.Enum):
    OPEN = "OPEN"             # Chưa ai nhận
    ASSIGNED = "ASSIGNED"     # Đã giao (có người/đơn vị cụ thể)
    IN_PROGRESS = "IN_PROGRESS"
    PENDING_REVIEW = "PENDING_REVIEW"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    
class TaskTag(str, enum.Enum):
    LEGAL = "LEGAL"           # Hồ sơ pháp lý
    FINANCE = "FINANCE"       # Hồ sơ tài chính
    TECH = "TECH"             # Biện pháp thi công
    CONTRACT = "CONTRACT"     # Hồ sơ hợp đồng tương tự
    DEVICE = "DEVICE"         # Hồ sơ máy móc thiết bị
    HR = "HR"                 # Hồ sơ nhân sự
    OTHER = "OTHER"           # Hồ sơ khác
    # --- [BỔ SUNG MỚI] ---
    DBTC = "DBTC"             # Bảo lãnh dự thầu, Cam kết tín dụng (BLDT, CKTD)
    VT = "VT"                 # Hồ sơ Vật tư
    GIA = "GIA"               # Hồ sơ Giá
    
class SecurityLevel(int, enum.Enum):
    PUBLIC = 1          # Công khai / Nhân viên thường
    INTERNAL = 2        # Nội bộ phòng ban
    CONFIDENTIAL = 3    # Mật (Cấp quản lý/Trưởng ban)
    SECRET = 4          # Tối mật (Lãnh đạo cấp cao)
    
class TaskPriority(str, enum.Enum):
    LOW = "LOW"         # Thấp
    MEDIUM = "MEDIUM"   # Trung bình
    HIGH = "HIGH"       # Cao/Gấp
    
class TaskType(str, enum.Enum):
    AUTO = "AUTO"           # Tự động (Hệ thống/AI tự chạy)
    SELECTION = "SELECTION" # Chọn (Người dùng chọn options)
    DRAFTING = "DRAFTING"   # Soạn thảo (Người dùng nhập liệu/Upload file)
    
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
    hashed_password: Mapped[str] = mapped_column((String), nullable=True)
    full_name: Mapped[str] = mapped_column(UnicodeText(100))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.ENGINEER, nullable=False)
    status: Mapped[bool] = mapped_column(Boolean, default=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # --- CÁC TRƯỜNG MỚI CHO ABAC ---
    org_unit_id: Mapped[Optional[int]] = mapped_column(ForeignKey("organizational_units.unit_id"))
    job_title: Mapped[Optional[str]] = mapped_column(Unicode(100)) # VD: Chuyên viên chính
    security_clearance: Mapped[SecurityLevel] = mapped_column(
        Enum(SecurityLevel), 
        default=SecurityLevel.PUBLIC,
        nullable=False
    )
    
    auth_provider: Mapped[str] = mapped_column(String(50), default="local") # 'google' hoặc 'local'

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
    # --- [BỔ SUNG MỚI] ---
    # Chủ đầu tư (Lưu danh sách tên các CĐT muốn tìm)
    investor: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=True)
    
    # Xã/Phường (Lưu danh sách xã phường cụ thể)
    commune: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=True)
    
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
# 3. PHÂN HỆ ĐẦU VÀO (INPUT & HSMT)
# ==========================================
class BiddingPackage(Base):
    __tablename__ = "bidding_packages"
    
    hsmt_id : Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bidding_project.id"))
    nguoi_duyet_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.user_id"), nullable=True)
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
    
    nguoi_duyet: Mapped[Optional["User"]] = relationship(foreign_keys=[nguoi_duyet_id])
    
    # 2. Quan hệ 1-n với File đính kèm
    files: Mapped[List["BiddingPackageFile"]] = relationship(back_populates="package", cascade="all, delete-orphan")
    result: Mapped[Optional["BiddingResult"]] = relationship(back_populates="package", uselist=False, cascade="all, delete-orphan")
    
    
    # 1. Quan hệ 1-1 với Yêu cầu Tài chính & Thủ tục
    # uselist=False giúp SQLAlchemy hiểu đây là quan hệ 1-1
    financial_req: Mapped[Optional["BiddingReqFinancialAdmin"]] = relationship(
        back_populates="package", 
        uselist=False, 
        cascade="all, delete-orphan"
    )

    # 2. Quan hệ 1-N với Yêu cầu Nhân sự
    personnel_reqs: Mapped[List["BiddingReqPersonnel"]] = relationship(
        back_populates="package", 
        cascade="all, delete-orphan"
    )

    # 3. Quan hệ 1-N với Yêu cầu Thiết bị
    equipment_reqs: Mapped[List["BiddingReqEquipment"]] = relationship(
        back_populates="package", 
        cascade="all, delete-orphan"
    )
    
class BiddingPackageFile(Base):
    __tablename__ = "bidding_package_files"
    
    file_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hsmt_id: Mapped[int] = mapped_column(Integer, ForeignKey("bidding_packages.hsmt_id"))
    file_name: Mapped[str] = mapped_column(Unicode(255)) # Tên file gốc
    file_type: Mapped[str] = mapped_column(String(100)) # HSMT, Phụ lục, Bản vẽ...
    upload_date: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    file_path: Mapped[str] = mapped_column(String(500)) # Đường dẫn lưu trữ file
    package: Mapped["BiddingPackage"] = relationship(back_populates="files")

# Bảng lưu kết quả chung (Gắn 1-1 với BiddingPackage)
# --- Cập nhật file models.py ---

class BiddingResult(Base):
    __tablename__ = "bidding_results"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hsmt_id: Mapped[int] = mapped_column(ForeignKey("bidding_packages.hsmt_id"), unique=True)
    
    # --- [MỚI] THÔNG TIN CHUNG (GENERAL INFO) ---
    result_status: Mapped[Optional[str]] = mapped_column(Unicode(255))        # Trạng thái KQLCNT
    posting_date: Mapped[Optional[datetime]] = mapped_column(DateTime)        # Ngày đăng tải
    
    approved_budget: Mapped[Optional[Decimal]] = mapped_column(Numeric(30,2)) # Dự toán gói thầu được duyệt
    package_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(30,2))   # Giá gói thầu

    approval_date: Mapped[Optional[datetime]] = mapped_column(DateTime)       # Ngày phê duyệt
    approving_agency: Mapped[Optional[str]] = mapped_column(Unicode(500))     # Cơ quan phê duyệt
    decision_number: Mapped[Optional[str]] = mapped_column(String(100))       # Số quyết định phê duyệt
    
    # Link file/văn bản
    decision_link: Mapped[Optional[str]] = mapped_column(String(500))         # Link Quyết định phê duyệt
    ehsdt_report_link: Mapped[Optional[str]] = mapped_column(String(500))     # Link Báo cáo đánh giá tổng hợp E-HSDT
    
    bidding_result_text: Mapped[Optional[str]] = mapped_column(Unicode(255))  # Kết quả đấu thầu (VD: Có nhà thầu trúng thầu)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Quan hệ
    package: Mapped["BiddingPackage"] = relationship(back_populates="result")
    
    # [THAY ĐỔI] Tách người trúng thầu ra bảng riêng để lưu được nhiều thành viên trong Liên danh
    winners: Mapped[List["BiddingResultWinner"]] = relationship(back_populates="result", cascade="all, delete-orphan")
    failed_bidders: Mapped[List["BiddingResultFailed"]] = relationship(back_populates="result", cascade="all, delete-orphan")
    items: Mapped[List["BiddingResultItem"]] = relationship(back_populates="result", cascade="all, delete-orphan")

# [BẢNG MỚI] Lưu danh sách nhà thầu trúng thầu (Hỗ trợ Liên danh nhiều thành viên)
class BiddingResultWinner(Base):
    __tablename__ = "bidding_results_winners"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("bidding_results.id"))
    
    bidder_code: Mapped[Optional[str]] = mapped_column(String(50))   # Mã định danh (vn...)
    tax_code: Mapped[Optional[str]] = mapped_column(String(50))      # Mã số thuế
    bidder_name: Mapped[Optional[str]] = mapped_column(Unicode(1000)) # Tên nhà thầu
    role: Mapped[Optional[str]] = mapped_column(Unicode(255))        # Tên liên danh
    
    # Các thông tin giá trị (thường giống nhau cho cả liên danh, nhưng cứ lưu để tiện)
    bid_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 2)) # Giá dự thầu
    corrected_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 2)) #Giá dự thầu sau hiệu chỉnh
    evaluated_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 2)) # Giá đánh giá
    winning_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 2)) # Giá trúng thầu
    technical_score: Mapped[Optional[str]] = mapped_column(String(100)) # Điểm kỹ thuật
    execution_time: Mapped[Optional[str]] = mapped_column(Unicode(500)) # Thời gian thực hiện (6 tháng...)
    # [MỚI] Thời gian thực hiện hợp đồng
    contract_period: Mapped[Optional[str]] = mapped_column(Unicode(500)) # Thời gian thực hiện hợp đồng 
    
    # [MỚI] Các nội dung khác
    other_content: Mapped[Optional[str]] = mapped_column(UnicodeText) # Nội dung khác (nếu có)
    
    result: Mapped["BiddingResult"] = relationship(back_populates="winners")

class BiddingResultFailed(Base):
    __tablename__ = "bidding_results_failed"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("bidding_results.id"))
    
    bidder_code: Mapped[Optional[str]] = mapped_column(String(50))   # Mã định danh (vn...)
    bidder_name: Mapped[Optional[str]] = mapped_column(Unicode(1000)) # Tên nhà thầu
    tax_code: Mapped[Optional[str]] = mapped_column(String(50)) # Mã số thuế
    
    # [MỚI] Hỗ trợ Liên danh
    joint_venture_name: Mapped[Optional[str]] = mapped_column(Unicode(1000)) # Tên Liên danh (nếu có)
    
    reason: Mapped[Optional[str]] = mapped_column(UnicodeText) # Lý do không trúng thầu
    
    result: Mapped["BiddingResult"] = relationship(back_populates="failed_bidders")

class BiddingResultItem(Base):
    __tablename__ = "bidding_results_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("bidding_results.id"))
    
    item_name: Mapped[Optional[str]] = mapped_column(Unicode(1000)) # Tên hàng hóa, dịch vụ
    model: Mapped[Optional[str]] = mapped_column(Unicode(500))      # Ký mã hiệu
    brand: Mapped[Optional[str]] = mapped_column(Unicode(500))      # Nhãn hiệu (Mới)
    manufacturer: Mapped[Optional[str]] = mapped_column(Unicode(500)) # Nhà sản xuất
    origin: Mapped[Optional[str]] = mapped_column(Unicode(255)) # Xuất xứ
    
    # [MỚI] Thông tin chi tiết hàng hóa (ảnh cuối)
    year_of_manufacture: Mapped[Optional[str]] = mapped_column(Unicode(100)) # Năm sản xuất
    technical_specs: Mapped[Optional[str]] = mapped_column(UnicodeText)    # Cấu hình/Thông số kỹ thuật
    
    result: Mapped["BiddingResult"] = relationship(back_populates="items")
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

# [MỚI] 1. Bảng lưu trữ các mẫu văn bản (Template) - Dùng cho Drafting Workspace
class DocumentTemplate(Base):
    __tablename__ = "document_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(Unicode(255), nullable=False)       # Tên mẫu (VD: Biên bản nghiệm thu)
    content: Mapped[str] = mapped_column(UnicodeText, nullable=False)      # Nội dung HTML
    category: Mapped[Optional[str]] = mapped_column(String(50), index=True) # Phân loại: HR, TECH, LEGAL...
    description: Mapped[Optional[str]] = mapped_column(Unicode(500), nullable=True)  # Mô tả ngắn
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)         # Ẩn/Hiện
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

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
    
    drive_folder_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(),onupdate=func.now())
    
    # Quan hệ với gói thầu (One-to-Many hoặc One-to-One tùy nghiệp vụ)
    packages: Mapped[List["BiddingPackage"]] = relationship(back_populates="project")
    tasks: Mapped[List["BiddingTask"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    
    # Relationships
    host: Mapped["User"] = relationship(foreign_keys=[host_id])
    team_leader: Mapped[Optional["User"]] = relationship(foreign_keys=[bid_team_leader_id])
    submit_logs: Mapped[List["BidSubmitLog"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class BidSubmitLog(Base):
    __tablename__ = "bid_submit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bidding_project_id: Mapped[int] = mapped_column(ForeignKey("bidding_project.id"))
    snapshot_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    snapshot_data: Mapped[Optional[dict]] = mapped_column(JSON) # Log lại data lúc submit
    archive_file_path: Mapped[Optional[str]] = mapped_column(Unicode(500))
    file_checksum: Mapped[Optional[str]] = mapped_column(String(64)) # MD5/SHA256 checksum của file nộp
    
    project: Mapped["BiddingProject"] = relationship(back_populates="submit_logs")
    
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
    template_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bidding_task_templates.id"), nullable=True)
    
    task_name: Mapped[str] = mapped_column(Unicode(255))
    
    # assignee_id cũ vẫn giữ để lưu người đang thực thi chính (sau khi accept assignment)
    assignee_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.user_id"), nullable=True) 
    reviewer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.OPEN)
    priority: Mapped[TaskPriority] = mapped_column(Enum(TaskPriority), default=TaskPriority.MEDIUM)
    
    task_type: Mapped[TaskType] = mapped_column(
        Enum(TaskType), 
        default=TaskType.DRAFTING,
        nullable=False
    )
    
    tag: Mapped[Optional[TaskTag]] = mapped_column(Enum(TaskTag), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(UnicodeText, nullable=True)
    attachment_url: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list, nullable=True)
    
    source_type: Mapped[Optional[str]] = mapped_column(String(50))
    ai_reasoning: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # [NEW] Thêm ngày tạo
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # [NEW] Thêm cột này để lưu ID người tạo task
    created_by: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)

    # [MỚI] Thêm cột này để lưu bản nháp html nhân viên đang soạn
    draft_content: Mapped[Optional[str]] = mapped_column(UnicodeText, nullable=True) 

    # Relationships
    # Relationship để truy vấn ngược lại info người tạo
    creator: Mapped["User"] = relationship(foreign_keys=[created_by])
    project: Mapped["BiddingProject"] = relationship(back_populates="tasks")
    assignments: Mapped[List["TaskAssignment"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    parent: Mapped[Optional["BiddingTask"]] = relationship(remote_side=[id], back_populates="sub_tasks")
    sub_tasks: Mapped[List["BiddingTask"]] = relationship(back_populates="parent", cascade="all, delete-orphan")
    comments: Mapped[List["TaskComment"]] = relationship(
        back_populates="task", 
        cascade="all, delete-orphan",
        order_by="TaskComment.created_at.asc()"
    )

    assignee: Mapped[Optional["User"]] = relationship(foreign_keys=[assignee_id])
    reviewer: Mapped[Optional["User"]] = relationship(foreign_keys=[reviewer_id])
    template: Mapped[Optional["BiddingTaskTemplate"]] = relationship()
    
    @property
    def assigned_unit_ids_list(self):
        return [
            assign.assigned_unit_id 
            for assign in self.assignments 
            if assign.assigned_unit_id is not None
        ]
        
    @property
    def assigned_unit_id(self):
        if self.assignments:
            for assign in self.assignments:
                if assign.assigned_unit_id:
                    return assign.assigned_unit_id
        return None
    
    @property
    def project_name(self):
        return self.project.name if self.project else None

# ==========================================
# [NEW] BẢNG MỚI: TaskComment (Trao đổi)
# ==========================================
class TaskComment(Base):
    __tablename__ = "task_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("bidding_task.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("task_comments.id"), nullable=True)
    
    content: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    task: Mapped["BiddingTask"] = relationship(back_populates="comments")
    author: Mapped["User"] = relationship(foreign_keys=[user_id])
    
    parent: Mapped[Optional["TaskComment"]] = relationship(remote_side=[id], back_populates="replies")
    replies: Mapped[List["TaskComment"]] = relationship(back_populates="parent", cascade="all, delete-orphan")

# ==========================================
# 4. PHÂN HỆ BẢO MẬT & ABAC (SECURITY POLICIES)
# ==========================================

class AbacAttribute(Base):
    __tablename__ = "attributes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attr_key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    attr_type: Mapped[AttributeType] = mapped_column(Enum(AttributeType), default=AttributeType.STRING, nullable=False)
    source_table: Mapped[Optional[str]] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Unicode(255))
    mapping_path: Mapped[Optional[str]] = mapped_column(String)


class AbacPolicy(Base):
    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(UnicodeText)
    target_resource: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    action: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    effect: Mapped[PolicyEffect] = mapped_column(Enum(PolicyEffect), default=PolicyEffect.ALLOW, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    condition_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime,server_default=func.now(), onupdate=func.now())
    
# ==========================================
# 5. PHÂN HỆ YÊU CẦU GÓI THẦU (REQUIREMENTS)
# ==========================================

class BiddingReqFinancialAdmin(Base):
    __tablename__ = "bidding_req_financial_admin"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hsmt_id: Mapped[int] = mapped_column(ForeignKey("bidding_packages.hsmt_id"), unique=True, nullable=False)

    # === MỤC 2: THỦ TỤC & BẢO ĐẢM ===
    bid_validity_days: Mapped[Optional[int]] = mapped_column(Integer)                
    bid_security_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))    
    bid_security_duration: Mapped[Optional[int]] = mapped_column(Integer)            
    submission_fee: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))        
    contract_duration_text: Mapped[Optional[str]] = mapped_column(Unicode(255))      

    # === MỤC 3: TÀI CHÍNH ===
    req_revenue_avg: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))       
    req_working_capital: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))   

    # === MỤC 3: HỢP ĐỒNG TƯƠNG TỰ ===
    req_similar_contract_qty: Mapped[Optional[int]] = mapped_column(Integer)         
    req_similar_contract_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2)) 
    req_similar_contract_desc: Mapped[Optional[str]] = mapped_column(UnicodeText)    

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    package: Mapped["BiddingPackage"] = relationship(back_populates="financial_req")


class BiddingReqPersonnel(Base):
    __tablename__ = "bidding_req_personnel"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hsmt_id: Mapped[int] = mapped_column(ForeignKey("bidding_packages.hsmt_id"), nullable=False)

    stt: Mapped[Optional[int]] = mapped_column(Integer)                              
    position_name: Mapped[Optional[str]] = mapped_column(Unicode(255))               
    quantity: Mapped[Optional[int]] = mapped_column(Integer)                         

    min_exp_years: Mapped[Optional[int]] = mapped_column(Integer)                    
    qualification_req: Mapped[Optional[str]] = mapped_column(UnicodeText)            
    similar_project_exp: Mapped[Optional[int]] = mapped_column(Integer)              

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    package: Mapped["BiddingPackage"] = relationship(back_populates="personnel_reqs")


class BiddingReqEquipment(Base):
    __tablename__ = "bidding_req_equipment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hsmt_id: Mapped[int] = mapped_column(ForeignKey("bidding_packages.hsmt_id"), nullable=False)

    stt: Mapped[Optional[int]] = mapped_column(Integer)
    equipment_name: Mapped[Optional[str]] = mapped_column(Unicode(255))              
    quantity: Mapped[Optional[int]] = mapped_column(Integer)                         
    specifications: Mapped[Optional[str]] = mapped_column(UnicodeText)               

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    package: Mapped["BiddingPackage"] = relationship(back_populates="equipment_reqs")