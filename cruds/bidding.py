from sqlalchemy.orm import Session
from sqlalchemy import or_, desc
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

# 2. Lấy danh sách gói thầu có Tìm kiếm & Lọc (Hàm chính)
def get_packages(
    db: Session, 
    skip: int = 0, 
    limit: int = 100, 
    search_query: Optional[str] = None, 
    status: Optional[PackageStatus] = None
):
    query = db.query(BiddingPackage)
    
    # --- Tìm kiếm ---
    if search_query:
        search = f"%{search_query}%"
        # Lưu ý: SQL Server mặc định không phân biệt hoa thường, dùng ilike hoặc like đều được
        query = query.filter(
            or_(
                BiddingPackage.ten_goi_thau.ilike(search),
                BiddingPackage.ma_tbmt.ilike(search),
                BiddingPackage.ten_du_an.ilike(search)
            )
        )
    
    # --- Lọc theo trạng thái ---
    if status:
        query = query.filter(BiddingPackage.trang_thai == status)
        
    # --- Sắp xếp & Phân trang (BẮT BUỘC CÓ ORDER BY) ---
    # Sắp xếp theo ngày tạo mới nhất lên đầu
    return query.order_by(desc(BiddingPackage.created_at))\
                .offset(skip)\
                .limit(limit)\
                .all()

# 3. Tạo mới gói thầu
def create_package(db: Session, package: schemas.BiddingPackageBase):
    # Chuyển Pydantic model sang dict
    package_data = package.model_dump()
    
    # Xử lý mapping field nếu tên trong Schema khác tên trong DB
    # Ví dụ: Nếu schema có 'ben_moi_thau' nhưng DB là 'chu_dau_tu'
    if 'ben_moi_thau' in package_data:
        # Nếu chu_dau_tu chưa có dữ liệu, lấy từ ben_moi_thau
        if not package_data.get('chu_dau_tu'):
            package_data['chu_dau_tu'] = package_data.pop('ben_moi_thau')
        else:
            # Nếu đã có chu_dau_tu, chỉ cần xóa ben_moi_thau để tránh lỗi dư cột
            package_data.pop('ben_moi_thau', None)

    # Tạo đối tượng DB
    db_obj = BiddingPackage(**package_data)
    
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

# 4. Cập nhật gói thầu
def update_package(db: Session, hsmt_id: int, package_update: schemas.BiddingPackageUpdate):
    db_obj = get_package(db, hsmt_id)
    if not db_obj:
        return None
    
    # exclude_unset=True chỉ lấy những trường người dùng gửi lên, không lấy trường None mặc định
    update_data = package_update.model_dump(exclude_unset=True)
    
    for key, value in update_data.items():
        # Kiểm tra xem Model có attribute này không trước khi set (để an toàn)
        if hasattr(db_obj, key):
            setattr(db_obj, key, value)
    
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

# 5. Xóa gói thầu
def delete_package(db: Session, hsmt_id: int):
    db_obj = get_package(db, hsmt_id)
    if db_obj:
        db.delete(db_obj)
        db.commit()
        return True
    return False

# 6. Lấy danh sách file đính kèm
def get_files_by_package_id(db: Session, hsmt_id: int):
    return db.query(BiddingPackageFile).filter(BiddingPackageFile.hsmt_id == hsmt_id).all()

# ==========================================
# NHIỆM VỤ (Task)
# ==========================================
def create_task(db: Session, task: schemas.TaskCreate): # Giả sử bạn có TaskCreate schema
    db_task = BiddingTask(**task.model_dump())
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task