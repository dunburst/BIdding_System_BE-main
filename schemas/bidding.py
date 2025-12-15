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


# --- Task Schemas ---
class TaskBase(BaseModel):
    task_name: str
    hsmt_id: int

class TaskCreate(TaskBase):
    pass

class TaskResponse(TaskBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# 1. Schema cho File đính kèm
class BiddingFileResponse(BaseModel):
    file_id: int
    hsmt_id: int
    file_name: str
    file_type: str
    upload_date: Optional[datetime] = None
    file_path: str

    class Config:
        from_attributes = True

# 2. Schema cho Gói thầu (Full thông tin theo DB)
class BiddingPackageResponse(BaseModel):
    hsmt_id: int
    ma_tbmt: str
    phien_ban_thay_doi: Optional[str] = "00"
    ngay_dang_tai: Optional[datetime] = None
    
    # Thông tin chung KHLCNT
    ma_khlcnt: str
    phan_loai_khlcnt: Optional[str] = None
    ten_du_an: str
    
    # Thông tin chi tiết gói thầu
    quy_trinh_ap_dung: Optional[str] = None
    ten_goi_thau: str
    chu_dau_tu: str
    chi_tiet_nguon_von: Optional[str] = None
    linh_vuc: str
    hinh_thuc_lua_chon_nha_thau: Optional[str] = None
    loai_hop_dong: Optional[str] = None
    trong_nuoc_hoac_quoc_te: Optional[str] = None
    phuong_thuc_lua_chon_nha_thau: Optional[str] = None
    thoi_gian_thuc_hien_goi_thau: Optional[str] = None
    goi_thau_co_nhieu_phan_lo: Optional[str] = None
    
    # Cách thức dự thầu
    hinh_thuc_du_thau: Optional[str] = None
    dia_diem_phat_hanh_e_hsmt: Optional[str] = None
    chi_phi_nop: Optional[Decimal] = None
    dia_diem_nhan_e_hsdt: Optional[str] = None
    dia_diem_thuc_hien_goi_thau: Optional[str] = None
    
    # Thời gian & Đảm bảo
    thoi_diem_dong_thau: Optional[datetime] = None
    thoi_diem_mo_thau: Optional[datetime] = None
    dia_diem_mo_thau: Optional[str] = None
    hieu_luc_hsdt: Optional[str] = None
    so_tien_dam_bao_du_thau: Optional[Decimal] = None
    hinh_thuc_dam_bao_du_thau: Optional[str] = None
    loai_cong_trinh: Optional[str] = None
    
    # Quyết định phê duyệt
    so_quyet_dinh_phe_duyet: Optional[str] = None
    ngay_phe_duyet: Optional[datetime] = None
    co_quan_ban_hanh_quyet_dinh: Optional[str] = None
    quyet_dinh_phe_duyet: Optional[str] = None
    
    # Metadata & Trạng thái
    duong_dan_goi_thau: Optional[str] = None
    trang_thai: PackageStatus
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True