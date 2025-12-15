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