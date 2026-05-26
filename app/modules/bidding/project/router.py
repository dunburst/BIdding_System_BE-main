from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy.orm import Session
from typing import List, Optional
from app.modules.bidding.project.model import BiddingProject
from app.modules.bidding.package.model import BiddingPackage
from app.modules.users.model import User
from app.modules.bidding.task.model import BiddingTask
from app.core.utils.enum import TaskStatus, UserRole
from app.modules.bidding.task.model import TaskAssignment
from app.modules.bidding.project.schema import BiddingProjectDetailResponse, BiddingProjectResponse
from app.core.security import get_current_user
from app.core.permission.abac import check_permission
from app.core.permission.constants import AbacAction
from app.core.permission.permission_service import get_user_allowed_tags_with_name
from app.integrations.google.mcp_drive.service import drive_service
from app.integrations.google.mcp_drive.router import _get_folder_tag
from app.modules.bidding.project.crud import _get_keywords_from_tags
from app.modules.users.schema import UserResponse
from app.modules.bidding.project.schema import ProjectStatusUpdateSchema
# Giả sử bạn có file dependencies để lấy DB session (get_db)
from app.infrastructure.database.database import get_db 
import app.modules.bidding.project.crud as cruds
import app.modules.bidding.project.schema as schemas

router = APIRouter(
    prefix="/bidding-projects",
    tags=["Bidding Projects"]
)

