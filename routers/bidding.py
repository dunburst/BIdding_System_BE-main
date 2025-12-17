from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi import status as http_status
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from models import PackageStatus, User
from utils.security import get_current_user
from schemas.base import BaseResponse # Giả sử bạn có class bọc response chuẩn
from schemas import bidding as schemas
from cruds import bidding as crud_bidding # Thống nhất dùng tên này
from utils.abac import check_permission, AbacAction

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
    search: Optional[str] = Query(None),
    status: Optional[PackageStatus] = Query(None), 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 2. CHECK QUYỀN
    is_allowed = check_permission(
        db=db,                      # <--- SỬA 2: Thêm tham số db
        user=current_user,
        resource="bidding_package", 
        required_action=AbacAction.LIST 
    )

    if not is_allowed:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN, 
            detail="Bạn không có quyền MANAGER hoặc cấp độ bảo mật không đủ."
        )

    # Logic lấy dữ liệu...
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
def get_package_detail(
    hsmt_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user) # Inject User
):
    # 1. Lấy gói thầu ra trước (để dùng làm resource checking nếu cần logic sâu hơn)
    # Tuy nhiên với rule của bạn chỉ check trên User attribute, ta chưa cần object package cụ thể
    # Nhưng để chuẩn bài ABAC (Resource attribute), ta nên lấy nó ra.
    
    package = crud_bidding.get_package(db, hsmt_id=hsmt_id)
    if not package:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy gói thầu ID {hsmt_id}")

    # 2. CHECK QUYỀN (Action: VIEW)
    # Ở đây tôi truyền object 'package' vào tham số resource
    # Để nếu sau này bạn muốn thêm luật "Chỉ xem gói thầu của phòng mình" thì nó vẫn chạy đúng
    is_allowed = check_permission(
        db=db,                      # <--- SỬA 2: Thêm tham số db
        user=current_user,
        resource=package, # Truyền cả object vào (hoặc string "bidding_package" nếu chỉ check user)
        required_action=AbacAction.VIEW
    )

    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Truy cập bị từ chối: Yêu cầu quyền MANAGER & CONFIDENTIAL."
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