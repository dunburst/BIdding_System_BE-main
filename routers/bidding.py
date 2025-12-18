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
from utils.abac import check_permission
from utils.constants import AbacAction

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
        resource="bidding_packages", 
        action=AbacAction.LIST 
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
        action=AbacAction.VIEW
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
def get_package_files(
    hsmt_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user) 
):
    # Check tồn tại trước
    package = crud_bidding.get_package(db, hsmt_id=hsmt_id)
    if not package:
        raise HTTPException(status_code=404, detail="Không tìm thấy gói thầu")
    
    # 3. ÁP DỤNG ABAC CHECK
    # Check quyền trên chính gói thầu đó (bidding_packages)
    is_allowed = check_permission(
        db=db,
        user=current_user,
        resource=package,       # Object gói thầu lấy từ DB
        action="VIEW"           # Hành động muốn kiểm tra (trùng với DB Policy)
    )

    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền MANAGER (Level 3) hoặc ADMIN (Level 4) để xem tài liệu này."
        )
        
    files = crud_bidding.get_files_by_package_id(db, hsmt_id=hsmt_id)
    
    return BaseResponse(
        success=True,
        status=200,
        message="Lấy danh sách file thành công",
        data=files
    )
    
# ==========================================
# 7. PHÊ DUYỆT / TỪ CHỐI DỰ THẦU (GO / NO-GO)
# ==========================================
@router.put("/{hsmt_id}/decision", response_model=BaseResponse[schemas.BiddingPackageResponse])
def make_bid_decision(
    hsmt_id: int, 
    request: schemas.BidDecisionRequest, # Body chứa GO hoặc NO_GO
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Lấy thông tin gói thầu
    package = crud_bidding.get_package(db, hsmt_id=hsmt_id)
    if not package:
        raise HTTPException(status_code=404, detail="Không tìm thấy gói thầu")
    
    allowed_statuses = [PackageStatus.NEW, PackageStatus.INTERESTED]

    # 2. KIỂM TRA LOGIC NGHIỆP VỤ (State Transition)
    # Chỉ được duyệt khi đang ở trạng thái 'INTERESTED'
    if package.trang_thai not in allowed_statuses:
        raise HTTPException(
            status_code=400, 
            detail=f"Không thể duyệt. Gói thầu đang ở trạng thái '{package.trang_thai.value}', yêu cầu phải là 'NEW' hoặc 'INTERESTED'."
        )

    # 3. CHECK QUYỀN ABAC (Action: APPROVE)
    # Đây là hành động quan trọng, cần quyền APPROVE (thường là Manager/Admin)

    # 4. Xử lý chuyển trạng thái
    new_status = None
    if request.decision == schemas.BidDecision.GO:
        new_status = PackageStatus.BIDDING # Chuyển sang "Đang dự thầu"
    elif request.decision == schemas.BidDecision.NO_GO:
        new_status = PackageStatus.NO_GO   # Chuyển sang "Không dự thầu"

    # 5. Cập nhật vào DB
    # Ta dùng lại hàm update_package nhưng tạo schema update nhỏ gọn
    update_data = schemas.BiddingPackageUpdate(trang_thai=new_status)
    updated_package = crud_bidding.update_package(db, hsmt_id, update_data)
    
    # (Optional) Bạn có thể lưu request.reason vào bảng AuditLog ở đây nếu cần

    return BaseResponse(
        success=True,
        status=200,
        message=f"Đã cập nhật quyết định: {request.decision.value}",
        data=updated_package
    )