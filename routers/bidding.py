<<<<<<< HEAD
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
=======
# routers/bidding.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from schemas.base import BaseResponse
from schemas.bidding import BiddingPackageResponse, BiddingFileResponse
import cruds.bidding as bidding_crud

router = APIRouter(
    prefix="/bidding-packages",
    tags=["Bidding Packages"]
)

# --- API 1: Get All Bidding Packages ---
@router.get("/", response_model=BaseResponse[List[BiddingPackageResponse]])
def get_all_packages(
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(get_db)
):
    packages = bidding_crud.get_all_bidding_packages(db, skip=skip, limit=limit)
    
    return BaseResponse(
        success=True,
        status=200,
        message="Lấy danh sách gói thầu thành công",
        data=packages
    )

# --- API 2: Get Bidding Package Detail by ID ---
@router.get("/{hsmt_id}", response_model=BaseResponse[BiddingPackageResponse])
def get_package_detail(hsmt_id: int, db: Session = Depends(get_db)):
    package = bidding_crud.get_bidding_package_by_id(db, hsmt_id=hsmt_id)
    
    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy gói thầu với ID {hsmt_id}"
        )
        
    return BaseResponse(
        success=True,
        status=200,
        message="Lấy thông tin gói thầu thành công",
        data=package
    )

# --- API 3: Get Files by Bidding Package ID ---
@router.get("/{hsmt_id}/files", response_model=BaseResponse[List[BiddingFileResponse]])
def get_package_files(hsmt_id: int, db: Session = Depends(get_db)):
    # Kiểm tra xem gói thầu có tồn tại không trước
    package = bidding_crud.get_bidding_package_by_id(db, hsmt_id=hsmt_id)
    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy gói thầu với ID {hsmt_id}"
        )
        
    files = bidding_crud.get_files_by_package_id(db, hsmt_id=hsmt_id)
    
    return BaseResponse(
        success=True,
        status=200,
        message="Lấy danh sách file thành công",
        data=files
    )
>>>>>>> fc5e93d7250bbb543615092398c0269867abee6c
