from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, or_, and_, case
from fastapi import HTTPException, status, UploadFile
from app.modules.bidding.task.model import BiddingTask, TaskAssignment, TaskComment, TaskHistory
from app.modules.organization.model import OrganizationalUnit
from app.modules.users.model import User
from app.core.utils.enum import TaskStatus, TaskPriority, TaskAction
from app.core.utils.enum import AssignmentType, UserRole
from app.modules.bidding.task.schema import TaskCreate, TaskListResponse, TaskUpdate, TaskCommentCreate, TaskCommentUpdate, TaskResponse, TaskAssignmentResponse
from app.core.permission.abac import check_permission, AbacAction
from sqlalchemy.orm import selectinload
import os
import uuid
import shutil
import logging
from typing import Optional, List, Dict, Set # <--- [FIX] Thêm Set
from app.infrastructure.storage.minio_client import minio_handler
from datetime import datetime, timedelta
logger = logging.getLogger(__name__)

# --- HÀM HELPER: XỬ LÝ KẾ THỪA TAG KHI HIỂN THỊ (VIEW ONLY) ---
def _fill_inherited_tags(tasks, parent_tag=None):
    """
    Đệ quy: Nếu task con không có tag, tự động lấy tag của cha để hiển thị.
    """
    for task in tasks:
        # 1. Xác định tag hiệu lực (Ưu tiên của chính nó, nếu không có thì lấy của cha)
        effective_tag = task.tag if task.tag else parent_tag
        
        # 2. Gán tạm vào object (Chỉ trong bộ nhớ, không lưu DB ở hàm này)
        if not task.tag and parent_tag:
            task.tag = parent_tag
        
        # 3. Tiếp tục đệ quy xuống các task con (sub_tasks)
        # Kiểm tra xem list sub_tasks có tồn tại và có dữ liệu không
        if hasattr(task, 'sub_tasks') and task.sub_tasks:
            _fill_inherited_tags(task.sub_tasks, effective_tag)

def _fill_inherited_tags_pydantic(tasks: List[TaskResponse], parent_tag=None):
    """
    Đệ quy tương tự nhưng dành cho danh sách Pydantic Model (get_my_tasks_as_tree)
    """
    for task in tasks:
        effective_tag = task.tag if task.tag else parent_tag
        if not task.tag and parent_tag:
            task.tag = parent_tag
        
        if task.sub_tasks:
            _fill_inherited_tags_pydantic(task.sub_tasks, effective_tag)

def _resolve_tags_for_flat_list(db: Session, tasks: List[TaskResponse]):
    """
    [MỚI] Điền tag cho danh sách task PHẲNG bằng cách truy vấn ngược lên cha/ông.
    Dùng cho API get_tasks_by_assignee_id.
    """
    # 1. Lọc ra những task cần tìm tag (Tag hiện tại là None và có Parent)
    tasks_to_update = [t for t in tasks if not t.tag and t.parent_task_id]
    
    if not tasks_to_update:
        return

    # 2. Thu thập dữ liệu các node cha/ông từ DB
    # Set chứa các ID cần query (ban đầu là parent_id của các task đang thiếu tag)
    # Thêm điều kiện `if t.parent_task_id is not None` ở cuối
    needed_ids: Set[int] = {t.parent_task_id for t in tasks_to_update if t.parent_task_id is not None}
    
    # Dictionary lưu info: ID -> {tag: str, parent_id: int}
    node_info = {} 
    
    # Vòng lặp để query ngược lên các cấp (Ông, Cụ...) đến khi hết hoặc tìm thấy tag
    while needed_ids:
        # Query DB lấy thông tin: id, tag, parent_task_id
        # Chỉ lấy những ID chưa có trong node_info để tránh query lại
        ids_to_fetch = [nid for nid in needed_ids if nid not in node_info]
        if not ids_to_fetch:
            break

        rows = db.query(BiddingTask.id, BiddingTask.tag, BiddingTask.parent_task_id)\
                 .filter(BiddingTask.id.in_(ids_to_fetch)).all()
        
        if not rows:
            break

        # Reset needed_ids để chứa các parent của cấp tiếp theo (nếu cần)
        needed_ids = set()

        for r_id, r_tag, r_pid in rows:
            node_info[r_id] = {'tag': r_tag, 'parent_id': r_pid}
            
            # Logic: Nếu node này chưa có tag và còn có cha -> Cần tìm tiếp cha của nó
            if not r_tag and r_pid:
                # Nếu cha chưa có trong kho thì thêm vào danh sách cần tìm
                if r_pid not in node_info:
                    needed_ids.add(r_pid)

    # 3. Gán Tag cho từng task trong danh sách ban đầu
    for task in tasks_to_update:
        current_pid = task.parent_task_id
        
        # Traverse up (Leo ngược lên cây phả hệ trong memory)
        # Limit loop để tránh infinite loop nếu dữ liệu lỗi (circular)
        for _ in range(10): 
            if current_pid not in node_info:
                break
                
            info = node_info[current_pid]
            
            # Nếu tìm thấy Tag ở cấp này -> Gán và dừng
            if info['tag']:
                task.tag = info['tag'] 
                break
            
            # Nếu chưa thấy -> Leo tiếp lên cấp trên
            current_pid = info['parent_id']
            if not current_pid:
                break

def _map_task_single_level(task_orm) -> TaskListResponse:
    """
    Chuyển đổi 1 Task ORM sang Schema mà KHÔNG đệ quy xuống con.
    Dùng cho các hàm dựng cây thủ công (như get_my_tasks, get_reviewer_tasks)
    nơi mà chúng ta tự code logic ghép cha-con.
    """
    # Pydantic sẽ tự động map các field, bao gồm assignments 
    # (vì query đã load assignments)
    schema = TaskListResponse.model_validate(task_orm)
    
    # Map tên dự án thủ công (nếu Pydantic chưa tự map được qua alias)
    if task_orm.project:
        schema.project_name = task_orm.project.name
        
    # Đảm bảo sub_tasks rỗng để logic bên ngoài tự append vào sau
    schema.sub_tasks = []
    
    return schema

