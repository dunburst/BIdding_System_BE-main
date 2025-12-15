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