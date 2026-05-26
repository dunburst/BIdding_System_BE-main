from typing import List, Optional, TYPE_CHECKING
from datetime import datetime
from sqlalchemy import Integer, String, Boolean, ForeignKey, Unicode, UnicodeText, Enum, DateTime, JSON
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from app.infrastructure.database.database import Base
from app.core.utils.enum import UnitType

if TYPE_CHECKING:
    from app.modules.users.model import User

class OrganizationalUnit(Base):
    __tablename__ = "organizational_units"

    unit_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    unit_name: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    unit_code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    parent_unit_id: Mapped[Optional[int]] = mapped_column(ForeignKey("organizational_units.unit_id"))
    unit_type: Mapped[UnitType] = mapped_column(Enum(UnitType), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(UnicodeText)
    manager_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.user_id"), nullable=True)

    # Relationships
    parent: Mapped[Optional["OrganizationalUnit"]] = relationship("OrganizationalUnit", remote_side=[unit_id], back_populates="children")
    children: Mapped[List["OrganizationalUnit"]] = relationship("OrganizationalUnit", back_populates="parent")
    manager: Mapped[Optional["User"]] = relationship("User", foreign_keys=[manager_id])
    members: Mapped[List["User"]] = relationship("User", foreign_keys="[User.org_unit_id]", back_populates="org_unit")

class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.user_id"))
    action: Mapped[str] = mapped_column(Unicode(255))
    entity_table: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[Optional[int]] = mapped_column(Integer)
    old_value: Mapped[Optional[dict]] = mapped_column(JSON)
    new_value: Mapped[Optional[dict]] = mapped_column(JSON)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="audit_logs")