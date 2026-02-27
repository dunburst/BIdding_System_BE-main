import enum

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
    
# 1. Định nghĩa các hành động có thể xảy ra
class TaskAction(str, enum.Enum):
    CREATED = "CREATED"         # Tạo mới / Giao việc
    VIEWED = "VIEWED"           # Đã xem (Cần cân nhắc ghi log này vì sẽ rất nhiều)
    ASSIGNED = "ASSIGNED"       # Phân công lại
    IN_PROGRESS = "IN_PROGRESS" # Bắt đầu làm
    SUBMITTED = "SUBMITTED"     # Nộp bài
    APPROVED = "APPROVED"       # Duyệt
    REJECTED = "REJECTED"       # Từ chối / Yêu cầu sửa
    COMMENTED = "COMMENTED"     # Bình luận
    UPDATED = "UPDATED"         # Cập nhật thông tin khác
    
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