def _map_task_recursive(task_orm) -> TaskListResponse:
    """
    Chuyển đổi Task ORM sang Schema VÀ đệ quy xuống con.
    Dùng cho hàm get_project_tasks_tree (nơi SQL đã load sẵn sub_tasks bằng selectinload).
    """
    # 1. Validate cấp hiện tại
    schema = TaskListResponse.model_validate(task_orm)
    
    if task_orm.project:
        schema.project_name = task_orm.project.name
    
    # 2. Đệ quy cho các task con (sub_tasks)
    # Lưu ý: Cần gọi lại chính hàm này cho các con để đảm bảo con cũng được convert đúng kiểu
    if task_orm.sub_tasks:
        schema.sub_tasks = [_map_task_recursive(sub) for sub in task_orm.sub_tasks]
        # --- [LOGIC MỚI BẮT ĐẦU] ---
        # Kiểm tra: Nếu có con VÀ tất cả con đều COMPLETED
        if schema.sub_tasks and all(sub.status == TaskStatus.COMPLETED for sub in schema.sub_tasks):
            # Gán trạng thái hiển thị của cha thành COMPLETED
            schema.status = TaskStatus.COMPLETED
        # --- [LOGIC MỚI KẾT THÚC] ---
    else:
        schema.sub_tasks = []
        
    return schema

def _sort_tasks_recursive(tasks_list):
    """
    Hàm sắp xếp đệ quy theo Deadline.
    (Null deadline xuống cuối, còn lại tăng dần)
    """
    tasks_list.sort(key=lambda x: (x.deadline is None, x.deadline))
    
    # Đệ quy sắp xếp tiếp các node con
    for task in tasks_list:
        if task.sub_tasks:
            _sort_tasks_recursive(task.sub_tasks)

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
            BiddingTask.assignee_id == user.user_id, 
            BiddingTask.reviewer_id == user.user_id,# Được gán chính
            BiddingTask.created_by == user.user_id,
            TaskAssignment.assigned_user_id == user.user_id,
            TaskAssignment.assigned_unit_id == user.org_unit_id# Được gán phụ
        )
    )
    
    # Chỉ cần tìm thấy 1 dòng kết quả là có quyền
    result = db.execute(query).first()
    return result is not None


# --- HÀM 1: GHI LOG (Dùng nội bộ trong các hàm CRUD khác) ---
def log_task_activity(
    db: Session, 
    task_id: int, 
    actor_id: int, 
    action: TaskAction, 
    old_status: Optional[str] = None, 
    new_status: Optional[str] = None, 
    detail: Optional[str] = None
):
    history = TaskHistory(
        task_id=task_id,
        actor_id=actor_id,
        action=action,
        old_status=old_status,
        new_status=new_status,
        detail=detail
    )
    db.add(history)
    # Lưu ý: Không cần db.commit() ở đây nếu hàm gọi nó sẽ commit sau. 
    # Nếu muốn chắc chắn lưu ngay lập tức thì uncomment dòng dưới.
    # db.commit() 

# --- HÀM 2: LẤY LUỒNG GIAO VIỆC (API bạn cần) ---
def get_task_workflow(db: Session, task_id: int):
    """
    Trả về timeline: Lịch sử quá khứ + 1 Bước dự kiến (Next Step)
    """
    
    # 1. Lấy thông tin Task hiện tại để biết Assignee/Reviewer
    task = db.query(BiddingTask).get(task_id)
    if not task:
        return []

    # 2. Lấy lịch sử quá khứ (Sắp xếp Tăng dần như bạn yêu cầu)
    histories = db.query(TaskHistory)\
        .filter(TaskHistory.task_id == task_id)\
        .order_by(TaskHistory.created_at.desc(), TaskHistory.id.desc())\
        .options(joinedload(TaskHistory.actor))\
        .all()
    
    # Chuyển đổi ORM object sang Dict hoặc Object có thuộc tính is_future = False
    # (Vì chúng ta cần append một object ảo vào list này)
    results = []
    for h in histories:
        # Hack nhẹ: Gán attribute is_future vào object ORM (Python cho phép làm việc này dynamic)
        setattr(h, "is_future", False)
        results.append(h)

    # 3. [LOGIC MỚI] TẠO BƯỚC TIẾP THEO (VIRTUAL STEP)
    future_step = None
    
    # Tình huống 1: Mới tạo hoặc Đã giao -> Người được giao cần "Bắt đầu làm"
    if task.status in [TaskStatus.OPEN, TaskStatus.ASSIGNED]:
        actor = None
        if task.assignee_id:
            actor = db.get(User, task.assignee_id)
        
        future_step = TaskHistory(
            id=-1, # ID ảo
            action=TaskAction.IN_PROGRESS, # Hành động tiếp theo dự kiến
            detail="Đang chờ bắt đầu...",
            actor=actor, # Hiện avatar người được giao
            created_at=None # Chưa diễn ra
        )

    # Tình huống 2: Đang thực hiện -> Người được giao cần "Nộp bài"
    elif task.status == TaskStatus.IN_PROGRESS:
        actor = None
        if task.assignee_id:
            actor = db.get(User, task.assignee_id)

        future_step = TaskHistory(
            id=-1,
            action=TaskAction.SUBMITTED,
            detail="Đang thực hiện & chờ nộp bài...", # Giống dòng "Đang cập nhật..." trong ảnh
            actor=actor,
            created_at=None
        )

    # Tình huống 3: Chờ duyệt -> Reviewer cần "Duyệt/Từ chối"
    elif task.status == TaskStatus.PENDING_REVIEW:
        actor = None
        if task.reviewer_id:
            actor = db.get(User, task.reviewer_id)

        future_step = TaskHistory(
            id=-1,
            action=TaskAction.APPROVED, # Hoặc REJECTED
            detail="Đang chờ duyệt...",
            actor=actor, # Hiện avatar Reviewer
            created_at=None
        )

    # 4. Nếu có bước tiếp theo, gán cờ is_future và thêm vào list
    if future_step:
        setattr(future_step, "is_future", True)
        results.append(future_step)

    return results
    
