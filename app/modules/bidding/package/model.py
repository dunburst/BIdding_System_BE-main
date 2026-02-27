from typing import List, Optional, TYPE_CHECKING
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Integer, String, Unicode, UnicodeText, DateTime, ForeignKey, Text, Float, Numeric, Enum
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from app.infrastructure.database.database import Base
from app.core.utils.enum import PackageStatus

if TYPE_CHECKING:
    from modules.users.model import User
    from modules.bidding.project.model import BiddingProject
    from modules.bidding.result.model import BiddingResult
    from modules.bidding.requirement.model import BiddingReqFinancialAdmin, BiddingReqPersonnel, BiddingReqEquipment

class BiddingPackage(Base):
    __tablename__ = "bidding_packages"
    
    hsmt_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bidding_project.id"))
    nguoi_duyet_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    
    # Thông tin cơ bản
    ma_tbmt: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    phien_ban_thay_doi: Mapped[str] = mapped_column(String(10), default='00')
    ngay_dang_tai: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ma_khlcnt: Mapped[str] = mapped_column(String(20))
    phan_loai_khlcnt: Mapped[Optional[str]] = mapped_column(Unicode(100), nullable=True)
    ten_du_an: Mapped[str] = mapped_column(Unicode(500))
    
    # Thông tin gói thầu
    quy_trinh_ap_dung: Mapped[Optional[str]] = mapped_column(Unicode(255), nullable=True)
    ten_goi_thau: Mapped[str] = mapped_column(Unicode(500), nullable=False)
    chu_dau_tu: Mapped[str] = mapped_column(Unicode(255))
    chi_tiet_nguon_von: Mapped[Optional[str]] = mapped_column(UnicodeText, nullable=True)
    linh_vuc: Mapped[str] = mapped_column(Unicode(50))
    hinh_thuc_lua_chon_nha_thau: Mapped[Optional[str]] = mapped_column(Unicode(255), nullable=True)
    loai_hop_dong: Mapped[Optional[str]] = mapped_column(Unicode(100), nullable=True)
    trong_nuoc_hoac_quoc_te: Mapped[Optional[str]] = mapped_column(Unicode(255), nullable=True)
    phuong_thuc_lua_chon_nha_thau: Mapped[Optional[str]] = mapped_column(Unicode(255), nullable=True)
    thoi_gian_thuc_hien_goi_thau: Mapped[Optional[str]] = mapped_column(Unicode(100), nullable=True)
    goi_thau_co_nhieu_phan_lo: Mapped[Optional[str]] = mapped_column(Unicode(255), nullable=True)
    
    # Cách thức dự thầu
    hinh_thuc_du_thau: Mapped[Optional[str]] = mapped_column(Unicode(100), nullable=True)
    dia_diem_phat_hanh_e_hsmt: Mapped[Optional[str]] = mapped_column(UnicodeText, nullable=True)
    chi_phi_nop: Mapped[Optional[float]] = mapped_column(Numeric(30, 2), nullable=True)
    dia_diem_nhan_e_hsdt: Mapped[Optional[str]] = mapped_column(UnicodeText, nullable=True)
    dia_diem_thuc_hien_goi_thau: Mapped[Optional[str]] = mapped_column(UnicodeText, nullable=True)
    
    # Thông tin dự thầu
    thoi_diem_dong_thau: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    thoi_diem_mo_thau: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    dia_diem_mo_thau: Mapped[Optional[str]] = mapped_column(UnicodeText, nullable=True)
    hieu_luc_hsdt: Mapped[Optional[str]] = mapped_column(Unicode(100), nullable=True)
    so_tien_dam_bao_du_thau: Mapped[Optional[float]] = mapped_column(Numeric(30, 2), nullable=True)
    hinh_thuc_dam_bao_du_thau: Mapped[Optional[str]] = mapped_column(UnicodeText, nullable=True)
    loai_cong_trinh: Mapped[Optional[str]] = mapped_column(UnicodeText, nullable=True)

    # Quyết định phê duyệt
    so_quyet_dinh_phe_duyet: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ngay_phe_duyet: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    co_quan_ban_hanh_quyet_dinh: Mapped[Optional[str]] = mapped_column(Unicode(255), nullable=True)
    quyet_dinh_phe_duyet: Mapped[Optional[str]] = mapped_column(UnicodeText, nullable=True)
    
    duong_dan_goi_thau: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trang_thai: Mapped[PackageStatus] = mapped_column(Enum(PackageStatus), default=PackageStatus.NEW, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    project: Mapped["BiddingProject"] = relationship("BiddingProject", back_populates="packages")
    nguoi_duyet: Mapped[Optional["User"]] = relationship("User", foreign_keys=[nguoi_duyet_id])
    files: Mapped[List["BiddingPackageFile"]] = relationship("BiddingPackageFile", back_populates="package", cascade="all, delete-orphan")
    result: Mapped[Optional["BiddingResult"]] = relationship("BiddingResult", back_populates="package", uselist=False, cascade="all, delete-orphan")
    
    financial_req: Mapped[Optional["BiddingReqFinancialAdmin"]] = relationship("BiddingReqFinancialAdmin", back_populates="package", uselist=False, cascade="all, delete-orphan")
    personnel_reqs: Mapped[List["BiddingReqPersonnel"]] = relationship("BiddingReqPersonnel", back_populates="package", cascade="all, delete-orphan")
    equipment_reqs: Mapped[List["BiddingReqEquipment"]] = relationship("BiddingReqEquipment", back_populates="package", cascade="all, delete-orphan")

class BiddingPackageFile(Base):
    __tablename__ = "bidding_package_files"
    
    file_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hsmt_id: Mapped[int] = mapped_column(Integer, ForeignKey("bidding_packages.hsmt_id"))
    file_name: Mapped[str] = mapped_column(Unicode(255))
    file_type: Mapped[str] = mapped_column(String(100))
    upload_date: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    file_path: Mapped[str] = mapped_column(String(500))
    
    package: Mapped["BiddingPackage"] = relationship("BiddingPackage", back_populates="files")