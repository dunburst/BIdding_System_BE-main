from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db # Hàm lấy DB session (bạn tự định nghĩa trong database.py)
from schemas import bidding as schemas
from cruds import bidding as crud_bidding
from models import PackageStatus

router = APIRouter(
    prefix="/packages",
    tags=["Bidding Packages"]
)

@router.post("/", response_model=schemas.BiddingPackageResponse)
def create_package(package: schemas.BiddingPackageCreate, db: Session = Depends(get_db)):
    db_package = crud_bidding.get_package_by_ma_tbmt(db, ma_tbmt=package.ma_tbmt)
    if db_package:
        raise HTTPException(status_code=400, detail="Mã TBMT đã tồn tại")
    return crud_bidding.create_package(db=db, package=package)

@router.get("/", response_model=List[schemas.BiddingPackageResponse])
def read_packages(
    skip: int = 0, 
    limit: int = 100, 
    q: Optional[str] = Query(None, description="Tìm kiếm theo tên hoặc mã"),
    status: Optional[PackageStatus] = Query(None, description="Lọc theo trạng thái"),
    db: Session = Depends(get_db)
):
    packages = crud_bidding.get_packages(db, skip=skip, limit=limit, search_query=q, status=status)
    return packages

@router.get("/{hsmt_id}", response_model=schemas.BiddingPackageResponse)
def read_package(hsmt_id: int, db: Session = Depends(get_db)):
    db_package = crud_bidding.get_package(db, hsmt_id=hsmt_id)
    if db_package is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy gói thầu")
    return db_package

@router.put("/{hsmt_id}", response_model=schemas.BiddingPackageResponse)
def update_package(hsmt_id: int, package_in: schemas.BiddingPackageUpdate, db: Session = Depends(get_db)):
    db_package = crud_bidding.update_package(db, hsmt_id, package_in)
    if db_package is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy gói thầu để cập nhật")
    return db_package

@router.delete("/{hsmt_id}")
def delete_package(hsmt_id: int, db: Session = Depends(get_db)):
    db_package = crud_bidding.delete_package(db, hsmt_id)
    if db_package is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy gói thầu")
    return {"message": "Đã xóa thành công"}