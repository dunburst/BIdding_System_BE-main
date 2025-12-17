from sqlalchemy.orm import Session
from models import User, UserRole
from schemas.user import UserCreate, UserUpdate
from sqlalchemy import select
from utils.security import get_password_hash

def get_user_by_email(db: Session, email: str):
    """Tìm user trong DB dựa theo email"""
    return db.query(User).filter(User.email == email).first()

def get_user(db: Session, user_id: int):
    return db.execute(select(User).where(User.user_id == user_id).order_by(User.user_id)).scalar_one_or_none()

def get_users(db: Session, skip: int = 0, limit: int = 100):
    return db.execute(select(User).order_by(User.user_id).offset(skip).limit(limit)).scalars().all()

# [CẬP NHẬT] Hàm tạo user nhận Schema UserCreate
def create_user(db: Session, user: UserCreate):
    # 1. Hash password
    hashed_password = get_password_hash(user.password)
    
    # 2. Map dữ liệu từ Schema sang Model
    # exclude={"password"} để loại bỏ password thô ra khỏi dict
    db_user = User(
        **user.model_dump(exclude={"password"}), 
        hashed_password=hashed_password
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# [MỚI] Hàm cập nhật thông tin user (Org, Role, Security...)
def update_user(db: Session, user_id: int, user_update: UserUpdate):
    db_user = get_user(db, user_id)
    if not db_user:
        return None
    
    # Lấy những trường có giá trị (loại bỏ None)
    update_data = user_update.model_dump(exclude_unset=True)
    
    for key, value in update_data.items():
        setattr(db_user, key, value)
        
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# Hàm update status riêng lẻ (giữ lại nếu cần dùng nhanh)
def update_user_status(db: Session, user_id: int, status: bool):
    user = get_user(db, user_id)
    if user:
        user.status = status
        db.commit()
        db.refresh(user)
    return user