from sqlalchemy.orm import Session
from sqlalchemy import func, select, or_
from typing import List, Optional
from app.modules.users.model import User
from app.core.utils.enum import TaskStatus, TaskPriority, UserRole
from app.modules.bidding.project.model import BiddingProject
from app.modules.bidding.task.model import BiddingTask, TaskAssignment
# Import model của bạn và schema ở trên
from app.modules.bidding.package.model import BiddingPackage
from app.modules.bidding.project.schema import ProjectStatistics
from app.modules.bidding.project.schema import BiddingProjectCreate, BiddingProjectUpdate
from sqlalchemy.orm import joinedload

def create_project_from_package(db: Session, project_in: BiddingProjectCreate) -> BiddingProject:
    # Bước 1: Kiểm tra gói thầu có tồn tại không
    # (Lưu ý: dùng hsmt_id hoặc id tùy vào khóa chính bạn đặt trong model Package)
    package = db.get(BiddingPackage, project_in.source_package_id)
    if not package:
        raise ValueError(f"Gói thầu ID {project_in.source_package_id} không tồn tại.")

    # Bước 2: Tạo BiddingProject
    db_project = BiddingProject(
        name=project_in.name,
        status=project_in.status,
    )
    db.add(db_project)
    
    # FLUSH: Đẩy data xuống DB để db_project có ID, nhưng chưa Commit hẳn (để đảm bảo tính giao dịch)
    db.flush() 

    # Bước 3: Cập nhật Gói thầu để trỏ về Dự án vừa tạo
    # Gán project_id của gói thầu = id của dự án mới
    package.project_id = db_project.id
    db.add(package) # Đánh dấu package đã thay đổi

    # Bước 4: Commit cả 2 thay đổi cùng lúc
    db.commit()
    
    # Refresh để lấy lại data mới nhất
    db.refresh(db_project)
    return db_project

# 2. Lấy chi tiết theo ID (Read One)
def get_project(db: Session, project_id: int) -> Optional[BiddingProject]:
    return db.get(BiddingProject, project_id)

# ---------------------------------------------------------
# 3. Lấy danh sách & Tìm kiếm (ĐÃ NÂNG CẤP)
# ---------------------------------------------------------
def get_projects(
    db: Session, 
    skip: int = 0, 
    limit: int = 100, 
    search_keyword: Optional[str] = None,
    status_filter: Optional[str] = None,
    user: Optional[User] = None
) -> List[BiddingProject]:
    
    # Bắt đầu query từ bảng Dự án
    query = select(BiddingProject).options(
        joinedload(BiddingProject.team_leader),
        joinedload(BiddingProject.packages)
    )

    # --- LOGIC JOIN ĐỂ LỌC (Quan trọng) ---
    if user and user.role not in [UserRole.ADMIN, UserRole.MANAGER, UserRole.BID_MANAGER]:
        # Join sang Task và Assignment để kiểm tra điều kiện
        # Dùng outerjoin để không bị mất dự án nếu user là Host (nhưng dự án chưa có task)
        query = query.outerjoin(
            BiddingTask, BiddingTask.bidding_project_id == BiddingProject.id
        ).outerjoin(
            TaskAssignment, BiddingTask.assignments
        )

    # --- CÁC BỘ LỌC CƠ BẢN ---
    if search_keyword:
        query = query.where(BiddingProject.name.ilike(f"%{search_keyword}%"))
    
    if status_filter:
        query = query.where(BiddingProject.status == status_filter)
        
    # --- LOGIC PHÂN QUYỀN ---
    # Nếu user KHÔNG phải cấp quản lý -> Áp dụng bộ lọc
    if user and user.role not in [UserRole.ADMIN, UserRole.MANAGER, UserRole.BID_MANAGER]:
        query = query.filter(
            or_(
                # 1. User là Lãnh đạo dự án (Host / Leader)
                BiddingProject.host_id == user.user_id,
                BiddingProject.bid_team_leader_id == user.user_id,

                # 2. User được giao việc trực tiếp trong Task (assignee_id)
                BiddingTask.assignee_id == user.user_id,

                # 3. User được giao việc qua Assignment (đích danh)
                TaskAssignment.assigned_user_id == user.user_id,

                # 4. User thuộc phòng ban được giao việc
                TaskAssignment.assigned_unit_id == user.org_unit_id
            )
        ).distinct() # CỰC KỲ QUAN TRỌNG: Loại bỏ các dòng dự án trùng lặp do phép Join

    # Sắp xếp và phân trang
    query = query.order_by(BiddingProject.created_at.desc()).offset(skip).limit(limit)
    
    result = db.execute(query)
    return list(result.scalars().unique().all())

