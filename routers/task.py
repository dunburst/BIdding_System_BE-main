from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database import get_db # Hàm lấy DB session của bạn
from schemas.task import TaskCreate, TaskResponse, TaskUpdate, TaskStatus
import cruds.task as task_crud
from models import User
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