def should_log_view(db: Session, task_id: int, user_id: int, cooldown_minutes: int = 5) -> bool:
    """
    Kiểm tra xem user có vừa xem task này gần đây không.
    Trả về False nếu user đã xem trong khoảng thời gian cooldown (tránh spam log).
    """
    # Tìm log VIEWED gần nhất của user này tại task này
    last_view = db.query(TaskHistory).filter(
        TaskHistory.task_id == task_id,
        TaskHistory.actor_id == user_id,
        TaskHistory.action == TaskAction.VIEWED
    ).order_by(TaskHistory.created_at.desc()).first()

    if last_view:
        # Tính khoảng cách thời gian
        time_diff = datetime.now() - last_view.created_at
        # Nếu chưa qua 'cooldown_minutes' phút -> Không log nữa
        if time_diff < timedelta(minutes=cooldown_minutes):
            return False
            
    return True
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
            
        # [NEW LOGIC] KẾ THỪA TAG TỪ CHA (Fix Database)
        # Nếu task con không được chỉ định Tag -> Lấy Tag của cha
        if not task_in.tag and parent_task.tag:
            task_in.tag = parent_task.tag

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
    
    # 2. --- [NEW LOGIC] XỬ LÝ STATUS VÀ REVIEWER TỰ ĐỘNG ---
    
    final_status = TaskStatus.OPEN
    final_reviewer_id = task_in.reviewer_id
    
    # CASE A: Gán cho NGƯỜI CỤ THỂ (assignee_id có giá trị)
    if task_in.assignee_id:
        final_status = TaskStatus.ASSIGNED # Status là ASSIGNED
        
        # Nếu chưa chọn reviewer thủ công, hệ thống tự tìm Manager của assignee
        if not final_reviewer_id:
            assignee_user = db.get(User, task_in.assignee_id)
            if assignee_user and assignee_user.org_unit_id:
                # Tìm Unit của người được gán
                org_unit = db.get(OrganizationalUnit, assignee_user.org_unit_id)
                # Lấy manager_id của Unit đó làm reviewer (Trưởng phòng)
                if org_unit and org_unit.manager_id:
                    final_reviewer_id = org_unit.manager_id

    # CASE B: CHỈ Gán cho PHÒNG BAN (assignment có unit, không có assignee_id)
    elif not task_in.assignee_id and task_in.assignments:
        # Kiểm tra xem có assignment nào gán cho Unit không
        unit_assignment = next((a for a in task_in.assignments if a.assigned_unit_id), None)
        
        if unit_assignment:
            final_status = TaskStatus.OPEN # Status là OPEN
            
            # Nếu chưa chọn reviewer thủ công, tìm SPECIALIST trong phòng đó
            if not final_reviewer_id:
                # Tìm 1 user có Role = SPECIALIST trong Unit đó
                specialist_in_unit = db.query(User).filter(
                    User.org_unit_id == unit_assignment.assigned_unit_id,
                    User.role == UserRole.SPECIALIST
                ).first()
                
                if specialist_in_unit:
                    final_reviewer_id = specialist_in_unit.user_id
    # --- BƯỚC 2: TẠO TASK (Logic cũ giữ nguyên)
    new_task = BiddingTask(
        bidding_project_id=task_in.bidding_project_id,
        parent_task_id=task_in.parent_task_id,
        template_id=task_in.template_id,
        task_name=task_in.task_name,
        deadline=task_in.deadline,
        priority=task_in.priority,
        task_type=task_in.task_type,
        # <--- THÊM MỚI DÒNG NÀY
        tag=task_in.tag,
        description=task_in.description,
        assignee_id=task_in.assignee_id,
        status=final_status,
        reviewer_id=final_reviewer_id,
        # [NEW] Lưu người tạo chính là người đang login
        created_by=current_user.user_id,
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
    # Log 1: Tạo mới
    log_task_activity(
        db, task_id=new_task.id, actor_id=current_user.user_id, 
        action=TaskAction.CREATED, 
        new_status=final_status,
        detail=f"Khởi tạo công việc: {new_task.task_name}"
    )

    # Log 2: Nếu có người nhận ngay lập tức -> Log giao việc
    if new_task.assignee_id:
        assignee = db.get(User, new_task.assignee_id)
        name = assignee.full_name if assignee else str(new_task.assignee_id)
        log_task_activity(
            db, task_id=new_task.id, actor_id=current_user.user_id,
            action=TaskAction.ASSIGNED, 
            detail=f"Đã giao trực tiếp cho: {name}"
        )
    db.commit()
    db.refresh(new_task)
    return new_task

FULL_ACCESS_ROLES = [UserRole.ADMIN, UserRole.MANAGER, UserRole.BID_MANAGER]
# --- READ (GET LIST WITH SECURITY) ---
# --- HELPER: ĐỆ QUY CONVERT SANG SCHEMA LITE ---
def _map_to_list_schema(task_orm) -> TaskListResponse:
    """
    Chuyển đổi ORM -> Pydantic Schema (Lite) và xử lý đệ quy cho sub_tasks.
    """
    # 1. Validate các trường cơ bản
    schema = TaskListResponse.model_validate(task_orm)
    
    # 2. Map Project Name (Nếu có)
    if task_orm.project:
        schema.project_name = task_orm.project.name
        
    # 3. Xử lý đệ quy cho Sub-tasks
    # Lưu ý: Vì sub_tasks trong ORM là list các ORM objects, 
    # ta cần map thủ công chúng sang TaskListResponse để đảm bảo đúng kiểu dữ liệu.
    if task_orm.sub_tasks:
        schema.sub_tasks = [_map_to_list_schema(sub) for sub in task_orm.sub_tasks]
    else:
        schema.sub_tasks = []
        
    return schema

# --- UPDATE: GET PROJECT TASKS TREE ---
def get_project_tasks_tree(db: Session, project_id: int, user: User) -> List[TaskListResponse]:
    # 1. Base Query: Root Tasks
    query = select(BiddingTask).where(
        BiddingTask.bidding_project_id == project_id,
        BiddingTask.parent_task_id == None
    )

    # 2. Options: Load Project và Assignments (kèm User/Unit)
    # Dùng selectinload cho assignments để tránh lỗi Cartesian product khi join nhiều bảng 1-N
    query = query.options(
        joinedload(BiddingTask.project),
        
        # Load danh sách phân công, trong đó load tiếp user và unit
        selectinload(BiddingTask.assignments).joinedload(TaskAssignment.user),
        selectinload(BiddingTask.assignments).joinedload(TaskAssignment.unit),
        
        # Load sub-tasks
        selectinload(BiddingTask.sub_tasks)
    )

    # 3. Check quyền (Giữ nguyên)
    if user.role not in FULL_ACCESS_ROLES:
        query = query.outerjoin(TaskAssignment, BiddingTask.assignments)
        query = query.where(
            or_(
                BiddingTask.assignee_id == user.user_id,
                TaskAssignment.assigned_user_id == user.user_id,
                BiddingTask.reviewer_id == user.user_id,
                BiddingTask.created_by == user.user_id,
                TaskAssignment.assigned_unit_id == user.org_unit_id
            )
        ).distinct()

    roots_orm = db.execute(query).unique().scalars().all()

    # 4. Map sang Schema (Dùng helper để đệ quy đúng)
    results = []
    for root in roots_orm:
        results.append(_map_task_recursive(root))

    # 5. Sort
    _sort_tasks_recursive(results)

    return results

# --- READ SINGLE ---
def get_task_detail(db: Session, task_id: int, user: User):
    # Thay vì dùng db.get(), ta dùng select + options để load project
    query = select(BiddingTask).where(BiddingTask.id == task_id).options(
        joinedload(BiddingTask.project),    # <--- Load Project
        joinedload(BiddingTask.assignments),
        joinedload(BiddingTask.assignments).joinedload(TaskAssignment.user),
        joinedload(BiddingTask.assignments).joinedload(TaskAssignment.unit),
        joinedload(BiddingTask.sub_tasks)
    )
    
    task = db.execute(query).unique().scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    # Logic đổi trạng thái từ ASSIGNED -> IN_PROGRESS khi chính chủ vào xem
    old_status = task.status
    if task.status == TaskStatus.ASSIGNED and task.assignee_id == user.user_id:
        task.status = TaskStatus.IN_PROGRESS
        
        # [LOG LOGIC] Tự động bắt đầu
        log_task_activity(
            db, task_id=task.id, actor_id=user.user_id,
            action=TaskAction.IN_PROGRESS,
            old_status=old_status, new_status=TaskStatus.IN_PROGRESS,
            detail="Người được giao đã xem và bắt đầu thực hiện"
        )
        db.commit()
        db.refresh(task) # Refresh để trả về status mới nhất cho FE
    return task
#Cập nhật Status
def update_task_status(db: Session, task_id: int, status_in: TaskStatus, user: User):
    """
    Cập nhật trạng thái Task.
    - Quyền: CHỈ REVIEWER mới được thực hiện.
    - Logic: 
        + Đồng ý (COMPLETED) -> Task thành COMPLETED.
        + Từ chối (REJECTED) -> Task quay về IN_PROGRESS (Yêu cầu làm lại).
    """
    # 1. Lấy thông tin Task
    task = db.query(BiddingTask).get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Công việc không tồn tại")

    # 2. [QUYỀN HẠN] Chỉ cho phép Reviewer
    # Lưu ý: Nếu muốn Admin cũng làm được thì thêm: or user.role == UserRole.ADMIN
    if task.reviewer_id != user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Bạn không phải là người duyệt (Reviewer) của công việc này."
        )

    old_status = task.status
    detail_log = ""
    action_log = TaskAction.UPDATED

    if status_in == TaskStatus.COMPLETED:
        task.status = TaskStatus.COMPLETED
        action_log = TaskAction.APPROVED
        detail_log = "Đã duyệt hoàn thành"
    elif status_in == TaskStatus.REJECTED:
        task.status = TaskStatus.IN_PROGRESS
        action_log = TaskAction.REJECTED
        detail_log = "Đã từ chối duyệt, yêu cầu làm lại"
    else:
        task.status = status_in
        detail_log = f"Cập nhật trạng thái thủ công: {status_in}"

    # [LOG LOGIC]
    log_task_activity(
        db, task_id=task.id, actor_id=user.user_id,
        action=action_log,
        old_status=old_status,
        new_status=task.status,
        detail=detail_log
    )

    db.commit()
    db.refresh(task)
    return task

