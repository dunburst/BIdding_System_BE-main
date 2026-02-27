from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from enum import Enum

# --- 1. SCHEMAS CHO YÊU CẦU TÀI CHÍNH (1-1) ---
class FinancialReqBase(BaseModel):
    bid_validity_days: Optional[int] = None
    bid_security_value: Optional[Decimal] = None
    bid_security_duration: Optional[int] = None
    submission_fee: Optional[Decimal] = None
    contract_duration_text: Optional[str] = None
    req_revenue_avg: Optional[Decimal] = None
    req_working_capital: Optional[Decimal] = None
    req_similar_contract_qty: Optional[int] = None
    req_similar_contract_value: Optional[Decimal] = None
    req_similar_contract_desc: Optional[str] = None

class FinancialReqRead(FinancialReqBase):
    id: int
    hsmt_id: int
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# --- 2. SCHEMAS CHO YÊU CẦU NHÂN SỰ (1-N) ---
class PersonnelReqBase(BaseModel):
    stt: Optional[int] = None
    position_name: Optional[str] = None
    quantity: Optional[int] = None
    min_exp_years: Optional[int] = None
    qualification_req: Optional[str] = None
    similar_project_exp: Optional[int] = None

class PersonnelReqRead(PersonnelReqBase):
    id: int
    hsmt_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- 3. SCHEMAS CHO YÊU CẦU THIẾT BỊ (1-N) ---
class EquipmentReqBase(BaseModel):
    stt: Optional[int] = None
    equipment_name: Optional[str] = None
    quantity: Optional[int] = None
    specifications: Optional[str] = None

class EquipmentReqRead(EquipmentReqBase):
    id: int
    hsmt_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
    
class PackageGeneralInfo(BaseModel):
    hsmt_id: int
    ma_tbmt: str
    ten_goi_thau: Optional[str] = None
    chu_dau_tu: Optional[str] = None
    chi_tiet_nguon_von: Optional[str] = None
    loai_hop_dong: Optional[str] = None
    dia_diem_thuc_hien_goi_thau: Optional[str] = None
    thoi_gian_thuc_hien_goi_thau: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
    
class FullPackageAnalysis(BaseModel):
    general_info: Optional[PackageGeneralInfo]
    financial: Optional[FinancialReqRead]
    personnel: List[PersonnelReqRead]
    equipment: List[EquipmentReqRead]
    
# --- ENUM CHO TRẠNG THÁI HEALTH CHECK ---
class HealthStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING" # Dành cho các trường hợp thiếu thông tin hoặc cần check tay

# --- SCHEMAS CHO HEALTH CHECK ---
class HealthCheckDetail(BaseModel):
    criteria_name: str      # Tên tiêu chí (VD: Doanh thu bình quân)
    required_value: str     # Yêu cầu của HSMT
    actual_value: str       # Năng lực thực tế của công ty
    status: HealthStatus    # PASS / FAIL / WARNING
    note: Optional[str] = None # Ghi chú thêm nếu cần

class HealthCheckCategory(BaseModel):
    category_name: str      # Tài chính / Nhân sự / Thiết bị
    status: HealthStatus
    details: List[HealthCheckDetail]

class HealthCheckResponse(BaseModel):
    hsmt_id: int
    overall_status: HealthStatus # Tổng thể gói thầu: PASS (GO) hoặc FAIL (NO GO)
    score: float             # Bổ sung trường điểm số (Thang điểm 10)
    categories: List[HealthCheckCategory]