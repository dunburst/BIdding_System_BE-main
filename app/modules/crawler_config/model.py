from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Integer, String, Boolean, UnicodeText, Numeric, JSON, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.dialects.mssql import NVARCHAR
from app.infrastructure.database.database import Base

class CrawlSchedule(Base):
    __tablename__ = "crawl_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_url: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(NVARCHAR(None), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class CrawlRule(Base):
    __tablename__ = "crawl_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_name: Mapped[str] = mapped_column(UnicodeText(255), nullable=False)
    business_field: Mapped[Optional[str]] = mapped_column(UnicodeText(100), nullable=True)
    keywords_include: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=True)
    keywords_exclude: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=True)
    min_budget: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 0), nullable=True)
    max_budget: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 0), nullable=True)
    locations: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=True)
    investor: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=True)
    commune: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=1, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class CrawlLog(Base):
    __tablename__ = "crawl_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[Optional[int]] = mapped_column(ForeignKey("crawl_rules.id"))
    start_time: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(50))
    packages_found: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    packages_failed: Mapped[int] = mapped_column(Integer, default=0)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    rule: Mapped["CrawlRule"] = relationship("CrawlRule")