def submit_task_for_review(db: Session, task_id: int, user: User):
    """
    Nhân viên nộp bài: Chuyển từ IN_PROGRESS -> PENDING_REVIEW.
    """
    # 1. Lấy Task
    task = db.query(BiddingTask).get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Công việc không tồn tại")

    # 2. [QUYỀN HẠN] Chỉ người được giao (Assignee) mới được nộp
    if task.assignee_id != user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Bạn không phải là người thực hiện công việc này nên không thể nộp duyệt."
        )

    # 3. [LOGIC TRẠNG THÁI] Chỉ cho phép khi đang làm
    if task.status != TaskStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Chỉ có thể nộp duyệt khi công việc đang thực hiện (Hiện tại: {task.status})."
        )
        
    old_status = task.status
    # 4. Cập nhật
    task.status = TaskStatus.PENDING_REVIEW
    
    # (Tùy chọn) Lưu thời điểm hoàn thành thực tế nếu cần
    # task.actual_finish_date = func.now()
    # [LOG LOGIC]
    log_task_activity(
        db, task_id=task.id, actor_id=user.user_id,
        action=TaskAction.SUBMITTED,
        old_status=old_status,
        new_status=TaskStatus.PENDING_REVIEW,
        detail="Đã nộp bài và chờ duyệt"
    )

    db.commit()
    db.refresh(task)
    return task
