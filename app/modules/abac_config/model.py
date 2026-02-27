from typing import List, Optional
from datetime import datetime
from sqlalchemy import Integer, String, Boolean, Unicode, UnicodeText, Enum, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.infrastructure.database.database import Base
from app.core.utils.enum import AttributeType, PolicyEffect

class AbacAttribute(Base):
    __tablename__ = "attributes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attr_key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    attr_type: Mapped[AttributeType] = mapped_column(Enum(AttributeType), default=AttributeType.STRING, nullable=False)
    source_table: Mapped[Optional[str]] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Unicode(255))
    mapping_path: Mapped[Optional[str]] = mapped_column(String)

class AbacPolicy(Base):
    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(UnicodeText)
    target_resource: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    action: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    effect: Mapped[PolicyEffect] = mapped_column(Enum(PolicyEffect), default=PolicyEffect.ALLOW, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    condition_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())