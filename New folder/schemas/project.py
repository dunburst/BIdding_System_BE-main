from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime
from models import PackageStatus

# Base Schema: Chứa các field chung
class BiddingProjectBase(BaseModel):
    name: str
    status: Optional[str] = "ACTIVE" # Giá trị mặc định

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

    # Cấu hình để đọc từ ORM
    model_config = ConfigDict(from_attributes=True)
# Response Schema: Dữ liệu trả về cho client
class BiddingProjectResponse(BiddingProjectBase):
    id: int
    host_id: Optional[int] = None
    bid_team_leader_id: Optional[int] = None
    drive_folder_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    packages: List[PackageSimpleSchema] = []

    # Cấu hình để Pydantic đọc được dữ liệu từ SQLAlchemy ORM object
    model_config = ConfigDict(from_attributes=True)