# --- UPDATE ---
def update_task(db: Session, task_id: int, task_in: TaskUpdate, user: User):
    # 1. Lấy task và check quyền (dùng lại hàm get_task_detail đã có check quyền)
    task = db.query(BiddingTask).get(task_id)
    if not task: raise HTTPException(status_code=404, detail="Task not found")
    
    # Snapshot dữ liệu cũ để so sánh
    old_data_summary = f"Deadline: {task.deadline}, Priority: {task.priority}"

    # 2. Cập nhật
    update_data = task_in.model_dump(exclude_unset=True)
    if "assignments" in update_data: del update_data["assignments"]
    
    # 2. Cập nhật các trường thông tin cơ bản (chỉ cập nhật trường khác None)
    update_data = task_in.model_dump(exclude_unset=True)
    
    # Loại bỏ 'assignments' khỏi update_data để xử lý riêng, tránh lỗi update vào bảng Task
    if "assignments" in update_data:
        del update_data["assignments"]

    updated_fields = []
    for field, value in update_data.items():
        if getattr(task, field) != value:
            updated_fields.append(field)
            setattr(task, field, value)

    # 3. Xử lý cập nhật Assignments (Nếu có gửi kèm)
    assignments_changed = False
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
        assignments_changed = True
            
    # [LOG LOGIC]
    log_detail = "Cập nhật thông tin công việc."
    if updated_fields:
        log_detail += f" Các trường thay đổi: {', '.join(updated_fields)}."
    if assignments_changed:
        log_detail += " Có thay đổi phân công (Assignments)."

    log_task_activity(
        db, task_id=task.id, actor_id=user.user_id,
        action=TaskAction.UPDATED,
        detail=log_detail
    )

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

# --- CẬP NHẬT: GET MY TASKS AS TREE (Dùng Schema Rút Gọn) ---
# --- CẬP NHẬT LOGIC LẤY DANH SÁCH (SORTING) ---

def get_my_tasks_as_tree(db: Session, user: User) -> List[TaskResponse]:
    """
    Lấy công việc của tôi nhưng hiển thị theo cấu trúc Cây (Tree).
    Logic:
    1. Tìm tất cả task mà user được giao (Leaf Nodes).
    2. Truy vết ngược lên tìm cha, ông (Ancestors) để có ngữ cảnh.
    3. Ghép lại thành cây trong bộ nhớ.
    """
    # --- BƯỚC 1: LẤY CÁC TASK ĐƯỢC GIAO TRỰC TIẾP ---
    query = select(BiddingTask).outerjoin(TaskAssignment, BiddingTask.assignments)

    filter_conditions = [
        BiddingTask.assignee_id == user.user_id,
        TaskAssignment.assigned_user_id == user.user_id
    ]
    # Nếu là SPECIALIST thì xem được task của phòng ban
    if user.role == UserRole.SPECIALIST and user.org_unit_id:
         filter_conditions.append(TaskAssignment.assigned_unit_id == user.org_unit_id)
    query = query.where(or_(*filter_conditions)).distinct()
    # Eager load project để hiển thị tên dự án
    query = query.options(
        joinedload(BiddingTask.project),
        joinedload(BiddingTask.assignments).joinedload(TaskAssignment.user),
        joinedload(BiddingTask.assignments).joinedload(TaskAssignment.unit)
    )
    # Danh sách task trực tiếp (My Tasks)
    my_tasks = db.execute(query).unique().scalars().all()
    if not my_tasks:
        return []
    # --- BƯỚC 2: TRUY VẾT NGƯỢC TÌM TASK CHA (ANCESTORS) ---
    # Dùng Dict để lưu unique các task (tránh trùng lặp)
    all_related_tasks: Dict[int, BiddingTask] = {t.id: t for t in my_tasks}
    # List chứa các ID cần đi tìm cha
    ids_to_find_parent = [t.id for t in my_tasks if t.parent_task_id is not None]
    while ids_to_find_parent:
        # Query lấy các task cha của danh sách ID hiện tại
        parent_query = select(BiddingTask).where(
            BiddingTask.id.in_(
                select(BiddingTask.parent_task_id).where(BiddingTask.id.in_(ids_to_find_parent))
            )
        ).options(
            joinedload(BiddingTask.project),
            joinedload(BiddingTask.assignments).joinedload(TaskAssignment.user),
            joinedload(BiddingTask.assignments).joinedload(TaskAssignment.unit)
        )
        parents = db.execute(parent_query).unique().scalars().all()
        ids_to_find_parent = [] # Reset để chứa các ID của vòng lặp tiếp theo

        for p in parents:
            if p.id not in all_related_tasks:
                all_related_tasks[p.id] = p
                # Nếu ông này vẫn còn cha, thì thêm vào list để tìm tiếp
                if p.parent_task_id:
                    ids_to_find_parent.append(p.id)
    # --- BƯỚC 3: DỰNG CÂY (IN-MEMORY BUILD) ---    
    # Chuyển đổi ORM Object sang Pydantic Schema để thao tác list `sub_tasks`
    schema_map: Dict[int, TaskResponse] = {}
    # 3.1 Convert sang Schema
    for t_id, t_orm in all_related_tasks.items():
        # Validate model, quan trọng là set sub_tasks = [] để ta tự fill
        t_schema = TaskResponse.model_validate(t_orm)
        t_schema.sub_tasks = []
        # Helper: Gán tên project vào schema (nếu schema có trường project_name)
        if t_orm.project:
            t_schema.project_name = t_orm.project.name     
        schema_map[t_id] = t_schema

    # 3.2 Ráp nối Cha - Con
    roots = []
    for t_id, t_schema in schema_map.items():
        # Nếu có cha và cha cũng nằm trong danh sách đã lấy
        if t_schema.parent_task_id and t_schema.parent_task_id in schema_map:
            parent = schema_map[t_schema.parent_task_id]
            parent.sub_tasks.append(t_schema)
        else:
            # Nếu không có cha (hoặc cha không thuộc scope lấy về) -> Nó là Root của nhánh này
            roots.append(t_schema)
    # 3.3 (Tùy chọn) Sắp xếp lại danh sách theo Priority hoặc Deadline
    def recursive_sort(tasks_list):
        # Map độ ưu tiên ra số
        prio_map = {TaskPriority.HIGH: 1, TaskPriority.MEDIUM: 2, TaskPriority.LOW: 3}
        tasks_list.sort(key=lambda x: (
            prio_map.get(x.priority, 2), # 1. Ưu tiên
            x.deadline is None,          # 2. Có deadline hay không (None xuống dưới)
            x.deadline                   # 3. Ngày deadline
        ))
        for task in tasks_list:
            if task.sub_tasks:
                recursive_sort(task.sub_tasks)
    recursive_sort(roots)
    # [NEW LOGIC] FILL TAG CHO VIEW (Fix hiển thị My Tasks)
    _fill_inherited_tags_pydantic(roots)
    return roots

