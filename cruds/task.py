from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, or_, and_, case
from fastapi import HTTPException, status, UploadFile
from models import BiddingTask, TaskAssignment, User, UserRole, TaskStatus, TaskPriority, TaskComment
from schemas.task import TaskCreate, TaskUpdate, TaskCommentCreate, TaskCommentUpdate, TaskResponse
from utils.abac import check_permission, AbacAction
import os
import uuid
import shutil
import logging
from typing import Optional, List, Dict
from minio_client import minio_handler

logger = logging.getLogger(__name__)

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
        # <--- THÊM joinedload(BiddingTask.project)
        joinedload(BiddingTask.project),
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
    # Thay vì dùng db.get(), ta dùng select + options để load project
    query = select(BiddingTask).where(BiddingTask.id == task_id).options(
        joinedload(BiddingTask.project),    # <--- Load Project
        joinedload(BiddingTask.assignments),
        joinedload(BiddingTask.sub_tasks)
    )
    
    task = db.execute(query).unique().scalar_one_or_none()
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
    query = query.options(joinedload(BiddingTask.project))
    
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
        ).options(joinedload(BiddingTask.project))
        
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
    
    return roots

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

def upload_task_attachment(db: Session, task_id: int, file: UploadFile, user: User):
    # 1. Lấy thông tin Task & Check quyền (Sử dụng lại hàm check access có sẵn)
    task = get_task_detail(db, task_id, user) # Hàm này đã bao gồm check quyền truy cập cơ bản
    
    # Check thêm quyền sửa: Chỉ người được giao (Assignee) hoặc Quản lý mới được up file
    # (Nếu logic của bạn cho phép người xem cũng được up thì bỏ đoạn này)
    is_assignee = (task.assignee_id == user.user_id)
    is_manager = user.role in [UserRole.ADMIN, UserRole.MANAGER, UserRole.BID_MANAGER]
    
    if not (is_assignee or is_manager):
         raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Chỉ người được phân công hoặc quản lý mới được tải lên tài liệu đính kèm."
        )

    # 2. Chuẩn bị thư mục tạm để lưu file trước khi upload MinIO
    # (MinIO fput_object cần file path thực tế)
    # Đoạn xử lý tên file tạm
    # 1. Xử lý tên file (Tránh lỗi splitext nhận None)
    # Nếu file.filename là None thì dùng "unknown_file"
    original_filename = file.filename or "unknown_file" 
    
    # 2. Xử lý Content-Type (Tránh lỗi upload_file nhận None)
    # Nếu file.content_type là None thì dùng "application/octet-stream"
    safe_content_type = file.content_type or "application/octet-stream"

    # -----------------------

    temp_dir = "temp_uploads"
    os.makedirs(temp_dir, exist_ok=True)
    
    # Dùng original_filename đã xử lý ở trên (đảm bảo là string)
    file_extension = os.path.splitext(original_filename)[1]
    unique_filename = f"task_{task_id}_{uuid.uuid4().hex}{file_extension}"
    temp_file_path = os.path.join(temp_dir, unique_filename)

    try:
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        minio_object_name = f"projects/{task.bidding_project_id}/tasks/{unique_filename}"
        
        # Truyền safe_content_type vào
        minio_url = minio_handler.upload_file(
            file_path=temp_file_path,
            object_name=minio_object_name,
            content_type=safe_content_type, # <--- Đã đảm bảo là string
            bucket_name="jkancon"
        )

        if not minio_url:
            raise HTTPException(status_code=500, detail="Lỗi MinIO Upload")

        task.attachment_url = minio_url
        db.commit()
        db.refresh(task)
        
        logger.info(f"User {user.user_id} uploaded file to task {task_id}: {minio_url}")
        return task

    except Exception as e:
        logger.error(f"Upload task attachment error: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
        
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)