# ---------------------------------------------------------
# [MỚI] Hàm kiểm tra quyền truy cập Project (cho API Detail)
# ---------------------------------------------------------
def check_user_project_access(db: Session, project_id: int, user: User) -> bool:
    """
    Trả về True nếu User có quyền xem dự án này.
    Điều kiện: Là Admin/Manager HOẶC Host/Leader HOẶC Có task trong dự án.
    """
    # 1. Nếu là Admin/Manager -> Allow all
    if user.role in [UserRole.ADMIN, UserRole.MANAGER, UserRole.BID_MANAGER]:
        return True

    # 2. Kiểm tra vai trò trong Dự án (Host/Leader)
    project = db.get(BiddingProject, project_id)
    if not project:
        return False
    if project.host_id == user.user_id or project.bid_team_leader_id == user.user_id:
        return True

    # 3. Kiểm tra xem có task nào dính dáng đến user không
    # Query: Đếm số task trong dự án này mà user có liên quan
    stmt = select(BiddingTask.id).outerjoin(TaskAssignment, BiddingTask.assignments).where(
        BiddingTask.bidding_project_id == project_id,
        or_(
            BiddingTask.assignee_id == user.user_id,
            TaskAssignment.assigned_user_id == user.user_id,
            TaskAssignment.assigned_unit_id == user.org_unit_id
        )
    ).limit(1) # Chỉ cần tìm thấy 1 cái là đủ

    result = db.execute(stmt).scalar_one_or_none()
    return result is not None

# 4. Cập nhật (Update)
def update_project(
    db: Session, 
    project_id: int, 
    project_in: BiddingProjectUpdate
) -> Optional[BiddingProject]:
    db_project = get_project(db, project_id)
    if not db_project:
        return None
    
    # Chỉ update những trường user gửi lên (exclude_unset=True)
    update_data = project_in.model_dump(exclude_unset=True)
    
    for key, value in update_data.items():
        setattr(db_project, key, value)

    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project

# 5. Xóa (Delete)
def delete_project(db: Session, project_id: int) -> bool:
    db_project = get_project(db, project_id)
    if not db_project:
        return False
    
    db.delete(db_project)
    db.commit()
    return True

def _get_keywords_from_tags(allowed_tag_codes: List[str]) -> List[str]:
    """
    Input: ['FINANCE', 'TECH']
    Output: ['tài chính', 'giá', 'kỹ thuật', 'biện pháp thi công'...]
    """
    # Map ngược từ Code sang các keyword tiếng Việt
    TAG_TO_KEYWORDS = {
        "HR": ["nhân sự"],
        "LEGAL": ["pháp lý"],
        "TECH": ["biện pháp thi công", "kỹ thuật"],
        "FINANCE": ["tài chính"],
        "DEVICE": ["máy móc", "thiết bị"],
        "CONTRACT": ["hợp đồng", "hợp đông"],
        "DBTC": ["bldt", "cktd", "bảo lãnh", "tín dụng"],
        "VT": ["vt", "vật tư"],
        "GIA": ["giá"]
    }
    
    result_keywords = []
    for code in allowed_tag_codes:
        if code in TAG_TO_KEYWORDS:
            result_keywords.extend(TAG_TO_KEYWORDS[code])
            
    return result_keywords

def get_project_participants(db: Session, project_id: int) -> List[User]:
    """
    Lấy danh sách nhân sự tham gia dự án (Assignee, Leader, Member).
    LOẠI TRỪ: Host (Chủ trì) và Reviewer (Người duyệt các task).
    """
    # 1. Lấy thông tin Dự án để biết Host và Leader
    project = get_project(db, project_id)
    if not project:
        return []

    # Danh sách ID cần LOẠI BỎ (Người duyệt)
    excluded_ids = set()
    if project.host_id:
        excluded_ids.add(project.host_id)


    # 2. Thu thập ID người tham gia (Participant IDs)
    participant_ids = set()

    # a. Trưởng nhóm thầu (Bid Team Leader)
    if project.bid_team_leader_id:
        participant_ids.add(project.bid_team_leader_id)

    # b. Người thực hiện chính (Assignee) trong bảng Task
    assignees = db.query(BiddingTask.assignee_id)\
        .filter(BiddingTask.bidding_project_id == project_id)\
        .filter(BiddingTask.assignee_id.isnot(None))\
        .distinct().all()
    
    for a in assignees:
        participant_ids.add(a.assignee_id)
        
    reviewers = db.query(BiddingTask.reviewer_id)\
        .filter(BiddingTask.bidding_project_id == project_id)\
        .filter(BiddingTask.reviewer_id.isnot(None))\
        .distinct().all()
    
    for r in reviewers:
        participant_ids.add(r.reviewer_id)

    # c. Người được phối hợp (Assigned User) trong bảng Assignment
    # Join bảng Task để lọc theo project_id
    assigned_users = db.query(TaskAssignment.assigned_user_id)\
        .join(BiddingTask, TaskAssignment.task_id == BiddingTask.id)\
        .filter(BiddingTask.bidding_project_id == project_id)\
        .filter(TaskAssignment.assigned_user_id.isnot(None))\
        .distinct().all()

    for u in assigned_users:
        participant_ids.add(u.assigned_user_id)

    # 3. Loại bỏ Người duyệt ra khỏi danh sách tham gia
    # (Dùng phép trừ set: participants - excluded)
    final_ids = participant_ids - excluded_ids

    if not final_ids:
        return []

    # 4. Query lấy thông tin chi tiết User
    users = db.query(User).filter(User.user_id.in_(final_ids)).all()
    
    return users

