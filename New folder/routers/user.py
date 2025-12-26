from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database import get_db
import cruds.user as crud_user
import schemas.user as schemas

router = APIRouter(
    prefix="/users",
    tags=["User Management (Quản lý người dùng)"]
)

# 1. Tạo User mới (Admin tạo)
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

# 4. Cập nhật User (Gán phòng ban, cấp quyền bảo mật...)
@router.put("/{user_id}", response_model=schemas.UserResponse)
def update_user(user_id: int, user_in: schemas.UserUpdate, db: Session = Depends(get_db)):
    db_user = crud_user.update_user(db, user_id=user_id, user_update=user_in)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user

@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
def delete_user(user_id: int, db: Session = Depends(get_db)):
    # Gọi hàm CRUD để xóa
    result = crud_user.delete_user(db=db, user_id=user_id)
    
    if not result:
        # Nếu hàm CRUD trả về False/None nghĩa là không tìm thấy user
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"message": "Xóa người dùng thành công"}