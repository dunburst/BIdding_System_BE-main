from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, or_, and_, case
from fastapi import HTTPException, status
from models import BiddingTask, TaskAssignment, User, UserRole, TaskStatus, TaskPriority
from schemas.task import TaskCreate, TaskUpdate
from utils.abac import check_permission, AbacAction

# --- HÀM KIỂM TRA QUYỀN TRUY CẬP (Helper) ---
def check_access_permission(db: Session, task_id: int, user: User) -> bool:
    """
    Kiểm tra quyền truy cập chi tiết Task.
    - ADMIN, MANAGER, BID_MANAGER: Xem được tất cả (Return True ngay).
    - Nhân viên khác: Chỉ xem được nếu mình là người được giao (Assignee).
    """
    
    # 1. Nhóm Role Quản lý -> Cho phép luôn
    VIP_ROLES = [UserRole.ADMIN, UserRole.MANAGER, UserRole.BID_MANAGER]
    if user.role in VIP_ROLES:
        return True

    # 2. Nhóm Nhân viên -> Phải check DB xem có được giao việc không
    # Logic: User ID phải trùng với assignee_id của Task HOẶC nằm trong bảng assignments
    query = select(BiddingTask.id).outerjoin(TaskAssignment, BiddingTask.assignments).where(
        BiddingTask.id == task_id,
        or_(
            BiddingTask.assignee_id == user.user_id,          # Được gán chính
            TaskAssignment.assigned_user_id == user.user_id   # Được gán phụ
        )
    )
    
    # Chỉ cần tìm thấy 1 dòng kết quả là có quyền
    result = db.execute(query).first()
    return result is not None

# --- CREATE ---
def create_task(db: Session, task_in: TaskCreate, current_user: User):
    # Trường hợp A: Tạo Task Con (Sub-task)
    if task_in.parent_task_id:
        parent_task = db.query(BiddingTask).get(task_in.parent_task_id)
        if not parent_task:
            raise HTTPException(status_code=404, detail="Task cha không tồn tại")

        # Logic: Để tạo task con, user phải có quyền "Giao việc" (ASSIGN_TASK) trên Task Cha
        # Ta truyền parent_task vào làm resource cho ABAC
        is_allowed = check_permission(
            db=db, 
            user=current_user, 
            resource=parent_task, # Check quyền dựa trên context của Task cha
            action=AbacAction.ASSIGN_TASK 
        )
        
        if not is_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="Bạn không có quyền giao việc (tạo sub-task) cho đầu mục này."
            )
            
    # Trường hợp B: Tạo Task Cha (Root Task)
    else:
        # Check quyền tạo project task thông thường (VD: Chỉ Manager được tạo root)
        # Resource ở đây là 'project' hoặc check global action
        is_allowed = check_permission(
            db=db, 
            user=current_user, 
            resource="bidding_task", # Resource name (string)
            action=AbacAction.CREATE
        )
        if not is_allowed:
             raise HTTPException(status_code=403, detail="Bạn không có quyền khởi tạo đầu việc mới.")
    # --- BƯỚC 2: TẠO TASK (Logic cũ giữ nguyên)
    new_task = BiddingTask(
        bidding_project_id=task_in.bidding_project_id,
        parent_task_id=task_in.parent_task_id,
        template_id=task_in.template_id,
        task_name=task_in.task_name,
        deadline=task_in.deadline,
        status=task_in.status,
        priority=task_in.priority,
        task_type=task_in.task_type,
        # <--- THÊM MỚI DÒNG NÀY
        tag=task_in.tag,
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
        raise HTTPException(
            status_code=403, 
            detail="Bạn không có quyền truy cập vào công việc này (Chỉ dành cho người được phân công hoặc Quản lý)."
        )
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

# --- CẬP NHẬT LOGIC LẤY DANH SÁCH (SORTING) ---
def get_all_tasks_by_user_id(db: Session, user: User):
    """
    Lấy công việc của user.
    Sắp xếp: Ưu tiên Cao lên đầu -> Deadline gần nhất -> Deadline xa.
    """
    query = select(BiddingTask).outerjoin(TaskAssignment, BiddingTask.assignments)

    filter_conditions = [
        BiddingTask.assignee_id == user.user_id,
        TaskAssignment.assigned_user_id == user.user_id
    ]

    if user.role == UserRole.SPECIALIST and user.org_unit_id:
         filter_conditions.append(TaskAssignment.assigned_unit_id == user.org_unit_id)

    query = query.where(or_(*filter_conditions)).distinct()

    query = query.options(joinedload(BiddingTask.project))

    tasks = db.execute(query).unique().scalars().all()

    # Priority Order Mapping để sort
    priority_order = {
        TaskPriority.HIGH: 1,
        TaskPriority.MEDIUM: 2,
        TaskPriority.LOW: 3
    }

    # Sắp xếp:
    # 1. Priority (HIGH < MEDIUM < LOW -> theo value 1,2,3)
    # 2. Deadline (None deadline sẽ đẩy xuống cuối hoặc đầu tùy bạn, ở đây để cuối)
    sorted_tasks = sorted(
        tasks, 
        key=lambda x: (
            priority_order.get(x.priority, 2), # Sort theo Priority trước
            x.deadline is None,                # Deadline có hay không
            x.deadline                         # Giá trị Deadline
        )
    )
    return sorted_tasks