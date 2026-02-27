from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Body
from sqlalchemy.orm import Session
from typing import List
import io # Thư viện xử lý stream

from app.infrastructure.database.database import get_db
import app.modules.users.crud as crud_user
import app.modules.users.schema as schemas
from app.modules.bidding.task.schema import TaskResponse, TaskListResponse
from app.modules.users.schema import UserChangePassword
from app.core.security import get_current_user, verify_password
from app.modules.users.model import User
from app.core.utils.enum import UserRole 
import app.modules.bidding.task.crud as task_crud
from urllib.parse import urlparse, unquote
from app.infrastructure.storage.minio_client import minio_handler # Import MinIO Handler

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
@router.post("", response_model=schemas.UserResponse)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud_user.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email đã tồn tại")
    return crud_user.create_user(db=db, user=user)

# 2. Lấy danh sách Users
@router.get("", response_model=List[schemas.UserResponse])
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
    current_user: User = Depends(get_current_user)
):
    """
    Upload ảnh đại diện. Nếu đã có ảnh cũ thì xóa ảnh cũ trên MinIO trước khi up ảnh mới.
    Bucket: files
    """
    user_id = current_user.user_id 
    
    # 1. Validate file ảnh
    file_type = file.content_type or "" 
    if not file_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File tải lên phải là hình ảnh (jpg, png, ...)")

    try:
        # --- [MỚI] LOGIC XÓA ẢNH CŨ ---
        if current_user.avatar_url:
            try:
                # URL dạng: http://localhost:9000/files/avatars/1_abc.jpg
                # Cần lấy ra: avatars/1_abc.jpg
                
                # Phân tích URL
                parsed_url = urlparse(current_user.avatar_url)
                # parsed_url.path sẽ là: /files/avatars/1_abc.jpg
                
                path_parts = parsed_url.path.lstrip("/").split("/", 1)
                # path_parts sẽ là: ['files', 'avatars/1_abc.jpg']
                
                if len(path_parts) == 2 and path_parts[0] == "files":
                    old_object_name = unquote(path_parts[1]) # decode các ký tự đặc biệt
                    
                    # Gọi hàm xóa
                    minio_handler.delete_file(object_name=old_object_name, bucket_name="files")
            except Exception as e:
                # Nếu xóa lỗi thì chỉ log lại, không chặn user upload ảnh mới
                print(f"Không thể xóa ảnh cũ: {e}")
        # ------------------------------

        # 2. Đọc file mới
        file_content = file.file.read()
        file_stream = io.BytesIO(file_content)
        file_size = len(file_content)
        
        # 3. Đặt tên file mới: avatars/{user_id}_{filename}
        object_name = f"avatars/{user_id}_{file.filename}"
        
        # 4. Upload lên MinIO (Bucket 'files')
        avatar_url = minio_handler.upload_file_obj(
            file_data=file_stream,
            length=file_size,
            object_name=object_name,
            content_type=file_type,
            bucket_name="files" 
        )
        
        if not avatar_url:
             raise HTTPException(status_code=500, detail="Lỗi khi upload ảnh lên MinIO")

        # 5. Cập nhật URL mới vào Database
        user_update = schemas.UserUpdate(avatar_url=avatar_url)
        updated_user = crud_user.update_user(db, user_id=user_id, user_update=user_update)
        
        return updated_user

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi hệ thống: {str(e)}")
    
# [MỚI] API Đổi mật khẩu cho người dùng đang đăng nhập
@router.put("/me/password", status_code=status.HTTP_200_OK)
def change_my_password(
    password_data: schemas.UserChangePassword, # Nhớ import đúng schema mới sửa
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Người dùng tự đổi mật khẩu (phiên bản không cần mật khẩu cũ).
    Chỉ cần Token hợp lệ là được phép đổi.
    """
    
    # 1. Kiểm tra confirm password (nếu Pydantic chưa bắt được, check thêm cho chắc)
    if password_data.new_password != password_data.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mật khẩu xác nhận không khớp"
        )
        
    # 2. Kiểm tra không cho đặt trùng mật khẩu cũ (Tùy chọn)
    # Lưu ý: Cần dùng verify_password để so sánh plain-text mới với hash cũ trong DB
    if verify_password(password_data.new_password, current_user.hashed_password):
         raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mật khẩu mới không được trùng với mật khẩu hiện tại"
        )

    # 3. Gọi CRUD để lưu mật khẩu mới
    crud_user.change_password(db, user_id=current_user.user_id, new_password=password_data.new_password)
    
    return {"message": "Đổi mật khẩu thành công"}

@router.put("/{user_id}/reset-password", dependencies=[Depends(get_current_user)]) 
# Lưu ý: cần thêm check Role Admin ở dependency nếu muốn bảo mật chặt
def admin_reset_password(
    user_id: int, 
    new_password: str = Body(..., embed=True, min_length=6), # Nhận trực tiếp string body
    db: Session = Depends(get_db)
):
    """
    Admin reset mật khẩu cho user khác (không cần mật khẩu cũ).
    """
    updated_user = crud_user.change_password(db, user_id=user_id, new_password=new_password)
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    return {"message": f"Đã reset mật khẩu cho user ID {user_id}"}

# 6. Xóa User
@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
def delete_user(user_id: int, db: Session = Depends(get_db)):
    result = crud_user.delete_user_soft(db=db, user_id=user_id)
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "Xóa người dùng thành công"}