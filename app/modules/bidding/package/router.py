from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from fastapi import status as http_status
from sqlalchemy.orm import Session
from typing import List, Optional
from app.integrations.ai.agent.bid_analysis import analyze_bidding_package
from app.infrastructure.database.database import get_db
from app.modules.bidding.package.model import BiddingPackage
from app.modules.users.model import User
from app.core.utils.enum import PackageStatus
from app.core.security import get_current_user
from app.core.logging import create_audit_log, get_client_ip
from app.core.utils.base_model import BaseResponse # Giả sử bạn có class bọc response chuẩn
from app.modules.bidding.package import schema as schemas
from app.modules.bidding.package import crud as crud_bidding # Thống nhất dùng tên này
from app.core.permission.abac import check_permission, get_allowed_actions
from app.core.permission.constants import AbacAction
from app.modules.bidding.package.schema import CountdownResponse
from app.modules.bidding.result.schema import BiddingResultSummaryResponse, BiddingResultFullResponse
import app.modules.bidding.result.crud as result_crud
from app.modules.bidding.package.crud import calculate_time_remaining, get_closing_time
from math import ceil

router = APIRouter(
    prefix="/bidding-packages",
    tags=["Bidding Packages"]
)

# ==========================================
# 1. TẠO MỚI (CREATE)
# ==========================================
@router.get("/history", response_model=BaseResponse[schemas.ProjectHistoryPagination])
def get_bidding_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1),
    year: Optional[int] = Query(None, description="Lọc theo năm (VD: 2025)"),
    linh_vuc: Optional[str] = Query(None, description="Lọc theo lĩnh vực (VD: Xây lắp)"),
    chu_dau_tu: Optional[str] = Query(None, description="Lọc theo tên Chủ đầu tư"), # <--- [MỚI]
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    API lấy lịch sử năng lực dự án (Portfolio).
    Hỗ trợ lọc: Năm, Lĩnh vực, Chủ đầu tư.
    """
    
    # Truyền tham số chu_dau_tu xuống CRUD
    items, total_count = crud_bidding.get_project_history(
        db, 
        skip=skip, 
        limit=limit,
        year=year,
        linh_vuc=linh_vuc,
        chu_dau_tu=chu_dau_tu # <--- Truyền vào đây
    )

    # Convert sang Schema
    result_items = [schemas.ProjectHistoryResponse.model_validate(item) for item in items]

    # ... (Phần logic phân trang giữ nguyên)
    from math import ceil
    current_page = (skip // limit) + 1
    total_pages = ceil(total_count / limit) if limit > 0 else 0

    pagination_data = schemas.ProjectHistoryPagination(
        items=result_items,
        total=total_count,
        page=current_page,
        size=limit,
        pages=total_pages
    )

    return BaseResponse(
        success=True,
        status=200,
        message="Lấy lịch sử dự án thành công",
        data=pagination_data
    )
    
@router.get("/history/filters", response_model=BaseResponse[schemas.HistoryFilterResponse])
def get_history_filter_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Lấy danh sách các options cho bộ lọc (Năm, Chủ đầu tư)
    từ các dự án đã hoàn thành.
    """
    data = crud_bidding.get_history_filters(db)
    
    return BaseResponse(
        success=True,
        status=200,
        message="Lấy dữ liệu bộ lọc thành công",
        data=data
    )
