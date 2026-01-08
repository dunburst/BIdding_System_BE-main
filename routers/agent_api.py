from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from cruds import bidding as crud_bidding
from cruds import bidding_req as crud_req
from pydantic import BaseModel

router = APIRouter(prefix="/agent-interface", tags=["Agent Interface"])

class AgentQueryRequest(BaseModel):
    hsmt_id: int

@router.post("/get-full-package-data")
def get_data_for_agent(payload: AgentQueryRequest, db: Session = Depends(get_db)):
    """
    API này tổng hợp toàn bộ dữ liệu của 1 gói thầu để trả về cho Agent.
    """
    # 1. Lấy thông tin cơ bản
    package = crud_bidding.get_package(db, hsmt_id=payload.hsmt_id)
    if not package:
        return {"found": False, "message": f"Không tìm thấy gói thầu ID {payload.hsmt_id}"}

    # 2. Lấy các yêu cầu chi tiết (Financial, Personnel, Equipment)
    financial = crud_req.get_financial_req_by_hsmt(db, payload.hsmt_id)
    personnel = crud_req.get_personnel_reqs_by_hsmt(db, payload.hsmt_id)
    equipment = crud_req.get_equipment_reqs_by_hsmt(db, payload.hsmt_id)

    # 3. Đóng gói dữ liệu trả về JSON
    return {
        "found": True,
        "package_info": {
            "id": package.hsmt_id,
            "ma_tbmt": package.ma_tbmt,
            "ten_goi_thau": package.ten_goi_thau,
            "trang_thai": package.trang_thai,
            "ngay_dong_thau": str(package.thoi_diem_dong_thau) if package.thoi_diem_dong_thau else "Chưa có"
        },
        "financial_req": {
            "doanh_thu_yeu_cau": float(financial.req_revenue_avg) if financial and financial.req_revenue_avg else 0,
            "nguon_von_luu_dong": float(financial.req_working_capital) if financial and financial.req_working_capital else 0
        },
        "personnel_req": [
            {"vitri": p.position_name, "so_luong": p.quantity, "kn_nam": p.min_exp_years} 
            for p in personnel
        ],
        "equipment_req": [
            {"thiet_bi": e.equipment_name, "so_luong": e.quantity} 
            for e in equipment
        ]
    }