# --- API: TẠO DỰ ÁN ---
@router.post("", response_model=schemas.BiddingProjectResponse)
def create_project(
    project_in: schemas.BiddingProjectCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user) # <--- Lấy người đang login (Người tạo)
):
    # 1. Lấy thông tin gói thầu gốc
    package = db.get(BiddingPackage, project_in.source_package_id)
    if not package:
        raise HTTPException(status_code=404, detail="Gói thầu không tồn tại")
    # ==================================================================
    # [MỚI] CHECK LOGIC: GÓI THẦU ĐÃ CÓ DỰ ÁN CHƯA?
    # ==================================================================
    if package.project_id:
        raise HTTPException(
            status_code=400, 
            detail=f"Gói thầu này đã thuộc về Dự án ID {package.project_id}. Không thể tạo thêm dự án mới."
        )
    # ==================================================================
    
    is_allowed = check_permission(
        db=db,
        user=current_user,
        resource=package,             # Resource context là gói thầu hiện tại
        action=AbacAction.CREATE_PROJECT
    )

    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Truy cập bị từ chối: Bạn không có quyền tạo Dự án từ gói thầu này."
        )

    # 2. Validate: Gói thầu phải được duyệt (có người duyệt) thì mới tạo dự án được
    if not package.nguoi_duyet_id:
         raise HTTPException(
            status_code=400, 
            detail="Gói thầu chưa được Lãnh đạo phê duyệt (GO), chưa có thông tin Host."
        )

    # 3. Tạo Project
    try:
        new_project = BiddingProject(
            name=project_in.name,
            status=project_in.status,
            
            # TỰ ĐỘNG GÁN ID:
            host_id=package.nguoi_duyet_id,       # Người chủ trì = Người đã duyệt gói thầu
            bid_team_leader_id=current_user.user_id # Trưởng nhóm thầu = Người đang tạo dự án
        )
        
        db.add(new_project)
        db.flush() # Để lấy ID dự án

        # Cập nhật ngược lại gói thầu (gán vào dự án)
        package.project_id = new_project.id
        db.add(package)
        # # ====================================================
        # # [MỚI] TỰ ĐỘNG TẠO 6 TASK GỐC (ROOT TASKS)
        # # ====================================================
        # default_tasks_config = [
        #     {
        #         "name": "01. Hồ sơ Pháp lý & Năng lực",
        #         "unit_id": 7  # VD: Phòng Pháp chế / Hành chính
        #     },
        #     {
        #         "name": "02. Hồ sơ Nhân sự",
        #         "unit_id": 4  # VD: Phòng Tổ chức / Nhân sự
        #     },
        #     {
        #         "name": "03. Biện pháp Thi công",
        #         "unit_id": 9  # VD: Phòng Kỹ thuật (như trong ảnh bạn gửi)
        #     },
        #     {
        #         "name": "04. Hồ sơ Tài chính",
        #         "unit_id": 5  # VD: Phòng Tài chính - Kế toán
        #     },
        #     {
        #         "name": "05. Hồ sơ Máy móc thiết bị",
        #         "unit_id": 10  # VD: Phòng Vật tư / Thiết bị
        #     },
        #     {
        #         "name": "06. Hồ sơ Hợp đồng & Thương mại",
        #         "unit_id": 11  # VD: Phòng Kế hoạch / Kinh doanh
        #     }
        # ]

        # # ====================================================
        # # VÒNG LẶP TẠO TASK & PHÂN QUYỀN TỰ ĐỘNG
        # # ====================================================
        # for config in default_tasks_config:
        #     # 1. Tạo Task (Thư mục gốc)
        #     root_task = BiddingTask(
        #         bidding_project_id=new_project.id,
        #         task_name=config["name"],
        #         parent_task_id=None,
        #         status=TaskStatus.OPEN,
        #         is_milestone=True,
                
        #         # Gán người phụ trách chính tạm thời là người tạo dự án
        #         assignee_id=current_user.user_id, 
        #         source_type="SYSTEM_AUTO"
        #     )
        #     db.add(root_task)
        #     db.flush() # Lấy ID của task vừa tạo

        #     # 2. Tạo Assignment (Phân về phòng ban tương ứng)
        #     # Chỉ tạo nếu unit_id hợp lệ (khác None/0)
        #     if config["unit_id"]:
        #         auto_assign = TaskAssignment(
        #             task_id=root_task.id,
                    
        #             # QUAN TRỌNG: Lấy ID phòng từ config map vào đây
        #             assigned_unit_id=config["unit_id"], 
                    
        #             assigned_user_id=None, # Để NULL để cả phòng đều thấy
        #             assignment_type="MAIN",
        #             required_role=None,    # Không yêu cầu role cụ thể, ai trong phòng cũng xem đc
        #             required_min_security=None,
        #             is_accepted=True       # Tự động chấp nhận
        #         )
        #         db.add(auto_assign)

        # # ====================================================
        
        db.commit()
        db.refresh(new_project)
        return new_project
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
# --- API: LẤY DANH SÁCH & TÌM KIẾM ---
@router.get("", response_model=List[schemas.BiddingProjectDetailResponse])
def read_projects(
    skip: int = 0,
    limit: int = 100,
    q: Optional[str] = Query(None, description="Tìm kiếm theo tên dự án"),
    status: Optional[str] = Query(None, description="Lọc theo trạng thái"),
    db: Session = Depends(get_db),
    
    # 1. Lấy thông tin người đang đăng nhập
    current_user: User = Depends(get_current_user) 
):
    """
    Lấy danh sách dự án thầu.
    - Admin: Xem hết.
    - User thường: Chỉ xem dự án mình là Host hoặc Leader.
    """
    projects = cruds.get_projects(
        db=db, 
        skip=skip, 
        limit=limit, 
        search_keyword=q,
        status_filter=status,
        
        # 2. Truyền user xuống CRUD để lọc
        user=current_user 
    )
    # 2. [QUAN TRỌNG] Vòng lặp để tính stats cho TỪNG dự án
    results = []
    
    for project in projects:
        # A. Tính toán thống kê cho dự án này
        # (Lưu ý: Việc gọi hàm này trong vòng lặp có thể gây chậm nếu limit quá lớn)
        stats = cruds.get_project_statistics(db, project.id)
        
        # B. Convert ORM -> Pydantic Basic
        project_base = schemas.BiddingProjectResponse.model_validate(project)
        
        # C. Gộp Basic + Stats -> DetailResponse
        project_detail = schemas.BiddingProjectDetailResponse(
            **project_base.model_dump(),
            stats=stats
        )
        
        results.append(project_detail)
    return results