@router.post("", response_model=BaseResponse[schemas.BiddingPackageResponse])
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
@router.get("", response_model=BaseResponse[schemas.BiddingPackagePagination])
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
            detail="Bạn không có quyền hoặc cấp độ bảo mật không đủ."
        )
        

    # Logic lấy dữ liệu...
    packages, total_count= crud_bidding.get_packages(
        db, 
        skip=skip, 
        limit=limit, 
        search_query=search, 
        status=status 
    )
    
    results = []
    
    for pkg in packages:
        # a. Convert SQLAlchemy Model sang Pydantic Model
        pkg_response = schemas.BiddingPackageResponse.model_validate(pkg)
        
        # b. Tính toán quyền cho riêng gói thầu này
        # (Ví dụ: Gói thầu này đang NEW -> Manager thấy nút Duyệt. 
        #  Gói kia đang CLOSED -> Manager không thấy nút Duyệt)
        pkg_response.allowed_actions = get_allowed_actions(db, current_user, pkg)
        
        results.append(pkg_response)
        
    # Tính toán thông tin phân trang
    current_page = (skip // limit) + 1
    total_pages = ceil(total_count / limit) if limit > 0 else 0
    # Tạo object pagination
    pagination_data = schemas.BiddingPackagePagination(
        items=results,
        total=total_count,
        page=current_page,
        size=limit,
        pages=total_pages
    )
    
    return BaseResponse(
        success=True,
        status=200,
        message="Lấy danh sách gói thầu thành công",
        data=pagination_data
    )
# ==========================================
# 3. LẤY CHI TIẾT (GET DETAIL)
# ==========================================
@router.get("/{hsmt_id}", response_model=BaseResponse[schemas.BiddingPackageResponse])
def get_package_detail(
    hsmt_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Lấy dữ liệu
    package = crud_bidding.get_package(db, hsmt_id=hsmt_id)
    if not package:
        raise HTTPException(status_code=404, detail="Không tìm thấy gói thầu")

    # 2. Check quyền xem (như cũ)
    is_allowed_view = check_permission(
        db=db, user=current_user, resource=package, action=AbacAction.VIEW
    )
    if not is_allowed_view:
        # Xử lý lỗi 403 như cũ...
        raise HTTPException(status_code=403, detail="...")

    # 3. --- MẤU CHỐT: TÍNH TOÁN QUYỀN NÚT BẤM ---
    # Convert SQLAlchemy object sang Pydantic Model thủ công để chèn thêm field
    package_response = schemas.BiddingPackageResponse.model_validate(package)
    
    # Gọi hàm quét quyền và gán vào response
    package_response.allowed_actions = get_allowed_actions(db, current_user, package)

    return BaseResponse(
        success=True, 
        status=200, 
        message="Thành công", 
        data=package_response
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
@router.delete("/cleanup", response_model=BaseResponse)
def cleanup_old_packages(
    req: Request,
    days: int = Query(30, ge=1, description="Xóa các gói thầu NEW/INTERESTED cũ hơn số ngày này."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    API này dùng cho nút 'Dọn dẹp dữ liệu' trên FE.
    Chức năng: Xóa các gói thầu rác (NEW/INTERESTED) đã quá hạn.
    """
    # 1. (Tùy chọn) Check quyền: Chỉ Manager hoặc Admin mới được xóa
    # if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
    #     raise HTTPException(status_code=403, detail="Bạn không có quyền dọn dẹp hệ thống.")

    # 2. Gọi CRUD thực hiện xóa
    deleted_count = crud_bidding.cleanup_old_packages(db, days_threshold=days)
    # --- [LOGGING] ---
    # Chỉ ghi log nếu thực sự có dữ liệu bị xóa
    if deleted_count > 0:
        create_audit_log(
            db=db,
            user=current_user,
            action="CLEANUP", # Action đặc biệt cho việc dọn dẹp
            entity_table=BiddingPackage.__tablename__,
            entity_id=None, # Không có 1 ID cụ thể
            old_value=None, 
            new_value={
                "deleted_count": deleted_count, 
                "threshold_days": days,
                "note": "System cleanup triggered manually"
            },
            ip_address=get_client_ip(req)
        )
    # -----------------
    msg = f"Đã dọn dẹp thành công {deleted_count} gói thầu cũ hơn {days} ngày."
    # # 3. Trả về kết quả
    # if deleted_count > 0:
    #     msg = f"Đã dọn dẹp thành công {deleted_count} gói thầu cũ hơn {days} ngày."
    # else:
    #     msg = "Hệ thống đã sạch, không có gói thầu nào cần xóa."

    return BaseResponse(
        success=True,
        status=200,
        message=msg,
        data={"deleted_count": deleted_count}
    )
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
    req: Request, # <--- [QUAN TRỌNG] Inject Request để lấy IP
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Lấy thông tin gói thầu
    package = crud_bidding.get_package(db, hsmt_id=hsmt_id)
    if not package:
        raise HTTPException(status_code=404, detail="Không tìm thấy gói thầu")
    # [LOGGING] Snapshot trạng thái cũ
    old_status = package.trang_thai.value
    old_approver = package.nguoi_duyet_id
    # Xác định Action: APPROVE_BID hoặc REJECT_BID
    required_action = AbacAction.APPROVE_BID if request.decision == "GO" else AbacAction.REJECT_BID
    
    # Policy SQL: Chỉ MANAGER mới có quyền này. BID_MANAGER sẽ bị chặn.
    is_allowed = check_permission(
        db=db, 
        user=current_user, 
        resource=package, 
        action=required_action
    )

    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Chỉ Lãnh đạo (Giám đốc) mới có quyền phê duyệt/từ chối."
        )
    
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

    # 4. Xử lý chuyển trạng thái & Lưu người duyệt
    new_status = None
    approver_id = None # Biến tạm

    if request.decision == schemas.BidDecision.GO:
        # Gán trực tiếp giá trị Enum vào model
        package.trang_thai = PackageStatus.BIDDING 
        # Lưu ID người duyệt (người đang đăng nhập)
        package.nguoi_duyet_id = current_user.user_id 
        
    elif request.decision == schemas.BidDecision.NO_GO:
        package.trang_thai = PackageStatus.NO_GO
        # Nếu từ chối, có thể không cần lưu người duyệt hoặc tùy nghiệp vụ
        
    else:
        # Thêm nhánh else này để Linter hiểu rằng không bao giờ có trường hợp lọt khe
        raise HTTPException(status_code=400, detail="Quyết định không hợp lệ")

    # 5. Cập nhật vào DB
    db.add(package)
    db.commit()
    db.refresh(package)
    
    # --- [LOGGING] ---
    # Xác định Action là APPROVE (Duyệt) hay REJECT (Không làm)
    action_log = "APPROVE" if request.decision == "GO" else "REJECT"
    create_audit_log(
        db=db,
        user=current_user,
        action=action_log,
        entity_table=BiddingPackage.__tablename__,
        entity_id=hsmt_id,
        old_value={
            "status": old_status,
            "nguoi_duyet_id": old_approver
        },
        new_value={
            "status": package.trang_thai.value,
            "decision": request.decision,
            "nguoi_duyet_id": package.nguoi_duyet_id
        },
        ip_address=get_client_ip(req) # <--- Ghi IP người duyệt
    )
    # -----------------

    return BaseResponse(
        success=True,
        status=200,
        message=f"Đã cập nhật quyết định: {request.decision.value}",
        data=package
    )

@router.post("/{hsmt_id}/analyze-ai")
async def run_ai_analysis(hsmt_id: int, db: Session = Depends(get_db)):
    return await analyze_bidding_package(hsmt_id, db)

# --- API ENDPOINT ---
@router.get("/{hsmt_id}/countdown", response_model=CountdownResponse)
def get_package_countdown(hsmt_id: int, db: Session = Depends(get_db)):
    """
    API nhẹ dành riêng cho Frontend để poll thời gian đếm ngược.
    """
    # 1. Chỉ lấy đúng thời gian từ DB
    deadline = get_closing_time(db, hsmt_id)
    
    # (Optional) Nếu muốn check ID có tồn tại hay không thì check ở đây. 
    # Nhưng nếu deadline = None thì hàm calculate đã trả về "Chưa có lịch" rồi.
    
    # 2. Tính toán
    time_str = calculate_time_remaining(deadline)
    
    # 3. Trả về JSON
    return CountdownResponse(
        hsmt_id=hsmt_id,
        thoi_gian_con_lai=time_str
    )

@router.get("/by-project/{project_id}", response_model=BaseResponse[schemas.BiddingPackageResponse])
def get_package_info_by_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Tìm gói thầu theo Project ID
    package = crud_bidding.get_package_by_project_id(db, project_id=project_id)
    
    if not package:
        # Trường hợp dự án này chưa được gán hoặc chưa tạo gói thầu
        raise HTTPException(
            status_code=404, 
            detail=f"Chưa tìm thấy gói thầu nào liên kết với dự án ID {project_id}"
        )

    # 2. Convert sang Schema response (đã có sẵn hsmt_id)
    pkg_response = schemas.BiddingPackageResponse.model_validate(package)
    
    # 3. Tính toán quyền (nếu cần thiết cho nút bấm)
    pkg_response.allowed_actions = get_allowed_actions(db, current_user, package)

    return BaseResponse(
        success=True,
        status=200,
        message="Lấy thông tin gói thầu theo dự án thành công",
        data=pkg_response
    )
    
# --- API 1: Lấy tóm tắt ---
@router.get("/{hsmt_id}/result-summary", response_model=BiddingResultSummaryResponse)
def get_bidding_result_summary(
    hsmt_id: int, 
    db: Session = Depends(get_db)
):
    """
    Trả về kết quả ngắn gọn: Tên nhà thầu/liên danh, giá trúng, ngày phê duyệt.
    """
    summary = result_crud.get_result_summary(db, hsmt_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Chưa tìm thấy kết quả lựa chọn nhà thầu.")
    return summary

# --- API 2: Lấy chi tiết ---
@router.get("/{hsmt_id}/result-full", response_model=BiddingResultFullResponse)
def get_bidding_result_full(
    hsmt_id: int, 
    db: Session = Depends(get_db)
):
    """
    Trả về TOÀN BỘ thông tin kết quả:
    - Thông tin chung
    - Danh sách trúng thầu
    - Danh sách trượt thầu
    - Danh sách hàng hóa
    """
    return result_crud.get_result_full_detail(db, hsmt_id)