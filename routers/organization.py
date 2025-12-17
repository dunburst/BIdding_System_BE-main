from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from models import OrganizationalUnit
from database import get_db
import schemas.organization as schemas
import cruds.organization as crud_org

router = APIRouter(
    prefix="/organization",
    tags=["Organization Structure (Cơ cấu tổ chức)"]
)

# API 1: Tạo đơn vị mới
@router.post("/", response_model=schemas.OrganizationalUnitResponse)
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

# API 3: Lấy danh sách phẳng (Dropdown list)
@router.get("/", response_model=List[schemas.OrganizationalUnitResponse])
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