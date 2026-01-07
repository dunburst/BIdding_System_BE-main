from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from sqlalchemy.orm import Session
from typing import List
import io # Thư viện xử lý stream

from database import get_db
import cruds.user as crud_user
import schemas.user as schemas
from schemas.task import TaskResponse, TaskListResponse
from utils.security import get_current_user
from models import User, UserRole 
import cruds.task as task_crud
from minio_client import minio_handler # Import MinIO Handler

router = APIRouter(
    prefix="/users",
    tags=["User Management (Quản lý người dùng)"]
)

# --- CÁC API VỀ REVIEWER (GIỮ NGUYÊN) ---
@router.get("/reviewer-list", response_model=List[TaskListResponse])
def get_tasks_i_need_to_review(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return task_crud.get_tasks_for_reviewer(db, user=current_user)

@router.get("/reviewer/{task_id}", response_model=TaskResponse)
def get_task_detail_reviewer_view(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return task_crud.get_task_detail_for_reviewer(db, task_id, current_user)

# --- CÁC API QUẢN LÝ USER ---

# 1. Tạo User mới
@router.post("/", response_model=schemas.UserResponse)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud_user.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email đã tồn tại")
    return crud_user.create_user(db=db, user=user)

# 2. Lấy danh sách Users
@router.get("/", response_model=List[schemas.UserResponse])
def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    users = crud_user.get_users(db, skip=skip, limit=limit)
    return users

# 3. Lấy chi tiết User
@router.get("/{user_id}", response_model=schemas.UserResponse)
def read_user(user_id: int, db: Session = Depends(get_db)):
    db_user = crud_user.get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user

# 4. Cập nhật User
@router.put("/{user_id}", response_model=schemas.UserResponse)
def update_user(user_id: int, user_in: schemas.UserUpdate, db: Session = Depends(get_db)):
    db_user = crud_user.update_user(db, user_id=user_id, user_update=user_in)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user

# 5. [ĐÃ CHỈNH SỬA] Upload Avatar vào bucket FILES, thư mục AVATARS
@router.post("/me/avatar", response_model=schemas.UserResponse)
def upload_my_avatar(
    file: UploadFile = File(...), 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user) # Tự động lấy user từ Token
):
    """
    Upload ảnh đại diện cho user đang đăng nhập.
    - Path MinIO: files/avatars/{user_id}_{filename}
    """
    user_id = current_user.user_id 
    
    # 1. Validate file ảnh
    file_type = file.content_type or "" 
    if not file_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File tải lên phải là hình ảnh (jpg, png, ...)")

    try:
        # 2. Đọc file
        file_content = file.file.read()
        file_stream = io.BytesIO(file_content)
        file_size = len(file_content)
        
        # 3. Đặt tên file: avatars/{user_id}_{filename}
        # Folder 'avatars' sẽ nằm trong bucket 'files'
        object_name = f"avatars/{user_id}_{file.filename}"
        
        # 4. Upload lên MinIO (Sử dụng bucket 'files')
        avatar_url = minio_handler.upload_file_obj(
            file_data=file_stream,
            length=file_size,
            object_name=object_name,
            content_type=file_type,
            bucket_name="files"  # <--- CHỐT LẠI LÀ DÙNG BUCKET FILES
        )
        
        if not avatar_url:
             raise HTTPException(status_code=500, detail="Lỗi khi upload ảnh lên MinIO")

        # 5. Cập nhật URL vào Database
        user_update = schemas.UserUpdate(avatar_url=avatar_url)
        updated_user = crud_user.update_user(db, user_id=user_id, user_update=user_update)
        
        return updated_user

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi hệ thống: {str(e)}")

# 6. Xóa User
@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
def delete_user(user_id: int, db: Session = Depends(get_db)):
    result = crud_user.delete_user(db=db, user_id=user_id)
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "Xóa người dùng thành công"}