from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.modules.organization.model import OrganizationalUnit
from app.core.utils.enum import UnitType
from app.infrastructure.database.database import get_db
import app.modules.organization.schema as schemas
import app.modules.organization.crud as crud_org
from app.modules.organization.schema import UserOrgResponse
router = APIRouter(
    prefix="/organization",
    tags=["Organization Structure (Cơ cấu tổ chức)"]
)

# API 1: Tạo đơn vị mới
@router.post("", response_model=schemas.OrganizationalUnitResponse)
def create_org_unit(unit: schemas.OrganizationalUnitCreate, db: Session = Depends(get_db)):
    # Check trùng mã (Optional)
    existing = db.query(OrganizationalUnit).filter_by(unit_code=unit.unit_code).first()
    if existing: raise HTTPException(400, "Mã đơn vị đã tồn tại")
    return crud_org.create_unit(db, unit)

# API 2: Lấy danh sách dạng cây (Sơ đồ tổ chức)
# Dùng schema TreeResponse để hiện cả children
@router.get("/tree", response_model=List[schemas.OrganizationalUnitTreeResponse])
def get_org_tree(db: Session = Depends(get_db)):
    """Trả về cấu trúc cây phân cấp (Tập đoàn -> Khối -> Ban...)"""
    return crud_org.get_organization_tree(db)

# --- [NEW API] Lấy danh sách tất cả các Ban ---
@router.get("/boards", response_model=List[schemas.OrganizationalUnitResponse])
def get_all_boards(db: Session = Depends(get_db)):
    """
    Lấy danh sách toàn bộ các Ban (BOARD).
    """
    return crud_org.get_all_boards(db)

# --- [NEW API] Lấy danh sách Phòng trực thuộc 1 Ban ---
@router.get("/boards/{board_id}/departments", response_model=List[schemas.OrganizationalUnitResponse])
def get_departments_of_board(
    board_id: int, 
    db: Session = Depends(get_db)
):
    """
    Lấy danh sách các Phòng (DEPARTMENT) thuộc về một Ban (BOARD) cụ thể.
    """
    # Bước 1: Kiểm tra xem Ban đó có tồn tại không (Optional nhưng nên làm)
    board = crud_org.get_unit(db, unit_id=board_id)
    if not board:
        raise HTTPException(status_code=404, detail="Ban không tồn tại")
    
    # Bước 2: Kiểm tra xem ID đó có đúng là Ban không hay là Khối/Phòng khác? (Optional)
    if board.unit_type != UnitType.BOARD:
        raise HTTPException(status_code=400, detail="ID cung cấp không phải là một Ban")

    # Bước 3: Lấy danh sách phòng
    return crud_org.get_departments_by_board(db, board_id)

# --- [NEW API] Lấy danh sách các Công ty con ---
@router.get("/subsidiaries", response_model=List[schemas.OrganizationalUnitResponse])
def get_all_subsidiaries(db: Session = Depends(get_db)):
    """
    Lấy danh sách toàn bộ các Công ty con (SUBSIDIARY).
    Dùng cho dropdown chọn đơn vị trực thuộc hoặc báo cáo.
    """
    return crud_org.get_all_subsidiaries(db)

# API 3: Lấy danh sách phẳng (Dropdown list)
@router.get("", response_model=List[schemas.OrganizationalUnitResponse])
def read_org_units(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud_org.get_units(db, skip=skip, limit=limit)

# API 4: Lấy chi tiết
@router.get("/{unit_id}", response_model=schemas.OrganizationalUnitResponse)
def read_org_unit(unit_id: int, db: Session = Depends(get_db)):
    db_unit = crud_org.get_unit(db, unit_id)
    if db_unit is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn vị")
    return db_unit

# API 5: Cập nhật
@router.put("/{unit_id}", response_model=schemas.OrganizationalUnitResponse)
def update_org_unit(unit_id: int, unit_in: schemas.OrganizationalUnitUpdate, db: Session = Depends(get_db)):
    db_unit = crud_org.update_unit(db, unit_id, unit_in)
    if db_unit is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn vị để cập nhật")
    return db_unit

# API 6: Xóa
@router.delete("/{unit_id}")
def delete_org_unit(unit_id: int, db: Session = Depends(get_db)):
    success = crud_org.delete_unit(db, unit_id)
    if not success:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn vị hoặc không thể xóa (có thể do ràng buộc khóa ngoại)")
    return {"message": "Đã xóa đơn vị thành công"}

# API 7: Lấy danh sách nhân viên trong phòng ban
@router.get("/{unit_id}/members", response_model=List[UserOrgResponse])
def read_unit_members(
    unit_id: int, 
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(get_db)
):
    # Kiểm tra unit có tồn tại không
    unit = crud_org.get_unit(db, unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail="Đơn vị không tồn tại")
        
    members = crud_org.get_members_by_unit(db, unit_id, skip=skip, limit=limit)
    return members
