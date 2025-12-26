from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from typing import List

from database import get_db # Hàm lấy DB session của bạn
from schemas.task import TaskCreate, TaskResponse, TaskUpdate, TaskStatus, TaskCommentCreate, TaskCommentResponse, TaskCommentUpdate
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

@router.post("/{task_id}/attachments", response_model=TaskResponse)
def upload_attachments(
    task_id: int,
    # [THAY ĐỔI] Nhận vào một List files
    files: List[UploadFile] = File(...), 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Upload NHIỀU file đính kèm cho công việc.
    - Files sẽ được lưu vào bucket 'jkancon' trong thư mục tên là ID của Task.
    - Cập nhật danh sách URL vào DB.
    """
    return task_crud.upload_task_attachments(db, task_id, files, current_user)

@router.delete("/{task_id}/attachments", response_model=TaskResponse)
def remove_all_attachments(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    XÓA TẤT CẢ file đính kèm của một Task.
    - Xóa toàn bộ folder {task_id} trên MinIO.
    - Reset danh sách file trong DB về rỗng.
    CẢNH BÁO: Hành động này không thể hoàn tác.
    """
    return task_crud.delete_all_task_attachments(db, task_id, current_user)

@router.delete("/{task_id}/attachments/{filename}", response_model=TaskResponse)
def remove_attachment(
    task_id: int,
    filename: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Xóa file đính kèm của Task.
    - Xóa file trên MinIO (Bucket jkancon).
    - Xóa link khỏi Database.
    User cần truyền đúng tên file (VD: tai_lieu.pdf).
    """
    return task_crud.delete_task_attachment(db, task_id, filename, current_user)

@router.post("/{task_id}/comments", response_model=TaskCommentResponse)
def add_comment_to_task(
    task_id: int,
    comment_in: TaskCommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Thêm bình luận vào công việc.
    Nếu muốn trả lời bình luận khác, truyền 'parent_id'.
    """
    # Gọi hàm create_comment trong crud (giả sử bạn để chung trong task_crud)
    return task_crud.create_comment(db, task_id, comment_in, current_user)

@router.get("/{task_id}/comments", response_model=List[TaskCommentResponse])
def get_task_comments(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Lấy toàn bộ thảo luận của Task dưới dạng cây phân cấp.
    """
    return task_crud.get_task_comments_tree(db, task_id, current_user)

@router.put("/comments/{comment_id}", response_model=TaskCommentResponse)
def update_comment(
    comment_id: int,
    comment_in: TaskCommentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Sửa nội dung bình luận (Chỉ dành cho chính chủ).
    """
    return task_crud.update_comment(db, comment_id, comment_in, current_user)

@router.delete("/comments/{comment_id}", status_code=status.HTTP_200_OK)
def delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Xóa bình luận.
    - User thường: Chỉ xóa được comment của mình.
    - Admin/Manager: Xóa được mọi comment.
    - Lưu ý: Xóa comment cha sẽ xóa luôn các comment trả lời (reply) bên trong.
    """
    return task_crud.delete_comment(db, comment_id, current_user)

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
    Xem danh sách công việc của tôi dưới dạng cây phân cấp.
    Hệ thống sẽ tự động tìm các task cha để hiển thị ngữ cảnh đầy đủ.
    """
    # Check quyền truy cập module
    is_allowed = check_permission(
        db=db, user=current_user, resource="bidding_task", action=AbacAction.LIST
    )
    if not is_allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền.")
    
    # [THAY ĐỔI] Gọi hàm get_my_tasks_as_tree thay vì hàm cũ
    return task_crud.get_my_tasks_as_tree(db, user=current_user)


# --- API: Quản lý xem công việc nhân viên (Cũng cần sửa để code không bị lỗi) ---
@router.get("/user/{target_user_id}", response_model=List[TaskResponse])
def get_user_tasks(
    target_user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # ... (Giữ nguyên phần check quyền Manager) ...
    
    # 1. Phải lấy thông tin User của nhân viên cần xem trước
    target_user = db.get(User, target_user_id)
    if not target_user:
         raise HTTPException(status_code=404, detail="Nhân viên không tồn tại")

    # 2. Truyền object target_user vào hàm crud
    return task_crud.get_my_tasks_as_tree(db, user=target_user)