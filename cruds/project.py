from sqlalchemy.orm import Session
from sqlalchemy import select, or_
from typing import List, Optional
from models import User, UserRole, BiddingTask, TaskAssignment

# Import model của bạn và schema ở trên
from models import BiddingPackage, BiddingProject 
from schemas.project import BiddingProjectCreate, BiddingProjectUpdate

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
    query = select(BiddingProject)

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
    return list(result.scalars().all())

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