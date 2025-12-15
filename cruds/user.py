from sqlalchemy.orm import Session
from models import User, UserRole
from sqlalchemy import select
from utils.security import get_password_hash

def get_user_by_email(db: Session, email: str):
    """Tìm user trong DB dựa theo email"""
    return db.query(User).filter(User.email == email).first()

def get_user(db: Session, user_id: int):
    return db.execute(select(User).where(User.user_id == user_id)).scalar_one_or_none()

def get_users(db: Session, skip: int = 0, limit: int = 100):
    return db.execute(select(User).offset(skip).limit(limit)).scalars().all()

def create_user(db: Session, email: str, password: str, full_name: str, role: UserRole = UserRole.ENGINEER):
    # Hash password trước khi lưu
    hashed_password = get_password_hash(password) 
    
    db_user = User(
        email=email,
        hashed_password=hashed_password,
        full_name=full_name,
        role=role,
        status=True
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def update_user_status(db: Session, user_id: int, status: bool):
    user = get_user(db, user_id)
    if user:
        user.status = status
        db.commit()
        db.refresh(user)
    return user