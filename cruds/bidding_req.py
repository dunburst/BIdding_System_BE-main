from sqlalchemy.orm import Session
from sqlalchemy import select
from models import BiddingPackage, BiddingReqFinancialAdmin, BiddingReqPersonnel, BiddingReqEquipment
from typing import List, Optional

# --- 1. FINANCIAL (1-1) ---
def get_financial_req_by_hsmt(db: Session, hsmt_id: int) -> Optional[BiddingReqFinancialAdmin]:
    """Lấy yêu cầu tài chính theo ID gói thầu (chỉ có 1 record)"""
    stmt = select(BiddingReqFinancialAdmin).where(BiddingReqFinancialAdmin.hsmt_id == hsmt_id)
    return db.scalar(stmt)

# --- 2. PERSONNEL (1-N) ---
def get_personnel_reqs_by_hsmt(db: Session, hsmt_id: int) -> List[BiddingReqPersonnel]:
    """Lấy danh sách toàn bộ nhân sự yêu cầu của 1 gói thầu"""
    stmt = select(BiddingReqPersonnel).where(BiddingReqPersonnel.hsmt_id == hsmt_id).order_by(BiddingReqPersonnel.stt)
    return list(db.scalars(stmt).all())

def get_personnel_req_detail(db: Session, req_id: int) -> Optional[BiddingReqPersonnel]:
    """Xem chi tiết 1 vị trí nhân sự cụ thể (theo ID dòng)"""
    stmt = select(BiddingReqPersonnel).where(BiddingReqPersonnel.id == req_id)
    return db.scalar(stmt)

# --- 3. EQUIPMENT (1-N) ---
def get_equipment_reqs_by_hsmt(db: Session, hsmt_id: int) -> List[BiddingReqEquipment]:
    """Lấy danh sách toàn bộ thiết bị yêu cầu của 1 gói thầu"""
    stmt = select(BiddingReqEquipment).where(BiddingReqEquipment.hsmt_id == hsmt_id).order_by(BiddingReqEquipment.stt)
    return list(db.scalars(stmt).all())

def get_equipment_req_detail(db: Session, req_id: int) -> Optional[BiddingReqEquipment]:
    """Xem chi tiết 1 thiết bị cụ thể"""
    stmt = select(BiddingReqEquipment).where(BiddingReqEquipment.id == req_id)
    return db.scalar(stmt)
def get_bidding_package_by_id(db: Session, hsmt_id: int) -> Optional[BiddingPackage]:
    """Lấy thông tin chung của gói thầu từ bảng BiddingPackage"""
    stmt = select(BiddingPackage).where(BiddingPackage.hsmt_id == hsmt_id)
    return db.scalar(stmt)