from sqlalchemy.orm import Session
from sqlalchemy import or_
from models import BiddingPackage, BiddingTask, PackageStatus, BiddingPackageFile
from schemas import bidding as schemas
from typing import Optional, List

# --- Gói thầu (Package) ---

def get_package(db: Session, hsmt_id: int):
    return db.query(BiddingPackage).filter(BiddingPackage.hsmt_id == hsmt_id).first()

def get_package_by_ma_tbmt(db: Session, ma_tbmt: str):
    return db.query(BiddingPackage).filter(BiddingPackage.ma_tbmt == ma_tbmt).first()

# 1. Lấy danh sách gói thầu (có phân trang)
def get_all_bidding_packages(db: Session, skip: int = 0, limit: int = 100):
    return db.query(BiddingPackage).order_by(BiddingPackage.created_at.desc()).offset(skip).limit(limit).all()

# 2. Lấy chi tiết gói thầu theo ID
def get_bidding_package_by_id(db: Session, hsmt_id: int):
    return db.query(BiddingPackage).filter(BiddingPackage.hsmt_id == hsmt_id).first()

# 3. Lấy danh sách file theo ID gói thầu
def get_files_by_package_id(db: Session, hsmt_id: int):
    return db.query(BiddingPackageFile).filter(BiddingPackageFile.hsmt_id == hsmt_id).all()

def get_packages(
    db: Session, 
    skip: int = 0, 
    limit: int = 100, 
    search_query: Optional[str] = None, 
    status: Optional[PackageStatus] = None
):
    query = db.query(BiddingPackage)
    
    # Tìm kiếm theo tên hoặc mã TBMT
    if search_query:
        search = f"%{search_query}%"
        query = query.filter(
            or_(
                BiddingPackage.ten_goi_thau.ilike(search),
                BiddingPackage.ma_tbmt.ilike(search)
            )
        )
    
    # Lọc theo trạng thái
    if status:
        query = query.filter(BiddingPackage.trang_thai == status)
        
    return query.offset(skip).limit(limit).all()

def create_package(db: Session, package: schemas.BiddingPackageCreate):
    # Lưu ý: Mapping fields từ schema sang model
    # Ở đây giả định schema khớp model, nếu tên khác nhau cần gán thủ công
    db_obj = BiddingPackage(
        ma_tbmt=package.ma_tbmt,
        ten_goi_thau=package.ten_goi_thau,
        chu_dau_tu=package.ben_moi_thau, # Mapping field
        linh_vuc=package.linh_vuc,
        trang_thai=package.trang_thai,
        so_tien_dam_bao_du_thau=package.so_tien_dam_bao_du_thau,
        thoi_diem_dong_thau=package.thoi_diem_dong_thau
        # ... map thêm các trường khác
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def update_package(db: Session, hsmt_id: int, package_update: schemas.BiddingPackageUpdate):
    db_obj = get_package(db, hsmt_id)
    if not db_obj:
        return None
    
    update_data = package_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_obj, key, value)
    
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def delete_package(db: Session, hsmt_id: int):
    db_obj = get_package(db, hsmt_id)
    if db_obj:
        db.delete(db_obj)
        db.commit()
    return db_obj

# --- Nhiệm vụ (Task) ---
def create_task(db: Session, task: schemas.TaskCreate):
    db_task = BiddingTask(**task.model_dump())
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task