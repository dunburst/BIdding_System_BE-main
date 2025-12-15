from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from models import PackageStatus
from schemas.base import BaseResponse # Giả sử bạn có class bọc response chuẩn
from schemas import bidding as schemas
from cruds import bidding as crud_bidding # Thống nhất dùng tên này

router = APIRouter(
    prefix="/bidding-packages",
    tags=["Bidding Packages"]
)

# ==========================================
# 1. TẠO MỚI (CREATE)
# ==========================================
@router.post("/", response_model=BaseResponse[schemas.BiddingPackageResponse])
def create_package(
    package: schemas.BiddingPackageBase, # Hoặc BiddingPackageCreate nếu bạn tách riêng
    db: Session = Depends(get_db)
):
    # 1. Check trùng mã TBMT
    db_package = crud_bidding.get_package_by_ma_tbmt(db, ma_tbmt=package.ma_tbmt)
    if db_package:
        raise HTTPException(status_code=400, detail=f"Mã TBMT '{package.ma_tbmt}' đã tồn tại")
    
    # 2. Tạo mới
    new_package = crud_bidding.create_package(db=db, package=package)
    
    return BaseResponse(
        success=True,
        status=201,
        message="Tạo gói thầu thành công",
        data=new_package
    )

# ==========================================
# 2. LẤY DANH SÁCH (GET LIST - CÓ FILTER & SEARCH)
# ==========================================
@router.get("/", response_model=BaseResponse[List[schemas.BiddingPackageResponse]])
def get_packages(
    skip: int = Query(0, ge=0), 
    limit: int = Query(100, ge=1),
    search: Optional[str] = Query(None, description="Tìm theo tên gói, mã TBMT, dự án"),
    status: Optional[PackageStatus] = Query(None, description="Lọc theo trạng thái"),
    db: Session = Depends(get_db)
):
    # Gọi hàm CRUD mới đã viết ở bước trước (có order_by, filter, search)
    packages = crud_bidding.get_packages(
        db, 
        skip=skip, 
        limit=limit, 
        search_query=search, 
        status=status
    )
    
    return BaseResponse(
        success=True,
        status=200,
        message="Lấy danh sách gói thầu thành công",
        data=packages
    )

# ==========================================
# 3. LẤY CHI TIẾT (GET DETAIL)
# ==========================================
@router.get("/{hsmt_id}", response_model=BaseResponse[schemas.BiddingPackageResponse])
def get_package_detail(hsmt_id: int, db: Session = Depends(get_db)):
    package = crud_bidding.get_package(db, hsmt_id=hsmt_id)
    
    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy gói thầu ID {hsmt_id}"
        )
        
    return BaseResponse(
        success=True,
        status=200,
        message="Lấy chi tiết gói thầu thành công",
        data=package
    )

# ==========================================
# 4. CẬP NHẬT (UPDATE)
# ==========================================
@router.put("/{hsmt_id}", response_model=BaseResponse[schemas.BiddingPackageResponse])
def update_package(
    hsmt_id: int, 
    package_in: schemas.BiddingPackageUpdate, 
    db: Session = Depends(get_db)
):
    db_package = crud_bidding.update_package(db, hsmt_id, package_in)
    
    if db_package is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy gói thầu để cập nhật")
        
    return BaseResponse(
        success=True,
        status=200,
        message="Cập nhật gói thầu thành công",
        data=db_package
    )

# ==========================================
# 5. XÓA (DELETE)
# ==========================================
@router.delete("/{hsmt_id}", response_model=BaseResponse)
def delete_package(hsmt_id: int, db: Session = Depends(get_db)):
    is_deleted = crud_bidding.delete_package(db, hsmt_id)
    
    if not is_deleted:
        raise HTTPException(status_code=404, detail="Không tìm thấy gói thầu để xóa")
        
    return BaseResponse(
        success=True,
        status=200,
        message="Đã xóa gói thầu thành công",
        data=None
    )

# ==========================================
# 6. LẤY FILE ĐÍNH KÈM
# ==========================================
@router.get("/{hsmt_id}/files", response_model=BaseResponse[List[schemas.BiddingFileResponse]]) # Giả sử bạn có schema này
def get_package_files(hsmt_id: int, db: Session = Depends(get_db)):
    # Check tồn tại trước
    package = crud_bidding.get_package(db, hsmt_id=hsmt_id)
    if not package:
        raise HTTPException(status_code=404, detail="Không tìm thấy gói thầu")
        
    files = crud_bidding.get_files_by_package_id(db, hsmt_id=hsmt_id)
    
    return BaseResponse(
        success=True,
        status=200,
        message="Lấy danh sách file thành công",
        data=files
    )