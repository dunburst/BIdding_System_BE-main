<<<<<<< HEAD
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
=======
# schemas/bidding.py
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from models import PackageStatus

# 1. Schema cho File đính kèm
class BiddingFileResponse(BaseModel):
    file_id: int
    hsmt_id: int
    file_name: str
    file_type: str
    upload_date: Optional[datetime] = None
    file_path: str

    class Config:
        from_attributes = True # Cho phép đọc dữ liệu từ ORM model

# 2. Schema cho Gói thầu (Bidding Package)
class BiddingPackageResponse(BaseModel):
    hsmt_id: int
    ma_tbmt: str
    ten_du_an: Optional[str] = None
    ten_goi_thau: str
    ben_moi_thau: str = "" # Mapping từ field 'chu_dau_tu' nếu cần, hoặc dùng chu_dau_tu
    chu_dau_tu: str
    linh_vuc: str
    hinh_thuc_lua_chon_nha_thau: Optional[str] = None
    trang_thai: PackageStatus
    
    # Các trường thời gian quan trọng
    ngay_dang_tai: Optional[datetime] = None
    thoi_diem_dong_thau: Optional[datetime] = None
    thoi_diem_mo_thau: Optional[datetime] = None
    
    so_tien_dam_bao_du_thau: Optional[Decimal] = None
    
    # Link
    duong_dan_goi_thau: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
