from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from models import BiddingPackage, BiddingProject, User
from utils.security import get_current_user
from utils.abac import check_permission
from utils.constants import AbacAction

# Giả sử bạn có file dependencies để lấy DB session (get_db)
from database import get_db 
import cruds.project as cruds
import schemas.project as schemas

router = APIRouter(
    prefix="/bidding-projects",
    tags=["Bidding Projects"]
)

# --- API: TẠO DỰ ÁN ---
@router.post("/", response_model=schemas.BiddingProjectResponse)
def create_project(
    project_in: schemas.BiddingProjectCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user) # <--- Lấy người đang login (Người tạo)
):
    # 1. Lấy thông tin gói thầu gốc
    package = db.get(BiddingPackage, project_in.source_package_id)
    if not package:
        raise HTTPException(status_code=404, detail="Gói thầu không tồn tại")
    
    is_allowed = check_permission(
        db=db,
        user=current_user,
        resource=package,             # Resource context là gói thầu hiện tại
        action=AbacAction.CREATE_PROJECT
    )

    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Truy cập bị từ chối: Bạn không có quyền tạo Dự án từ gói thầu này."
        )

    # 2. Validate: Gói thầu phải được duyệt (có người duyệt) thì mới tạo dự án được
    if not package.nguoi_duyet_id:
         raise HTTPException(
            status_code=400, 
            detail="Gói thầu chưa được Lãnh đạo phê duyệt (GO), chưa có thông tin Host."
        )

    # 3. Tạo Project
    try:
        new_project = BiddingProject(
            name=project_in.name,
            status=project_in.status,
            
            # TỰ ĐỘNG GÁN ID:
            host_id=package.nguoi_duyet_id,       # Người chủ trì = Người đã duyệt gói thầu
            bid_team_leader_id=current_user.user_id # Trưởng nhóm thầu = Người đang tạo dự án
        )
        
        db.add(new_project)
        db.flush() # Để lấy ID dự án

        # Cập nhật ngược lại gói thầu (gán vào dự án)
        package.project_id = new_project.id
        db.add(package)
        
        db.commit()
        db.refresh(new_project)
        return new_project
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
# --- API: LẤY DANH SÁCH & TÌM KIẾM ---
@router.get("/", response_model=List[schemas.BiddingProjectResponse])
def read_projects(
    skip: int = 0,
    limit: int = 100,
    q: Optional[str] = Query(None, description="Tìm kiếm theo tên dự án"),
    status: Optional[str] = Query(None, description="Lọc theo trạng thái"),
    db: Session = Depends(get_db)
):
    """
    Lấy danh sách dự án thầu. 
    Hỗ trợ phân trang (skip, limit), tìm kiếm (q) và lọc (status).
    """
    projects = cruds.get_projects(
        db=db, 
        skip=skip, 
        limit=limit, 
        search_keyword=q,
        status_filter=status
    )
    return projects

# --- API: LẤY CHI TIẾT 1 DỰ ÁN ---
@router.get("/{project_id}", response_model=schemas.BiddingProjectResponse)
def read_project(project_id: int, db: Session = Depends(get_db)):
    db_project = cruds.get_project(db, project_id=project_id)
    if db_project is None:
        raise HTTPException(status_code=404, detail="Bidding Project not found")
    return db_project

# --- API: CẬP NHẬT DỰ ÁN ---
@router.put("/{project_id}", response_model=schemas.BiddingProjectResponse)
def update_project(
    project_id: int, 
    project_in: schemas.BiddingProjectUpdate, 
    db: Session = Depends(get_db)
):
    db_project = cruds.update_project(db, project_id=project_id, project_in=project_in)
    if db_project is None:
        raise HTTPException(status_code=404, detail="Bidding Project not found")
    return db_project

# --- API: XÓA DỰ ÁN ---
@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    success = cruds.delete_project(db, project_id=project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Bidding Project not found")
    return None