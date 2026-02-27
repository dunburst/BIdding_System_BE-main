from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Optional, List, Any
from datetime import datetime
from app.core.utils.enum import PackageStatus

# Base Schema: Chứa các field chung
class BiddingProjectBase(BaseModel):
    name: str
    status: Optional[str] = "ACTIVE" # Giá trị mặc định
    
class ProjectStatusUpdateSchema(BaseModel):
    status: str = Field(..., description="Trạng thái mới: ACTIVE, CLOSED, PAUSED, CANCELLED")

# Create Schema: Dùng khi tạo mới
class BiddingProjectCreate(BiddingProjectBase):
    source_package_id: int = Field(..., description="ID của gói thầu (hsmt_id) kích hoạt việc tạo dự án")

# Update Schema: Tất cả các field đều optional để update từng phần
class BiddingProjectUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    host_id: Optional[int] = None
    bid_team_leader_id: Optional[int] = None

class PackageSimpleSchema(BaseModel):
    hsmt_id: int
    ma_tbmt: str
    ten_goi_thau: str
    trang_thai: PackageStatus
    ngay_dang_tai: Optional[datetime] = None
    
    # --- [NEW FIELDS] Thêm trực tiếp vào đây ---
    thoi_diem_dong_thau: Optional[datetime] = None
    chu_dau_tu: Optional[str] = None
    linh_vuc: Optional[str] = None
    
    # Lưu ý: DB tên là "dia_diem_thuc_hien_goi_thau", 
    # 2. Dùng serialization_alias="dia_diem" để khi API trả về JSON nó sẽ tự đổi tên thành "dia_diem" cho gọn
    dia_diem_thuc_hien_goi_thau: Optional[str] = Field(default=None, serialization_alias="dia_diem")

    # Cấu hình để đọc từ ORM
    model_config = ConfigDict(from_attributes=True)
# Response Schema: Dữ liệu trả về cho client
class BiddingProjectResponse(BiddingProjectBase):
    id: int
    host_id: Optional[int] = None
    bid_team_leader_id: Optional[int] = None
    # Tên Team Leader vẫn nên để ở đây (vì nó thuộc context quản lý dự án)
    bid_team_leader_name: Optional[str] = None
    drive_folder_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    packages: List[PackageSimpleSchema] = []

    # Cấu hình để Pydantic đọc được dữ liệu từ SQLAlchemy ORM object
    model_config = ConfigDict(from_attributes=True)
    # Validator chỉ cần giữ lại logic lấy tên Team Leader
    @model_validator(mode='before')
    @classmethod
    def get_leader_name(cls, data: Any) -> Any:
        if isinstance(data, dict): return data
        
        if hasattr(data, 'team_leader') and data.team_leader:
            data.bid_team_leader_name = data.team_leader.full_name
        return data
    
# Schema chứa các thông số thống kê
class ProjectStatistics(BaseModel):
    deadline: Optional[datetime] = Field(None, description="Hạn chót (Dựa trên task trễ nhất)")
    progress: float = Field(0.0, description="Tiến độ % (Completed tasks / Total tasks)")
    total_tasks: int = 0
    completed_tasks: int = 0
    participant_count: int = Field(0, description="Tổng số nhân sự tham gia")
    # priority: str = Field("MEDIUM", description="Độ ưu tiên tổng thể (LOW/MEDIUM/HIGH)")
    
# Schema response cuối cùng (Gộp thông tin dự án + Thống kê)
class BiddingProjectDetailResponse(BiddingProjectResponse):
    stats: ProjectStatistics

    model_config = ConfigDict(from_attributes=True)