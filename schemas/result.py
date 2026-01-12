from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from decimal import Decimal

# ==========================================
# 1. CÁC SCHEMA CON (Chi tiết từng phần)
# ==========================================

class WinnerFull(BaseModel):
    id: int
    # Thông tin định danh
    bidder_code: Optional[str] = None
    tax_code: Optional[str] = None
    bidder_name: Optional[str] = None
    role: Optional[str] = None # Tên liên danh
    
    # Thông tin tài chính
    # bid_price: Optional[Decimal] = None       # Giá dự thầu
    # corrected_price: Optional[Decimal] = None # Giá sửa lỗi
    evaluated_price: Optional[Decimal] = None # Giá đánh giá
    winning_price: Optional[Decimal] = None   # Giá trúng thầu
    
    # Thông tin kỹ thuật / Hợp đồng
    technical_score: Optional[str] = None
    # execution_time: Optional[str] = None
    contract_period: Optional[str] = None
    other_content: Optional[str] = None

    class Config:
        from_attributes = True

class FailedBidderFull(BaseModel):
    id: int
    bidder_code: Optional[str] = None
    bidder_name: Optional[str] = None
    tax_code: Optional[str] = None
    joint_venture_name: Optional[str] = None # Tên liên danh (nếu có)
    reason: Optional[str] = None

    class Config:
        from_attributes = True

class ItemFull(BaseModel):
    id: int
    item_name: Optional[str] = None
    model: Optional[str] = None
    brand: Optional[str] = None
    manufacturer: Optional[str] = None
    origin: Optional[str] = None
    
    year_of_manufacture: Optional[str] = None
    technical_specs: Optional[str] = None

    class Config:
        from_attributes = True

# ==========================================
# 2. SCHEMA TỔNG HỢP (FULL RESPONSE)
# ==========================================

class BiddingResultFullResponse(BaseModel):
    id: int
    hsmt_id: int
    
    # --- Thông tin chung ---
    result_status: Optional[str] = None
    posting_date: Optional[datetime] = None
    
    # approved_budget: Optional[Decimal] = None
    package_price: Optional[Decimal] = None
    
    approval_date: Optional[datetime] = None
    approving_agency: Optional[str] = None
    decision_number: Optional[str] = None
    
    # decision_link: Optional[str] = None
    # ehsdt_report_link: Optional[str] = None
    bidding_result_text: Optional[str] = None
    
    created_at: Optional[datetime] = None

    # --- Nested Lists (Danh sách con) ---
    winners: List[WinnerFull] = []
    failed_bidders: List[FailedBidderFull] = []
    items: List[ItemFull] = []

    class Config:
        from_attributes = True
# --- 1. SCHEMA TÓM TẮT (Cho hàm đầu tiên) ---
class BiddingResultSummaryResponse(BaseModel):
    hsmt_id: int
    bidding_result_text: Optional[str] = None # Kết quả (VD: Có nhà thầu trúng)
    approval_date: Optional[datetime] = None  # Ngày phê duyệt
    
    # Hai trường này ta sẽ tự xử lý logic trong CRUD để gộp dữ liệu
    winner_name: Optional[str] = None         # Tên nhà thầu hoặc Liên danh
    winning_price: Optional[Decimal] = None   # Giá trúng thầu

    class Config:
        from_attributes = True
