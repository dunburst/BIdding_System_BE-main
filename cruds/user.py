from sqlalchemy.orm import Session, joinedload
from models import User, UserRole
from schemas.user import UserCreate, UserUpdate
from sqlalchemy import select
from utils.security import get_password_hash
from models import OrganizationalUnit
from models import BiddingTask, TaskAssignment

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
    # 1. Tìm user
    db_user = db.query(User).filter(User.user_id == user_id).first()
    if not db_user:
        return False
    
    # 2. Xử lý các Task mà user là Người thực hiện chính (Assignee)
    # -> Yêu cầu: Xóa luôn Task này.
    # Ta query ra list object rồi xóa từng cái để đảm bảo Cascade (xóa sub-task, xóa file...) hoạt động tốt ở mức ORM.
    tasks_assigned = db.query(BiddingTask).filter(BiddingTask.assignee_id == user_id).all()
    for task in tasks_assigned:
        db.delete(task)
        
    # 3. Xử lý bảng phân công phụ (TaskAssignment)
    # -> Yêu cầu: Xóa user khỏi danh sách phối hợp.
    db.query(TaskAssignment).filter(TaskAssignment.assigned_user_id == user_id).delete()
    
    # 4. Xử lý các Task mà user là Người duyệt (Reviewer)
    # -> Yêu cầu: KHÔNG xóa task (vì người khác đang làm), chỉ set reviewer về NULL.
    db.query(BiddingTask).filter(BiddingTask.reviewer_id == user_id).update({BiddingTask.reviewer_id: None})

    # 5. [QUAN TRỌNG] Xử lý trường hợp User là người TẠO task (Created By)
    # Vì cột created_by thường là nullable=False, nếu xóa user sẽ lỗi khóa ngoại.
    # Giải pháp: Xóa luôn các task do user này tạo (nếu logic cho phép) HOẶC user này tạo task nào thì task đó cũng bị xóa theo logic Assignee ở trên.
    # Nếu vẫn còn task do user tạo nhưng giao cho người khác -> Cần xóa nốt hoặc chuyển quyền sở hữu.
    # Ở đây tôi chọn phương án xóa nốt để tránh lỗi IntegrityError (nếu bạn muốn giữ lại thì cần update created_by sang ID của Admin).
    tasks_created = db.query(BiddingTask).filter(BiddingTask.created_by == user_id).all()
    for task in tasks_created:
        db.delete(task)

    # 6. Cuối cùng: Xóa User
    db.delete(db_user)
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