# --- CẬP NHẬT: GET ASSIGNED TASKS ONLY (Dùng Schema Rút Gọn) ---
def get_tasks_by_assignee_id(db: Session, user: User) -> List[TaskListResponse]:
    query = select(BiddingTask).where(
        BiddingTask.assignee_id == user.user_id
    ).options(
        joinedload(BiddingTask.project),
        selectinload(BiddingTask.assignments).joinedload(TaskAssignment.user),
        selectinload(BiddingTask.assignments).joinedload(TaskAssignment.unit)
    )

    tasks = db.execute(query).unique().scalars().all()

    sorted_tasks = sorted(tasks, key=lambda x: (x.deadline is None, x.deadline))

    results = []
    for task_orm in sorted_tasks:
        # Dùng helper map
        results.append(_map_task_single_level(task_orm))

    return results
# ... (Giữ nguyên các hàm CRUD Comment và Attachment cũ) ...
# --- LOGIC CRUD CHO COMMENT ---

def create_comment(db: Session, task_id: int, comment_in: TaskCommentCreate, user: User):
    """
    Tạo comment mới hoặc trả lời comment khác.
    """
    # 1. Kiểm tra quyền truy cập Task trước khi comment
    # (Dùng lại hàm check_access_permission bạn đã có)
    # if not check_access_permission(db, task_id, user):
    #     raise HTTPException(status_code=403, detail="Bạn không có quyền thảo luận tại công việc này.")

    # 2. Nếu là reply, kiểm tra parent comment có tồn tại và thuộc task này không
    if comment_in.parent_id:
        parent = db.query(TaskComment).filter(
            TaskComment.id == comment_in.parent_id,
            TaskComment.task_id == task_id
        ).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Comment cha không tồn tại hoặc không thuộc task này.")

    # 3. Tạo comment
    new_comment = TaskComment(
        task_id=task_id,
        user_id=user.user_id,
        parent_id=comment_in.parent_id,
        content=comment_in.content
    )
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)
    return new_comment

def get_task_comments_tree(db: Session, task_id: int, user: User):
    """
    Lấy danh sách comment theo dạng cây (Nested).
    Chỉ lấy các comment gốc (parent_id=None), các reply sẽ được load qua relationship.
    """
    # if not check_access_permission(db, task_id, user):
    #      raise HTTPException(status_code=403, detail="Không có quyền xem thảo luận.")

    # Eager Load: Load luôn author và replies để tránh N+1 query
    query = select(TaskComment).where(
        TaskComment.task_id == task_id,
        TaskComment.parent_id == None # Chỉ lấy gốc
    ).options(
        joinedload(TaskComment.author),
        joinedload(TaskComment.replies).joinedload(TaskComment.author) # Load cấp con
    ).order_by(TaskComment.created_at.asc())

    comments = db.execute(query).unique().scalars().all()
    return comments

