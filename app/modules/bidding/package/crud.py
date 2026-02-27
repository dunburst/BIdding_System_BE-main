from sqlalchemy.orm import Session
from sqlalchemy import or_, desc
from app.modules.bidding.package.model import BiddingPackage, BiddingPackageFile
from app.modules.bidding.project.model import BiddingProject
from app.core.utils.enum import PackageStatus
from app.modules.bidding.task.model import BiddingTask
from app.modules.bidding.package import schema as schemas
from typing import Optional, List
from datetime import datetime
from sqlalchemy import extract
from sqlalchemy.orm import contains_eager
from datetime import timedelta
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
    
    # --- [MỚI] JOIN VỚI BẢNG DỰ ÁN ĐỂ CHECK TRẠNG THÁI ---
    # Dùng outerjoin để giữ lại cả những gói thầu chưa có dự án (project_id = NULL)
    query = query.outerjoin(BiddingProject, BiddingPackage.project_id == BiddingProject.id)
    
    # --- [MỚI] ĐIỀU KIỆN LỌC BỎ "COMPLETED" ---
    # Logic: Chỉ lấy gói thầu nếu:
    # 1. Chưa có dự án (BiddingProject.id là None)
    # HOẶC
    # 2. Đã có dự án nhưng trạng thái KHÁC "COMPLETED"
    query = query.filter(
        or_(
            BiddingProject.status != "COMPLETED",
            BiddingProject.id.is_(None)
        )
    )
    
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
    # --- BƯỚC QUAN TRỌNG: Đếm tổng số lượng trước khi phân trang ---
    total = query.count()
        
    # --- Sắp xếp & Phân trang (BẮT BUỘC CÓ ORDER BY) ---
    # Sắp xếp theo ngày tạo mới nhất lên đầu
    items = query.order_by(desc(BiddingPackage.created_at))\
                .offset(skip)\
                .limit(limit)\
                .all()
    
    # Trả về cả items và total
    return items, total
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

def get_closing_time(db: Session, hsmt_id: int):
    """
    Chỉ lấy giá trị thoi_diem_dong_thau của gói thầu.
    Dùng .scalar() để lấy trực tiếp giá trị thay vì object.
    """
    result = db.query(BiddingPackage.thoi_diem_dong_thau)\
        .filter(BiddingPackage.hsmt_id == hsmt_id)\
        .first()
    
    # result sẽ là một tuple (datetime,) hoặc None nếu không tìm thấy ID
    if result:
        return result[0] # Trả về datetime object
    return None # Không tìm thấy gói thầu

# --- HÀM LOGIC TÍNH TOÁN (Helper nội bộ) ---
def calculate_time_remaining(deadline: Optional[datetime]) -> str:
    if not deadline:
        return "Chưa có lịch"
    
    now = datetime.now()
    if deadline.tzinfo:
        deadline = deadline.replace(tzinfo=None) # Xử lý timezone nếu cần

    delta = deadline - now
    total_seconds = int(delta.total_seconds())

    if total_seconds <= 0:
        return "Đã đóng thầu"

    days = delta.days
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60

    if days > 0:
        return f"{days} ngày {hours} giờ"
    elif hours > 0:
        return f"{hours} giờ {minutes} phút"
    else:
        return f"{minutes} phút"


def get_package_by_project_id(db: Session, project_id: int):
    """
    Tìm gói thầu thuộc về một dự án cụ thể.
    """
    return db.query(BiddingPackage).filter(BiddingPackage.project_id == project_id).first()

