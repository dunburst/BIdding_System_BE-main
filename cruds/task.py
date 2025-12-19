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

# --- READ (GET LIST WITH SECURITY) ---
def get_project_tasks_tree(db: Session, project_id: int, user: User):
    """
    Lấy danh sách task của dự án theo dạng cây.
    NHƯNG: Chỉ trả về các nhánh mà User có quyền nhìn thấy (thuộc phòng ban).
    """
    query = select(BiddingTask).where(
        BiddingTask.bidding_project_id == project_id,
        # Chỉ lấy task cha cao nhất (Root tasks), các task con sẽ được load qua relationship
        BiddingTask.parent_task_id == None
    ).options(
        # Eager load để lấy task con và assignments
        joinedload(BiddingTask.assignments),
        joinedload(BiddingTask.sub_tasks).joinedload(BiddingTask.assignments)
    )

    # NẾU KHÔNG PHẢI ADMIN -> ÁP DỤNG BỘ LỌC PHÒNG BAN
    if user.role != UserRole.ADMIN:
        # Logic lọc phức tạp:
        # Ta cần join với bảng TaskAssignment để lọc.
        # Tuy nhiên, nếu lọc thẳng ở Root Task, ta có thể mất các Sub-task mà user được giao 
        # (nếu user không được giao task cha nhưng được giao task con).
        
        # Cách tiếp cận đơn giản và hiệu quả nhất cho API Tree:
        # 1. Lấy toàn bộ cấu trúc (hoặc filter nhẹ).
        # 2. Filter đệ quy bằng Python sau khi query (để xử lý việc ẩn hiện nút cha/con).
        
        # Ở đây tôi demo cách filter bằng SQL Join cho các Task mà User TRỰC TIẾP liên quan
        query = query.join(TaskAssignment, BiddingTask.assignments).where(
            or_(
                TaskAssignment.assigned_unit_id == user.org_unit_id,
                TaskAssignment.assigned_user_id == user.user_id
            )
        )
    
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