# --- UPDATE COMMENT ---
def update_comment(db: Session, comment_id: int, comment_in: TaskCommentUpdate, user: User):
    # 1. Tìm comment
    comment = db.query(TaskComment).filter(TaskComment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Bình luận không tồn tại.")

    # 2. Kiểm tra quyền sở hữu (Chỉ chủ nhân mới được sửa)
    if comment.user_id != user.user_id:
        raise HTTPException(status_code=403, detail="Bạn không có quyền sửa bình luận của người khác.")

    # 3. Cập nhật
    comment.content = comment_in.content
    db.commit()
    db.refresh(comment)
    return comment

# --- DELETE COMMENT ---
def delete_comment(db: Session, comment_id: int, user: User):
    # 1. Tìm comment
    comment = db.query(TaskComment).filter(TaskComment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Bình luận không tồn tại.")

    # 2. Kiểm tra quyền:
    # - Chủ nhân comment được xóa
    # - Hoặc Admin/Manager được xóa (để kiểm duyệt nội dung xấu)
    is_author = comment.user_id == user.user_id
    is_admin = user.role in [UserRole.ADMIN, UserRole.MANAGER]
    
    if not (is_author or is_admin):
        raise HTTPException(status_code=403, detail="Bạn không có quyền xóa bình luận này.")

    # 3. Xóa
    # Lưu ý: Do đã cấu hình cascade ở DB và Model, 
    # các comment con (reply) của comment này cũng sẽ tự động bị xóa theo.
    db.delete(comment)
    db.commit()
    return {"message": "Đã xóa bình luận thành công."}

def upload_task_attachments(db: Session, task_id: int, files: List[UploadFile], user: User):
    # 1. Lấy thông tin Task & Check quyền
    from app.modules.bidding.task.crud import get_task_detail 
    task = get_task_detail(db, task_id, user) 

    # Check quyền (Assignee hoặc Manager)
    is_assignee = (task.assignee_id == user.user_id)
    is_manager = user.role in [UserRole.ADMIN, UserRole.MANAGER, UserRole.BID_MANAGER]
    
    if not (is_assignee or is_manager):
         raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Bạn không có quyền tải lên tài liệu cho công việc này."
        )

    # 2. Chuẩn bị thư mục tạm
    temp_dir = "temp_uploads"
    os.makedirs(temp_dir, exist_ok=True)
    
    # Danh sách để chứa các URL sau khi upload thành công
    uploaded_urls = []
    
    # Nếu task.attachment_url đang là None, khởi tạo list rỗng. 
    # Nếu đã có data (JSON), lấy data cũ ra để append thêm.
    current_urls = task.attachment_url if task.attachment_url else []
    # Đảm bảo current_urls là list (phòng trường hợp DB lưu sai format)
    if not isinstance(current_urls, list):
        current_urls = []

    try:
        # 3. [VÒNG LẶP] Xử lý từng file
        for file in files:
            # Xử lý tên file & content type
            original_filename = file.filename or f"unknown_{uuid.uuid4().hex}"
            safe_content_type = file.content_type or "application/octet-stream"
            
            # Tạo file tạm
            # Giữ nguyên tên gốc hoặc thêm UUID để tránh trùng file trong cùng folder
            # Cách 1: Giữ nguyên tên gốc (nếu upload trùng tên sẽ ghi đè):
            # clean_filename = original_filename
            # Cách 2: Thêm UUID (an toàn hơn):
            file_ext = os.path.splitext(original_filename)[1]
            clean_filename = f"{uuid.uuid4().hex}_{original_filename}"
            
            temp_file_path = os.path.join(temp_dir, clean_filename)

            # Lưu xuống đĩa tạm
            with open(temp_file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # --- [QUAN TRỌNG] Tạo đường dẫn theo yêu cầu: {task_id}/{filename} ---
            # Bucket: jkancon
            # Object: 102/tai_lieu_hop.pdf
            minio_object_name = f"{task_id}/{original_filename}" 
            
            # Upload MinIO
            minio_url = minio_handler.upload_file(
                file_path=temp_file_path,
                object_name=minio_object_name,
                content_type=safe_content_type,
                bucket_name="jkancon"
            )

            if minio_url:
                uploaded_urls.append(minio_url)
            
            # Xóa file tạm ngay sau khi up xong file đó
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

        # 4. Cập nhật DB
        # Nối list mới vào list cũ
        updated_list = current_urls + uploaded_urls
        
        # Lưu lại vào DB (SQLAlchemy sẽ tự convert list -> JSON array)
        task.attachment_url = updated_list
        
        db.commit()
        db.refresh(task)
        
        logger.info(f"User {user.user_id} added {len(uploaded_urls)} files to task {task_id}")
        return task

    except Exception as e:
        logger.error(f"Batch upload error: {e}")
        # Dọn dẹp folder tạm nếu lỗi
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    
def delete_task_attachment(db: Session, task_id: int, filename: str, user: User):
    # 1. Lấy task và check quyền
    from app.modules.bidding.task.crud import get_task_detail
    task = get_task_detail(db, task_id, user)

    # Check quyền (Chỉ Assignee hoặc Manager được xóa)
    is_assignee = (task.assignee_id == user.user_id)
    is_manager = user.role in [UserRole.ADMIN, UserRole.MANAGER, UserRole.BID_MANAGER]
    
    if not (is_assignee or is_manager):
         raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Bạn không có quyền xóa tài liệu của công việc này."
        )

    # 2. Xác định Object Name trên MinIO
    # Cấu trúc folder: {task_id}/{filename}
    minio_object_name = f"{task_id}/{filename}"

    # 3. Xử lý danh sách URL trong Database
    current_urls = task.attachment_url if isinstance(task.attachment_url, list) else []
    
    # Tạo list mới KHÔNG chứa file cần xóa
    # Logic: Giữ lại các URL mà trong chuỗi KHÔNG chứa "task_id/filename"
    # (Cách này an toàn hơn so sánh chuỗi tuyệt đối vì URL có thể chứa domain thay đổi)
    new_urls = [url for url in current_urls if minio_object_name not in url]

    # Nếu độ dài không đổi nghĩa là không tìm thấy file trong DB
    if len(new_urls) == len(current_urls):
        raise HTTPException(status_code=404, detail="Không tìm thấy file này trong dữ liệu công việc.")

    # 4. Gọi MinIO xóa file vật lý
    is_deleted = minio_handler.delete_file(minio_object_name, bucket_name="jkancon")
    
    if not is_deleted:
        # Tùy chọn: Có thể throw lỗi hoặc vẫn cho qua nếu muốn ưu tiên sạch DB
        logger.warning(f"Không thể xóa file trên MinIO (hoặc file không tồn tại): {minio_object_name}")

    # 5. Cập nhật DB
    task.attachment_url = new_urls
    db.commit()
    db.refresh(task)
    
    return task
def delete_all_task_attachments(db: Session, task_id: int, user: User):
    # 1. Lấy task và check quyền
    from app.modules.bidding.task.crud import get_task_detail
    task = get_task_detail(db, task_id, user)

    # Check quyền (Chỉ Assignee hoặc Manager)
    is_assignee = (task.assignee_id == user.user_id)
    is_manager = user.role in [UserRole.ADMIN, UserRole.MANAGER, UserRole.BID_MANAGER]
    
    if not (is_assignee or is_manager):
         raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Bạn không có quyền xóa tài liệu của công việc này."
        )

    # 2. Gọi MinIO xóa folder "{task_id}/"
    # Lưu ý: Cần thêm dấu "/" ở cuối để đảm bảo chỉ xóa đúng folder task đó
    # Nếu không có dấu "/", task_id="1" có thể xóa nhầm file của task_id="10", "11"...
    folder_prefix = f"{task_id}/"
    
    minio_handler.delete_folder(folder_prefix, bucket_name="jkancon")

    # 3. Làm sạch dữ liệu trong DB (Set về mảng rỗng)
    task.attachment_url = []
    
    db.commit()
    db.refresh(task)
    
    logger.info(f"User {user.user_id} deleted ALL attachments of task {task_id}")
    return task

