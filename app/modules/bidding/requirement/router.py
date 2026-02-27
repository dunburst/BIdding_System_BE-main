from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.infrastructure.database.database import get_db # Hàm get_db session của bạn
from app.modules.bidding.requirement import crud as crud
import app.modules.bidding.requirement.schema as schemas
from app.modules.bidding.requirement import crud as req_service

router = APIRouter(
    prefix="/packages_req",
    tags=["Package Requirements (HSMT Details)"]
)

# ==========================================
# 1. APIs CHO TÀI CHÍNH & THỦ TỤC
# ==========================================
@router.get("/{hsmt_id}/financial", response_model=schemas.FinancialReqRead)
def read_financial_requirement(hsmt_id: int, db: Session = Depends(get_db)):
    """
    Lấy thông tin yêu cầu Tài chính & Thủ tục của gói thầu.
    """
    item = crud.get_financial_req_by_hsmt(db, hsmt_id=hsmt_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Financial requirements not found for this package")
    return item

# ==========================================
# 2. APIs CHO NHÂN SỰ
# ==========================================
@router.get("/{hsmt_id}/personnel", response_model=List[schemas.PersonnelReqRead])
def read_personnel_list(hsmt_id: int, db: Session = Depends(get_db)):
    """
    Lấy danh sách tất cả vị trí nhân sự yêu cầu cho gói thầu.
    """
    return crud.get_personnel_reqs_by_hsmt(db, hsmt_id=hsmt_id)

@router.get("/personnel/{req_id}", response_model=schemas.PersonnelReqRead)
def read_personnel_detail(req_id: int, db: Session = Depends(get_db)):
    """
    Xem chi tiết một yêu cầu nhân sự cụ thể (theo ID dòng).
    """
    item = crud.get_personnel_req_detail(db, req_id=req_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Personnel requirement not found")
    return item

# ==========================================
# 3. APIs CHO THIẾT BỊ
# ==========================================
@router.get("/{hsmt_id}/equipment", response_model=List[schemas.EquipmentReqRead])
def read_equipment_list(hsmt_id: int, db: Session = Depends(get_db)):
    """
    Lấy danh sách tất cả thiết bị yêu cầu cho gói thầu.
    """
    return crud.get_equipment_reqs_by_hsmt(db, hsmt_id=hsmt_id)

@router.get("/equipment/{req_id}", response_model=schemas.EquipmentReqRead)
def read_equipment_detail(req_id: int, db: Session = Depends(get_db)):
    """
    Xem chi tiết một yêu cầu thiết bị cụ thể.
    """
    item = crud.get_equipment_req_detail(db, req_id=req_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Equipment requirement not found")
    return item

@router.get("/{hsmt_id}/full-analysis", response_model=schemas.FullPackageAnalysis)
def read_full_analysis(hsmt_id: int, db: Session = Depends(get_db)):
    # 1. Lấy thông tin gói thầu
    package_info = crud.get_bidding_package_by_id(db, hsmt_id)
    
    if not package_info:
        raise HTTPException(status_code=404, detail="Bidding Package not found")
    return {
        "general_info": package_info,
        "financial": crud.get_financial_req_by_hsmt(db, hsmt_id),
        "personnel": crud.get_personnel_reqs_by_hsmt(db, hsmt_id),
        "equipment": crud.get_equipment_reqs_by_hsmt(db, hsmt_id)
    }
    
# ==========================================
# 4. API HEALTH CHECK (ĐÁNH GIÁ GO / NO GO)
# ==========================================
@router.get("/{hsmt_id}/health-check", response_model=schemas.HealthCheckResponse)
def get_package_health_check(hsmt_id: int, db: Session = Depends(get_db)):
    """
    Đánh giá năng lực công ty so với yêu cầu của gói thầu (Health Check).
    Dữ liệu công ty hiện tại đang được MOCK (fix cứng).
    """
    # Check xem gói thầu có tồn tại không
    package = crud.get_bidding_package_by_id(db, hsmt_id)
    if not package:
        raise HTTPException(status_code=404, detail="Bidding Package not found")
        
    # Chạy logic so sánh
    return req_service.perform_health_check(db, hsmt_id)