def get_project_history(
    db: Session, 
    skip: int = 0, 
    limit: int = 100, 
    year: Optional[int] = None,
    linh_vuc: Optional[str] = None,
    chu_dau_tu: Optional[str] = None
):
    """
    Lấy lịch sử dự án COMPLETED, kèm theo Drive Folder ID.
    """
    
    # 1. Query & Join
    # Thêm .options(contains_eager(...)) để load luôn dữ liệu Project
    query = db.query(BiddingPackage)\
              .join(BiddingProject, BiddingPackage.project_id == BiddingProject.id)\
              .options(contains_eager(BiddingPackage.project)) 

    # 2. Filter Status
    query = query.filter(BiddingProject.status == "COMPLETED")

    # --- Các bộ lọc ---
    if year:
        query = query.filter(extract('year', BiddingPackage.thoi_diem_dong_thau) == year)
    
    if linh_vuc:
        query = query.filter(BiddingPackage.linh_vuc.ilike(f"%{linh_vuc}%"))

    if chu_dau_tu:
        query = query.filter(BiddingPackage.chu_dau_tu.ilike(f"%{chu_dau_tu}%"))

    # Đếm tổng
    total = query.count()
    
    # Sắp xếp & Phân trang
    items = query.order_by(BiddingPackage.thoi_diem_dong_thau.desc())\
                 .offset(skip)\
                 .limit(limit)\
                 .all()

    return items, total

def get_history_filters(db: Session):
    """
    Lấy danh sách các Năm và Chủ đầu tư duy nhất từ các dự án COMPLETED
    để dùng cho Dropdown lọc.
    """
    
    # --- 1. Lấy danh sách NĂM (Years) ---
    # Query: Select DISTINCT YEAR(thoi_diem_dong_thau) from ... where status = 'COMPLETED'
    years_query = db.query(extract('year', BiddingPackage.thoi_diem_dong_thau))\
        .join(BiddingProject, BiddingPackage.project_id == BiddingProject.id)\
        .filter(
            BiddingProject.status == "COMPLETED",
            BiddingPackage.thoi_diem_dong_thau.isnot(None) # Loại bỏ gói thầu chưa có ngày
        )\
        .distinct()\
        .order_by(extract('year', BiddingPackage.thoi_diem_dong_thau).desc())\
        .all()
    
    # Kết quả trả về dạng danh sách tuple: [(2025,), (2024,)] -> Cần flatten thành [2025, 2024]
    unique_years = [y[0] for y in years_query if y[0] is not None]

    # --- 2. Lấy danh sách CHỦ ĐẦU TƯ (Investors) ---
    # Query: Select DISTINCT chu_dau_tu from ... where status = 'COMPLETED'
    investors_query = db.query(BiddingPackage.chu_dau_tu)\
        .join(BiddingProject, BiddingPackage.project_id == BiddingProject.id)\
        .filter(
            BiddingProject.status == "COMPLETED",
            BiddingPackage.chu_dau_tu.isnot(None)
        )\
        .distinct()\
        .order_by(BiddingPackage.chu_dau_tu.asc())\
        .all()
        
    # Flatten: [('EVN',), ('Viettel',)] -> ['EVN', 'Viettel']
    unique_investors = [i[0] for i in investors_query if i[0]]

    return {
        "years": unique_years,
        "investors": unique_investors
    }
    
def cleanup_old_packages(db: Session, days_threshold: int = 30) -> int:
    """
    Xóa các gói thầu ở trạng thái NEW hoặc INTERESTED nếu created_at cũ hơn số ngày quy định.
    Trả về số lượng bản ghi đã xóa.
    """
    # 1. Tính thời điểm cắt (Cutoff date)
    cutoff_date = datetime.now() - timedelta(days=days_threshold)
    
    # 2. Các trạng thái cần dọn dẹp
    target_statuses = [PackageStatus.NEW, PackageStatus.INTERESTED]
    
    # 3. Thực hiện xóa
    # synchronize_session=False: Giúp xóa nhanh số lượng lớn mà không cần update lại session hiện tại
    deleted_count = db.query(BiddingPackage)\
        .filter(
            BiddingPackage.trang_thai.in_(target_statuses),
            BiddingPackage.created_at < cutoff_date
        )\
        .delete(synchronize_session=False)
    
    db.commit()
    
    return deleted_count