# --- API: LẤY CHI TIẾT 1 DỰ ÁN (Cũng nên chặn xem chi tiết nếu không phải người của dự án) ---
# --- API: LẤY CHI TIẾT 1 DỰ ÁN ---
@router.get("/{project_id}", response_model=schemas.BiddingProjectResponse)
def read_project(
    project_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Lấy dữ liệu dự án
    db_project = cruds.get_project(db, project_id=project_id)
    if db_project is None:
        raise HTTPException(status_code=404, detail="Bidding Project not found")
    
    # 2. --- CHECK QUYỀN MỞ RỘNG ---
    # Sử dụng hàm check logic mới (bao gồm cả việc check task)
    has_access = cruds.check_user_project_access(db, project_id, current_user)
    
    if not has_access:
        raise HTTPException(
            status_code=403, 
            detail="Bạn không có quyền truy cập dự án này (Không phải thành viên dự án hoặc được giao việc)."
        )
            
    return db_project

# --- API: CẬP NHẬT DỰ ÁN ---
@router.put("/{project_id}", response_model=schemas.BiddingProjectResponse)
def update_project(
    project_id: int, 
    project_in: schemas.BiddingProjectUpdate, 
    db: Session = Depends(get_db)
):
    db_project = cruds.update_project(db, project_id=project_id, project_in=project_in)
    if db_project is None:
        raise HTTPException(status_code=404, detail="Bidding Project not found")
    return db_project

# --- API: XÓA DỰ ÁN ---
@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    success = cruds.delete_project(db, project_id=project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Bidding Project not found")
    return None

# --- API: DỪNG / HỦY DỰ ÁN ---
@router.post("/{project_id}/stop", response_model=schemas.BiddingProjectResponse)
def stop_project(
    project_id: int, 
    reason: str = Query(..., description="Lý do dừng dự án (Bắt buộc)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Chuyển trạng thái dự án từ ĐANG CHẠY sang DỪNG (STOPPED).
    Yêu cầu:
    - User phải có quyền (Chủ trì dự án hoặc Admin).
    - Dự án phải đang ở trạng thái ACTIVE (chưa đóng).
    """
    # 1. Lấy thông tin dự án
    project = cruds.get_project(db, project_id=project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Dự án không tồn tại")

    # 2. Kiểm tra quyền (Chỉ Host hoặc Admin được dừng)
    # Lưu ý: Nếu có ABAC thì thay thế bằng check_permission()
    is_host = (project.host_id == current_user.user_id)
    is_admin = (current_user.role == "ADMIN") # Hoặc role tương ứng
    
    if not (is_host or is_admin):
        raise HTTPException(
            status_code=403, 
            detail="Bạn không có quyền dừng dự án này (Chỉ dành cho Chủ trì)."
        )

    # 3. Kiểm tra trạng thái hợp lệ
    # Giả sử bạn dùng Enum hoặc String cho status. Ví dụ: 'ACTIVE', 'STOPPED', 'CLOSED'
    if project.status != "ACTIVE": 
        raise HTTPException(
            status_code=400, 
            detail=f"Không thể dừng dự án đang ở trạng thái '{project.status}' (Chỉ dừng được dự án đang chạy)"
        )

    # 4. Thực hiện chuyển đổi
    try:
        project.status = "STOPPED"
        # project.stop_reason = reason # Nếu model có cột này thì gán vào
        
        db.commit()
        db.refresh(project)
        return project
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi khi dừng dự án: {str(e)}")

@router.get("/{project_id}/personnel", response_model=List[UserResponse])
def get_project_personnel_list(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Lấy danh sách nhân sự thực hiện dự án.
    - Bao gồm: Trưởng nhóm thầu, Người thực hiện (Assignee), Người phối hợp.
    - Loại trừ: Chủ trì (Host), Người duyệt (Reviewer).
    """
    # 1. Kiểm tra quyền truy cập dự án (Optional: nếu muốn bảo mật kỹ)
    has_access = cruds.check_user_project_access(db, project_id, current_user)
    if not has_access:
         raise HTTPException(status_code=403, detail="Bạn không có quyền truy cập thông tin dự án này.")

    # 2. Gọi hàm CRUD
    users = cruds.get_project_participants(db, project_id)
    
    return users

@router.get("/{project_id}/dashboard", response_model=BiddingProjectDetailResponse)
def get_project_dashboard(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Lấy thông tin chi tiết dự án KÈM THEO các chỉ số thống kê (Dashboard).
    """
    # 1. Lấy thông tin dự án gốc (SQLAlchemy Object)
    project = cruds.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Dự án không tồn tại")

    # 2. Check quyền
    has_access = cruds.check_user_project_access(db, project_id, current_user)
    if not has_access:
        raise HTTPException(status_code=403, detail="Không có quyền truy cập.")

    # 3. Tính toán thống kê (Pydantic Object)
    stats = cruds.get_project_statistics(db, project_id)

    # ==========================================================
    # [FIX LỖI VALIDATION ERROR TẠI ĐÂY]
    # ==========================================================
    
    # Bước A: Chuyển đổi Project ORM sang Pydantic cơ bản (chưa có stats)
    project_base = BiddingProjectResponse.model_validate(project)

    # Bước B: Tạo Response cuối cùng bằng cách gộp dữ liệu
    # **project_base.model_dump(): Bung tất cả các trường cũ (id, name, status...)
    # stats=stats: Gán thêm trường stats mới tính được
    response_data = BiddingProjectDetailResponse(
        **project_base.model_dump(), 
        stats=stats
    )
    
    return response_data
    
@router.get("/folder/{project_id}/me")
def get_project_files_by_user(
    project_id: int = Path(..., title="ID của dự án trong Database"), 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Lấy danh sách file/folder.
    - Nếu là VIP: Lấy root folder bình thường.
    - Nếu là NV thường: Search đệ quy các folder khớp với Tag được cấp quyền.
    """
    
    # --- BƯỚC 1: LẤY THÔNG TIN PROJECT ---
    project = db.query(BiddingProject).filter(BiddingProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dự án ID: {project_id}")
    
    folder_id = project.drive_folder_id
    if not folder_id:
        raise HTTPException(status_code=400, detail="Dự án chưa có thư mục Drive.")

    # --- BƯỚC 2: TÍNH TOÁN QUYỀN (Làm trước để quyết định cách query) ---
    allowed_tags_map = get_user_allowed_tags_with_name(db, current_user, project_id)
    user_clearance = current_user.security_clearance.value 
    
    VIP_ROLES = [UserRole.ADMIN, UserRole.MANAGER, UserRole.BID_MANAGER]
    is_vip = current_user.role in VIP_ROLES

    visible_items = []

    # --- BƯỚC 3: CHIẾN LƯỢC QUERY GOOGLE DRIVE ---
    
    # TRƯỜNG HỢP A: Sếp/Admin -> Xem như cũ (List root folder)
    if is_vip:
        # Lấy tất cả file ở root
        drive_items = drive_service.list_files_in_folder(folder_id)
        
        # Duyệt và format (giữ nguyên logic hiển thị cũ)
        for item in drive_items:
            # Logic map tag/check clearance giống code cũ của bạn
            # ... (Lược bớt để tập trung vào phần thay đổi chính) ...
            # Bạn có thể copy lại đoạn logic vòng lặp for item in all_items cũ vào đây
            pass
            
            # [LƯU Ý]: Nếu bạn muốn Sếp cũng thấy folder con bên trong, 
            # hãy dùng hàm search bên dưới với từ khóa rỗng (lấy hết folder).
            # Nhưng thường Sếp thích nhìn từ Root hơn.

    # TRƯỜNG HỢP B: Nhân viên -> Dùng SEARCH để tìm folder nằm sâu bên trong
    else:
        # [FIX LỖI 1]: Ép kiểu .keys() thành list()
        tag_codes_list = list(allowed_tags_map.keys()) 
        target_keywords = _get_keywords_from_tags(tag_codes_list)

        if target_keywords:
            # Search các FOLDER khớp tên
            found_folders = drive_service.search_folders_by_keywords(folder_id, target_keywords)
            
            for item in found_folders:
                folder_name = item.get('name', '')
                folder_tag = _get_folder_tag(folder_name)
                
                # [FIX LỖI 2]: Kiểm tra folder_tag tồn tại trước khi get từ dict
                granted_project = None
                if folder_tag: 
                    granted_project = allowed_tags_map.get(folder_tag)
                
                # Chỉ lấy nếu có quyền (granted_project không None)
                if granted_project:
                    visible_items.append({
                        "id": item['id'], 
                        "name": folder_name, 
                        "type": "FOLDER",
                        "link": item.get('webViewLink', ''),
                        "access": "GRANTED",
                        "tag": folder_tag,
                        "granted_by_project": granted_project,
                        "parents": item.get('parents') 
                    })
        
        # B.3: (Tùy chọn) Vẫn lấy thêm các File lẻ ở Root nếu User đủ level
        # root_files = drive_service.list_files_in_folder(folder_id)
        # Filter lấy các file (không lấy folder) và check security_level...

    return {
        "project_id": project_id,
        "project_name": project.name,
        "current_folder_id": folder_id,
        "total_items": len(visible_items),
        "data": visible_items
    }
    
@router.patch("/{project_id}/status", response_model=schemas.BiddingProjectResponse)
def change_project_status(
    project_id: int,
    status_in: ProjectStatusUpdateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Thay đổi trạng thái dự án (VD: ACTIVE -> CLOSED).
    Quyền hạn: Chỉ Admin, Manager hoặc Người chủ trì (Host) mới được đổi.
    """
    # 1. Tìm dự án
    project = cruds.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Dự án không tồn tại")

    # 2. Kiểm tra quyền (Authorization)
    # Admin/Manager luôn có quyền
    is_admin_or_manager = current_user.role in [UserRole.ADMIN, UserRole.MANAGER, UserRole.BID_MANAGER]
    # Host của dự án có quyền
    is_host = (project.host_id == current_user.user_id)

    if not (is_admin_or_manager or is_host):
        raise HTTPException(
            status_code=403, 
            detail="Bạn không có quyền thay đổi trạng thái dự án này (Chỉ dành cho Chủ trì hoặc Lãnh đạo)."
        )

    # 3. Cập nhật
    updated_project = cruds.update_project_status(db, project_id, status_in.status)
    
    return updated_project