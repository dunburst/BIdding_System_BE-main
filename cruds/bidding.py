# cruds/bidding.py
from sqlalchemy.orm import Session
from models import BiddingPackage, BiddingPackageFile

# 1. Lấy danh sách gói thầu (có phân trang)
def get_all_bidding_packages(db: Session, skip: int = 0, limit: int = 100):
    return db.query(BiddingPackage).order_by(BiddingPackage.created_at.desc()).offset(skip).limit(limit).all()

# 2. Lấy chi tiết gói thầu theo ID
def get_bidding_package_by_id(db: Session, hsmt_id: int):
    return db.query(BiddingPackage).filter(BiddingPackage.hsmt_id == hsmt_id).first()

# 3. Lấy danh sách file theo ID gói thầu
def get_files_by_package_id(db: Session, hsmt_id: int):
    return db.query(BiddingPackageFile).filter(BiddingPackageFile.hsmt_id == hsmt_id).all()