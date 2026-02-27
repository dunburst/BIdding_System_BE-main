from sqlalchemy.orm import Session, joinedload
from app.modules.users.model import User
from app.core.utils.enum import TaskStatus, UserRole
from app.modules.users.schema import UserCreate, UserUpdate
from sqlalchemy import select
from app.core.security import get_password_hash
from app.modules.organization.model import OrganizationalUnit
from app.modules.bidding.task.model import BiddingTask, TaskAssignment

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

def delete_user_soft(db: Session, user_id: int):
    """
    Xóa mềm: Chỉ vô hiệu hóa tài khoản và gỡ bỏ các trách nhiệm hiện tại.
    Dữ liệu lịch sử và Task cũ vẫn còn nguyên.
    """
    # 1. Tìm user
    db_user = db.query(User).filter(User.user_id == user_id).first()
    if not db_user:
        return False
        
    # 2. Vô hiệu hóa tài khoản
    db_user.status = False  # Giả sử bạn có cột status hoặc is_active
    # (Tùy chọn) Đổi password hoặc token để force logout ngay lập tức
    db_user.hashed_password = "DELETED_USER" 

    # 3. Gỡ bỏ trách nhiệm ở các Task ĐANG CHẠY (Task cũ đã xong thì kệ)
    # 3.1 Gỡ khỏi vị trí Assignee -> Task trở thành OPEN (Vô chủ) để sếp giao người khác
    active_tasks = db.query(BiddingTask).filter(
        BiddingTask.assignee_id == user_id,
        BiddingTask.status.in_([TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS, TaskStatus.PENDING_REVIEW])
    ).all()
    
    for task in active_tasks:
        task.assignee_id = None
        task.status = TaskStatus.OPEN # Reset trạng thái về Open
        # (Optional) Ghi log hệ thống: "User nghỉ việc, hệ thống tự động gỡ task"
    
    # 3.2 Gỡ khỏi vị trí Reviewer
    db.query(BiddingTask).filter(BiddingTask.reviewer_id == user_id).update({BiddingTask.reviewer_id: None})
    
    # 3.3 Xóa khỏi các Assignment phụ
    db.query(TaskAssignment).filter(TaskAssignment.assigned_user_id == user_id).delete()

    # 4. Lưu
    db.commit()
    return True

# [MỚI] Hàm lưu mật khẩu mới vào DB
def change_password(db: Session, user_id: int, new_password: str):
    """
    Hàm này chỉ thực hiện việc hash pass mới và lưu vào DB.
    Việc kiểm tra mật khẩu cũ đúng sai sẽ nằm ở tầng Router/Service.
    """
    db_user = get_user(db, user_id)
    if not db_user:
        return None
    
    # 1. Hash mật khẩu mới
    hashed_password = get_password_hash(new_password)
    
    # 2. Cập nhật
    db_user.hashed_password = hashed_password
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user