def update_project_status(db: Session, project_id: int, new_status: str) -> Optional[BiddingProject]:
    """
    Cập nhật riêng trạng thái của dự án
    """
    project = db.get(BiddingProject, project_id)
    if not project:
        return None
    
    project.status = new_status
    # Nếu muốn lưu vết thời gian update
    project.updated_at = func.now()
    
    db.commit()
    db.refresh(project)
    return project

def get_project_statistics(db: Session, project_id: int) -> ProjectStatistics:
    """
    Hàm tính toán các chỉ số KPI của dự án:
    1. Deadline: Lấy ngày deadline xa nhất của các Task.
    2. Tiến độ: (Số task COMPLETED / Tổng số task) * 100.
    3. Nhân sự: Đếm unique (Host + Leader + Assignee + Reviewer + Assigned User).
    4. Độ ưu tiên: Lấy độ ưu tiên cao nhất trong các Task đang chạy.
    """
    
    # --- 1. LẤY DEADLINE XA NHẤT ---
    # Query: Max deadline của task thuộc dự án này
    stmt_deadline = select(func.max(BiddingTask.deadline)).where(
        BiddingTask.bidding_project_id == project_id
    )
    max_deadline = db.execute(stmt_deadline).scalar()

    # --- 2. TÍNH TIẾN ĐỘ ---
    # Tổng số task (Loại bỏ task cha nếu muốn tính chính xác theo đầu việc cụ thể, ở đây ta đếm hết)
    total_tasks = db.query(BiddingTask).filter(
        BiddingTask.bidding_project_id == project_id
    ).count()

    completed_tasks = db.query(BiddingTask).filter(
        BiddingTask.bidding_project_id == project_id,
        BiddingTask.status == TaskStatus.COMPLETED
    ).count()

    progress = 0.0
    if total_tasks > 0:
        progress = round((completed_tasks / total_tasks) * 100, 2)

    # --- 3. ĐẾM SỐ NGƯỜI THAM GIA (PARTICIPANTS) ---
    # Logic: Union các user ID từ các nguồn khác nhau trong dự án
    
    # A. Lấy Host và Team Leader từ Project
    project = db.get(BiddingProject, project_id)
    participants = set()
    if project:
    #     if project.host_id: participants.add(project.host_id)
        if project.bid_team_leader_id: participants.add(project.bid_team_leader_id)

    # B. Lấy Assignee và Reviewer từ bảng Task
    task_users = db.query(BiddingTask.assignee_id, BiddingTask.reviewer_id).filter(
        BiddingTask.bidding_project_id == project_id
    ).all()
    
    for assignee, reviewer in task_users:
        if assignee: participants.add(assignee)
        if reviewer: participants.add(reviewer)

    # C. Lấy Assigned User từ bảng Assignment (Join với Task để filter theo Project)
    assignment_users = db.query(TaskAssignment.assigned_user_id)\
        .join(BiddingTask, TaskAssignment.task_id == BiddingTask.id)\
        .filter(BiddingTask.bidding_project_id == project_id)\
        .filter(TaskAssignment.assigned_user_id.isnot(None))\
        .all()
        
    for (uid,) in assignment_users:
        participants.add(uid)

    participant_count = len(participants)

    # --- 4. TÍNH ĐỘ ƯU TIÊN (PRIORITY) ---
    # Logic: Nếu có bất kỳ task nào là HIGH -> Project là HIGH.
    # Nếu không, nếu có MEDIUM -> Project là MEDIUM. Còn lại là LOW.
    
    # Kiểm tra xem có task HIGH nào không
    has_high = db.query(BiddingTask).filter(
        BiddingTask.bidding_project_id == project_id,
        BiddingTask.priority == TaskPriority.HIGH,
        BiddingTask.status != TaskStatus.COMPLETED # Chỉ xét task chưa xong
    ).first()

    current_priority = "LOW"
    if has_high:
        current_priority = "HIGH"
    else:
        # Check Medium
        has_medium = db.query(BiddingTask).filter(
            BiddingTask.bidding_project_id == project_id,
            BiddingTask.priority == TaskPriority.MEDIUM,
            BiddingTask.status != TaskStatus.COMPLETED
        ).first()
        if has_medium:
            current_priority = "MEDIUM"

    return ProjectStatistics(
        deadline=max_deadline,
        progress=progress,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        participant_count=participant_count
        # priority=current_priority
    )