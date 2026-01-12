from sqlalchemy.orm import Session, joinedload
from models import User, UserRole
from schemas.user import UserCreate, UserUpdate
from sqlalchemy import select
from utils.security import get_password_hash
from models import OrganizationalUnit

def get_user_by_email(db: Session, email: str):
    """Tìm user trong DB dựa theo email"""
    return db.query(User).filter(User.email == email).first()

def get_users(db: Session, skip: int = 0, limit: int = 100):
    query = (
        select(User)
        .options(
            # Kỹ thuật Nested Eager Loading:
            # 1. Load User.org_unit
            # 2. Từ org_unit đó, load tiếp .parent
            joinedload(User.org_unit).joinedload(OrganizationalUnit.parent)
        )
        .order_by(User.user_id)
        .offset(skip)
        .limit(limit)
    )
    return db.execute(query).scalars().all()

# Lời khuyên: Bạn nên sửa luôn hàm get_user (chi tiết) để nó cũng hiển thị
def get_user(db: Session, user_id: int):
    query = (
        select(User)
        .options(
            joinedload(User.org_unit).joinedload(OrganizationalUnit.parent)
        )
        .where(User.user_id == user_id)
    )
    return db.execute(query).scalar_one_or_none()
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

def delete_user(db: Session, user_id: int):
    # 1. Tìm user theo ID
    db_user = db.query(User).filter(User.user_id == user_id).first()
    
    # 2. Nếu không thấy thì trả về False
    if not db_user:
        return False
    
    # 3. Xóa và lưu thay đổi
    db.delete(db_user)
    db.commit()
    return True