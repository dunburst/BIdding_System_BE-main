from sqlalchemy.orm import Session
from sqlalchemy import select, or_
from typing import List, Optional
from models import User, UserRole

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

# 3. Lấy danh sách & Tìm kiếm (Read Many / Search)
def get_projects(
    db: Session, 
    skip: int = 0, 
    limit: int = 100, 
    search_keyword: Optional[str] = None,
    status_filter: Optional[str] = None,
    user: Optional[User] = None
) -> List[BiddingProject]:
    query = select(BiddingProject)

    # Logic tìm kiếm theo tên (không phân biệt hoa thường)
    if search_keyword:
        query = query.where(BiddingProject.name.ilike(f"%{search_keyword}%"))
    
    # Logic lọc theo trạng thái
    if status_filter:
        query = query.where(BiddingProject.status == status_filter)
        
    # 3. --- LOGIC PHÂN QUYỀN (QUAN TRỌNG) ---
    # Nếu user KHÔNG phải ADMIN -> Áp dụng bộ lọc cá nhân
    if user and user.role != UserRole.ADMIN:
        query = query.filter(
            or_(
                # Trường hợp 1: User là Người chủ trì (Host/Người duyệt)
                BiddingProject.host_id == user.user_id,
                
                # Trường hợp 2: User là Trưởng nhóm thầu
                BiddingProject.bid_team_leader_id == user.user_id
            )
        )
    # Nếu là ADMIN thì bỏ qua đoạn if trên -> Xem được tất cả

    # Sắp xếp theo mới nhất
    query = query.order_by(BiddingProject.created_at.desc()).offset(skip).limit(limit)
    
    result = db.execute(query)
    return list(result.scalars().all())

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