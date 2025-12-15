from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from models import PackageStatus, TaskStatus

# --- Bidding Package Schemas ---
class BiddingPackageBase(BaseModel):
    ma_tbmt: str
    phien_ban_thay_doi: Optional[str] = "00"
    ten_goi_thau: str
    ben_moi_thau: Optional[str] = None # Mapping từ chu_dau_tu
    linh_vuc: str
    trang_thai: PackageStatus = PackageStatus.NEW
    # ... Thêm các trường khác nếu cần thiết (rút gọn cho ngắn gọn)
    so_tien_dam_bao_du_thau: Optional[Decimal] = None
    thoi_diem_dong_thau: Optional[datetime] = None

class BiddingPackageCreate(BiddingPackageBase):
    pass

class BiddingPackageUpdate(BaseModel):
    # Cho phép update từng phần
    ten_goi_thau: Optional[str] = None
    trang_thai: Optional[PackageStatus] = None
    so_quyet_dinh_phe_duyet: Optional[str] = None
    # ...

class BiddingPackageResponse(BiddingPackageBase):
    hsmt_id: int
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# --- Task Schemas ---
class TaskBase(BaseModel):
    task_name: str
    hsmt_id: int

class TaskCreate(TaskBase):
    pass

class TaskResponse(TaskBase):
    id: int
    model_config = ConfigDict(from_attributes=True)