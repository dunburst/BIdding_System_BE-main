from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, or_, and_
from fastapi import HTTPException, status
from models import BiddingTask, TaskAssignment, User, UserRole, TaskStatus
from schemas.task import TaskCreate, TaskUpdate

# --- HÀM KIỂM TRA QUYỀN TRUY CẬP (Helper) ---
def check_access_permission(db: Session, task_id: int, user: User) -> bool:
    """
    Kiểm tra xem User có quyền thao tác với Task này không.
    Logic: User phải thuộc Unit được assign vào task, hoặc là đích danh User đó.
    Admin/Manager dự án có thể được bypass (tùy nghiệp vụ).
    """
    if user.role == UserRole.ADMIN:
        return True

    # Query kiểm tra tồn tại assignment khớp với user
    statement = select(TaskAssignment).where(
        TaskAssignment.task_id == task_id,
        or_(
            TaskAssignment.assigned_user_id == user.user_id,
            TaskAssignment.assigned_unit_id == user.org_unit_id
        )
    )
    assignment = db.execute(statement).scalar_one_or_none()
    return assignment is not None

# --- CREATE ---
def create_task(db: Session, task_in: TaskCreate, current_user: User):
    # 1. Tạo Task
    real_parent_id = task_in.parent_task_id
    if real_parent_id == 0:
        real_parent_id = None
    new_task = BiddingTask(
        bidding_project_id=task_in.bidding_project_id,
        parent_task_id=real_parent_id,
        template_id=task_in.template_id,
        task_name=task_in.task_name,
        deadline=task_in.deadline,
        status=task_in.status,
        is_milestone=task_in.is_milestone,
        assignee_id=task_in.assignee_id,
        reviewer_id=task_in.reviewer_id,
        source_type=task_in.source_type
    )
    db.add(new_task)
    db.flush() # Để lấy ID của new_task

    # 2. Tạo Assignments (Phân quyền ngay khi tạo)
    if task_in.assignments:
        for assign_in in task_in.assignments:
            final_user_id = assign_in.assigned_user_id
            
            # Nếu trong assignment không chỉ định user cụ thể, 
            # nhưng ở Task cha đã chọn người thực hiện (assignee_id)
            # -> Thì lấy luôn người đó gán vào assignment này.
            if final_user_id is None and task_in.assignee_id is not None:
                final_user_id = task_in.assignee_id
            new_assign = TaskAssignment(
                task_id=new_task.id,
                assigned_unit_id=assign_in.assigned_unit_id,
                assigned_user_id=final_user_id,
                assignment_type=assign_in.assignment_type,
                required_role=assign_in.required_role,
                required_min_security=assign_in.required_min_security,
                is_accepted=True
            )
            db.add(new_assign)
    
    db.commit()
    db.refresh(new_task)
    return new_task

FULL_ACCESS_ROLES = [UserRole.ADMIN, UserRole.MANAGER, UserRole.BID_MANAGER]
# --- READ (GET LIST WITH SECURITY) ---
def get_project_tasks_tree(db: Session, project_id: int, user: User):
    """
    Lấy danh sách task dạng cây.
    - Manager/Bid_Manager: Xem hết.
    - Employee: Chỉ xem task mình được giao (trực tiếp hoặc qua phòng ban).
    """
    
    # 1. Base Query: Lấy các Root Task (Task cha cao nhất) và nạp sẵn con
    query = select(BiddingTask).where(
        BiddingTask.bidding_project_id == project_id,
        BiddingTask.parent_task_id == None
    ).options(
        joinedload(BiddingTask.assignments),
        joinedload(BiddingTask.sub_tasks).joinedload(BiddingTask.assignments)
    )

    # 2. Kiểm tra quyền hạn
    # Nếu user KHÔNG thuộc nhóm quản lý -> Áp dụng bộ lọc
    if user.role not in FULL_ACCESS_ROLES:
        
        # Sử dụng OUTER JOIN để không bị mất task nếu bảng assignment rỗng
        query = query.outerjoin(TaskAssignment, BiddingTask.assignments)
        
        query = query.where(
            or_(
                # 1. Giao đích danh trên bảng Task (Đây là cái bạn đang thiếu)
                BiddingTask.assignee_id == user.user_id,
                
                # 2. Giao đích danh qua bảng phụ Assignment
                TaskAssignment.assigned_user_id == user.user_id,
                
                # 3. Giao cho phòng ban của user
                TaskAssignment.assigned_unit_id == user.org_unit_id
            )
        ).distinct() # Quan trọng: Loại bỏ trùng lặp do phép Join

    # 3. Thực thi query
    result = db.execute(query).unique().scalars().all()
    return result

# --- READ SINGLE ---
def get_task_detail(db: Session, task_id: int, user: User):
    task = db.get(BiddingTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Kiểm tra quyền
    if not check_access_permission(db, task_id, user):
        raise HTTPException(status_code=403, detail="Bạn không thuộc phòng ban được giao task này")
        
    return task

# --- UPDATE ---
def update_task_status(db: Session, task_id: int, status: TaskStatus, user: User):
    task = get_task_detail(db, task_id, user) # Đã check quyền trong hàm này
    
    task.status = status
    # Nếu user nhận task, cập nhật assignee
    if status == TaskStatus.IN_PROGRESS and not task.assignee_id:
        task.assignee_id = user.user_id
        
    db.commit()
    db.refresh(task)
    return task

# --- UPDATE ---
def update_task(db: Session, task_id: int, task_in: TaskUpdate, user: User):
    # 1. Lấy task và check quyền (dùng lại hàm get_task_detail đã có check quyền)
    task = get_task_detail(db, task_id, user)
    
    # 2. Cập nhật các trường thông tin cơ bản (chỉ cập nhật trường khác None)
    update_data = task_in.model_dump(exclude_unset=True)
    
    # Loại bỏ 'assignments' khỏi update_data để xử lý riêng, tránh lỗi update vào bảng Task
    if "assignments" in update_data:
        del update_data["assignments"]

    for field, value in update_data.items():
        setattr(task, field, value)

    # 3. Xử lý cập nhật Assignments (Nếu có gửi kèm)
    if task_in.assignments is not None:
        # A. Xóa toàn bộ phân công cũ của task này
        db.query(TaskAssignment).filter(TaskAssignment.task_id == task.id).delete()
        
        # B. Tạo lại phân công mới
        for assign_in in task_in.assignments:
            final_user_id = assign_in.assigned_user_id
            
            # Logic: Nếu assignment ko có user, lấy assignee_id HIỆN TẠI của task
            if final_user_id is None and task.assignee_id is not None:
                final_user_id = task.assignee_id
                
            new_assign = TaskAssignment(
                task_id=task.id,
                assigned_unit_id=assign_in.assigned_unit_id,
                assigned_user_id=final_user_id,
                assignment_type=assign_in.assignment_type,
                required_role=assign_in.required_role,
                required_min_security=assign_in.required_min_security,
                is_accepted=True
            )
            db.add(new_assign)

    db.commit()
    db.refresh(task)
    return task

# --- DELETE ---
def delete_task(db: Session, task_id: int, user: User):
    # 1. Lấy task và check quyền
    task = get_task_detail(db, task_id, user)
    
    # Lưu ý: Nếu task này có sub-tasks, DB phải cấu hình cascade delete 
    # hoặc bạn phải xóa sub-tasks bằng code trước.
    # Ở đây giả định DB đã cấu hình relationship(cascade="all, delete")
    
    db.delete(task)
    db.commit()
    return {"message": "Task deleted successfully"}