from typing import List, Optional, TYPE_CHECKING
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Integer, String, Unicode, UnicodeText, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from app.infrastructure.database.database import Base

if TYPE_CHECKING:
    from modules.bidding.package.model import BiddingPackage

class BiddingResult(Base):
    __tablename__ = "bidding_results"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hsmt_id: Mapped[int] = mapped_column(ForeignKey("bidding_packages.hsmt_id"), unique=True)
    result_status: Mapped[Optional[str]] = mapped_column(Unicode(255))
    posting_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    approved_budget: Mapped[Optional[Decimal]] = mapped_column(Numeric(30,2))
    package_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(30,2))
    approval_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    approving_agency: Mapped[Optional[str]] = mapped_column(Unicode(500))
    decision_number: Mapped[Optional[str]] = mapped_column(String(100))
    decision_link: Mapped[Optional[str]] = mapped_column(String(500))
    ehsdt_report_link: Mapped[Optional[str]] = mapped_column(String(500))
    bidding_result_text: Mapped[Optional[str]] = mapped_column(Unicode(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    package: Mapped["BiddingPackage"] = relationship("BiddingPackage", back_populates="result")
    winners: Mapped[List["BiddingResultWinner"]] = relationship("BiddingResultWinner", back_populates="result", cascade="all, delete-orphan")
    failed_bidders: Mapped[List["BiddingResultFailed"]] = relationship("BiddingResultFailed", back_populates="result", cascade="all, delete-orphan")
    items: Mapped[List["BiddingResultItem"]] = relationship("BiddingResultItem", back_populates="result", cascade="all, delete-orphan")

class BiddingResultWinner(Base):
    __tablename__ = "bidding_results_winners"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("bidding_results.id"))
    bidder_code: Mapped[Optional[str]] = mapped_column(String(50))
    tax_code: Mapped[Optional[str]] = mapped_column(String(50))
    bidder_name: Mapped[Optional[str]] = mapped_column(Unicode(1000))
    role: Mapped[Optional[str]] = mapped_column(Unicode(255))
    bid_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 2))
    corrected_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 2))
    evaluated_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 2))
    winning_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 2))
    technical_score: Mapped[Optional[str]] = mapped_column(String(100))
    execution_time: Mapped[Optional[str]] = mapped_column(Unicode(500))
    contract_period: Mapped[Optional[str]] = mapped_column(Unicode(500))
    other_content: Mapped[Optional[str]] = mapped_column(UnicodeText)
    
    result: Mapped["BiddingResult"] = relationship("BiddingResult", back_populates="winners")

class BiddingResultFailed(Base):
    __tablename__ = "bidding_results_failed"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("bidding_results.id"))
    bidder_code: Mapped[Optional[str]] = mapped_column(String(50))
    bidder_name: Mapped[Optional[str]] = mapped_column(Unicode(1000))
    tax_code: Mapped[Optional[str]] = mapped_column(String(50))
    joint_venture_name: Mapped[Optional[str]] = mapped_column(Unicode(1000))
    reason: Mapped[Optional[str]] = mapped_column(UnicodeText)
    
    result: Mapped["BiddingResult"] = relationship("BiddingResult", back_populates="failed_bidders")

class BiddingResultItem(Base):
    __tablename__ = "bidding_results_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("bidding_results.id"))
    item_name: Mapped[Optional[str]] = mapped_column(Unicode(1000))
    model: Mapped[Optional[str]] = mapped_column(Unicode(500))
    brand: Mapped[Optional[str]] = mapped_column(Unicode(500))
    manufacturer: Mapped[Optional[str]] = mapped_column(Unicode(500))
    origin: Mapped[Optional[str]] = mapped_column(Unicode(255))
    year_of_manufacture: Mapped[Optional[str]] = mapped_column(Unicode(100))
    technical_specs: Mapped[Optional[str]] = mapped_column(UnicodeText)
    
    result: Mapped["BiddingResult"] = relationship("BiddingResult", back_populates="items")