# --- 2. [MỚI] GET LIST FOR REVIEWER ---
def get_tasks_for_reviewer(db: Session, user: User) -> List[TaskListResponse]:
    # 1. Tìm task review
    query = select(BiddingTask).where(BiddingTask.reviewer_id == user.user_id)
    
    # [CẬP NHẬT] Thêm load assignments
    query = query.options(
        joinedload(BiddingTask.project),
        selectinload(BiddingTask.assignments).joinedload(TaskAssignment.user),
        selectinload(BiddingTask.assignments).joinedload(TaskAssignment.unit)
    )
    
    review_tasks = db.execute(query).unique().scalars().all()
    if not review_tasks:
        return []

    # 2. Tìm cha (Ancestors)
    all_related_tasks: Dict[int, BiddingTask] = {t.id: t for t in review_tasks}
    ids_to_find_parent = [t.id for t in review_tasks if t.parent_task_id is not None]

    while ids_to_find_parent:
        parent_query = select(BiddingTask).where(
            BiddingTask.id.in_(
                select(BiddingTask.parent_task_id).where(BiddingTask.id.in_(ids_to_find_parent))
            )
        ).options(
            joinedload(BiddingTask.project),
            # Load assignments cho cha
            selectinload(BiddingTask.assignments).joinedload(TaskAssignment.user),
            selectinload(BiddingTask.assignments).joinedload(TaskAssignment.unit)
        )
        parents = db.execute(parent_query).unique().scalars().all()
        ids_to_find_parent = []
        for p in parents:
            if p.id not in all_related_tasks:
                all_related_tasks[p.id] = p
                if p.parent_task_id:
                    ids_to_find_parent.append(p.id)

    # 3. Dựng cây
    schema_map: Dict[int, TaskListResponse] = {}
    for t_id, t_orm in all_related_tasks.items():
        t_schema = _map_task_single_level(t_orm) # Dùng helper
        schema_map[t_id] = t_schema

    roots = []
    for t_id, t_schema in schema_map.items():
        original_orm = all_related_tasks.get(t_id)
        parent_id = original_orm.parent_task_id if original_orm else None

        if parent_id and parent_id in schema_map:
            parent = schema_map[parent_id]
            parent.sub_tasks.append(t_schema)
        else:
            roots.append(t_schema)

    # 4. Sort riêng cho reviewer
    def recursive_sort_reviewer(tasks_list):
        tasks_list.sort(key=lambda x: (
            0 if x.status == TaskStatus.PENDING_REVIEW else 1,
            0 if x.deadline and x.deadline < datetime.now() else 1,
            x.deadline if x.deadline else datetime.max
        ))
        for task in tasks_list:
            if task.sub_tasks:
                recursive_sort_reviewer(task.sub_tasks)

    recursive_sort_reviewer(roots)
    return roots
# --- 3. [MỚI] GET DETAIL FOR REVIEWER ---
def get_task_detail_for_reviewer(db: Session, task_id: int, user: User):
    """
    Xem chi tiết dành riêng cho Reviewer.
    CHỈ CHO PHÉP người được gán là Reviewer (reviewer_id) truy cập.
    """
    # 1. Query load đầy đủ thông tin
    query = select(BiddingTask).where(BiddingTask.id == task_id).options(
        joinedload(BiddingTask.project),
        joinedload(BiddingTask.assignments).joinedload(TaskAssignment.user),
        joinedload(BiddingTask.assignments).joinedload(TaskAssignment.unit),
        joinedload(BiddingTask.sub_tasks).joinedload(BiddingTask.assignments),
        joinedload(BiddingTask.comments).joinedload(TaskComment.author)
    )
    
    task = db.execute(query).unique().scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Công việc không tồn tại")

    # 2. [QUAN TRỌNG] Kiểm tra quyền STRICT (Chặt chẽ)
    # Logic cũ: Cho phép Reviewer HOẶC Admin
    # Logic MỚI: Chỉ cho phép Reviewer (Reviewer ID phải khớp với User ID hiện tại)
    
    if task.reviewer_id != user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Bạn không có quyền duyệt công việc này (Sai Reviewer)."
        )
        

    return task