from typing import Optional, TYPE_CHECKING
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Integer, String, Unicode, UnicodeText, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from app.infrastructure.database.database import Base

if TYPE_CHECKING:
    from modules.bidding.package.model import BiddingPackage

class BiddingReqFinancialAdmin(Base):
    __tablename__ = "bidding_req_financial_admin"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hsmt_id: Mapped[int] = mapped_column(ForeignKey("bidding_packages.hsmt_id"), unique=True, nullable=False)
    bid_validity_days: Mapped[Optional[int]] = mapped_column(Integer)
    bid_security_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    bid_security_duration: Mapped[Optional[int]] = mapped_column(Integer)
    submission_fee: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    contract_duration_text: Mapped[Optional[str]] = mapped_column(Unicode(255))
    req_revenue_avg: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    req_working_capital: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    req_similar_contract_qty: Mapped[Optional[int]] = mapped_column(Integer)
    req_similar_contract_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    req_similar_contract_desc: Mapped[Optional[str]] = mapped_column(UnicodeText)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    package: Mapped["BiddingPackage"] = relationship("BiddingPackage", back_populates="financial_req")

class BiddingReqPersonnel(Base):
    __tablename__ = "bidding_req_personnel"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hsmt_id: Mapped[int] = mapped_column(ForeignKey("bidding_packages.hsmt_id"), nullable=False)
    stt: Mapped[Optional[int]] = mapped_column(Integer)
    position_name: Mapped[Optional[str]] = mapped_column(Unicode(255))
    quantity: Mapped[Optional[int]] = mapped_column(Integer)
    min_exp_years: Mapped[Optional[int]] = mapped_column(Integer)
    qualification_req: Mapped[Optional[str]] = mapped_column(UnicodeText)
    similar_project_exp: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    package: Mapped["BiddingPackage"] = relationship("BiddingPackage", back_populates="personnel_reqs")

class BiddingReqEquipment(Base):
    __tablename__ = "bidding_req_equipment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hsmt_id: Mapped[int] = mapped_column(ForeignKey("bidding_packages.hsmt_id"), nullable=False)
    stt: Mapped[Optional[int]] = mapped_column(Integer)
    equipment_name: Mapped[Optional[str]] = mapped_column(Unicode(255))
    quantity: Mapped[Optional[int]] = mapped_column(Integer)
    specifications: Mapped[Optional[str]] = mapped_column(UnicodeText)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    package: Mapped["BiddingPackage"] = relationship("BiddingPackage", back_populates="equipment_reqs")