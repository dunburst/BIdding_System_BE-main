from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database import get_db # Hàm lấy DB session của bạn
from schemas.task import TaskCreate, TaskResponse, TaskUpdate, TaskStatus
import cruds.task as task_crud
from models import User , UserRole
from utils.abac import check_permission, AbacAction
from utils.security import get_current_user


router = APIRouter(prefix="/tasks", tags=["Bidding Tasks"])

@router.post("/", response_model=TaskResponse)
def create_new_task(
    task_in: TaskCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Tạo Task mới. 
    Có thể tạo Main Task hoặc Sub-task (thông qua parent_task_id).
    Có thể gán luôn phòng ban (TaskAssignment) trong payload.
    """
    # Có thể thêm check: Chỉ Host dự án hoặc Admin mới được tạo task
    return task_crud.create_task(db, task_in, current_user)

@router.get("/project/{project_id}", response_model=List[TaskResponse])
def get_project_tasks(
    project_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Lấy danh sách task của dự án.
    Hệ thống sẽ TỰ ĐỘNG LỌC: User chỉ nhìn thấy task mà phòng ban mình được giao.
    """
    return task_crud.get_project_tasks_tree(db, project_id, current_user)

@router.get("/{task_id}", response_model=TaskResponse)
def get_task_detail(
    task_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return task_crud.get_task_detail(db, task_id, current_user)

@router.patch("/{task_id}/status")
def update_status(
    task_id: int,
    status: TaskStatus,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Cập nhật trạng thái Task. 
    Chỉ nhân viên thuộc phòng ban được assign mới update được.
    """
    return task_crud.update_task_status(db, task_id, status, current_user)

@router.put("/{task_id}", response_model=TaskResponse)
def update_existing_task(
    task_id: int,
    task_in: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Cập nhật thông tin Task.
    - Nếu gửi kèm 'assignments': Hệ thống sẽ XÓA assignments cũ và TẠO assignments mới.
    - Nếu không gửi 'assignments': Giữ nguyên assignments cũ.
    """
    return task_crud.update_task(db, task_id, task_in, current_user)

@router.delete("/{task_id}", status_code=status.HTTP_200_OK)
def delete_existing_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Xóa Task.
    Lưu ý: Nếu Task có Task con (sub-tasks), chúng cũng sẽ bị xóa theo (nếu DB config cascade).
    """
    return task_crud.delete_task(db, task_id, current_user)

# --- API: Xem công việc của chính mình ---
@router.get("/user/me", response_model=List[TaskResponse])
def get_my_tasks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    User xem danh sách task được giao cho chính mình.
    """
    is_allowed = check_permission(
        db=db,
        user=current_user,
        resource="bidding_task", 
        action=AbacAction.LIST # Hoặc "LIST" nếu bạn chưa định nghĩa Enum
    )

    if not is_allowed:
        # Nếu DB không có policy nào khớp -> Trả về False -> Chặn
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Bạn không có quyền truy cập danh sách công việc."
        )
    
    # -----------------------------------------------
    return task_crud.get_all_tasks_by_user_id(db, target_user_id=current_user.user_id)

# --- API: Quản lý xem công việc nhân viên (Optional) ---
@router.get("/user/{target_user_id}", response_model=List[TaskResponse])
def get_user_tasks(
    target_user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Dành cho Quản lý check việc của nhân viên cụ thể.
    """
    # Check quyền: Chỉ Manager hoặc Admin mới được soi việc người khác
    allowed_roles = [UserRole.ADMIN, UserRole.MANAGER, UserRole.BID_MANAGER]
    
    if current_user.user_id != target_user_id and current_user.role not in allowed_roles:
         raise HTTPException(
             status_code=status.HTTP_403_FORBIDDEN, 
             detail="Bạn không có quyền xem danh sách công việc của người khác."
         )

    return task_crud.get_all_tasks_by_user_id(db, target_user_id=target_user_id)