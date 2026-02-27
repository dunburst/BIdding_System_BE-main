from typing import Optional, TYPE_CHECKING
from sqlalchemy import Integer, String, Boolean, Text, Enum, ForeignKey, Unicode, UnicodeText
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.infrastructure.database.database import Base
from app.core.utils.enum import UserRole, SecurityLevel

if TYPE_CHECKING:
    from modules.organization.model import OrganizationalUnit, AuditLog

class User(Base):
    __tablename__ = "users"
    
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=True)
    full_name: Mapped[str] = mapped_column(UnicodeText(100))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.ENGINEER, nullable=False)
    status: Mapped[bool] = mapped_column(Boolean, default=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # ABAC fields
    org_unit_id: Mapped[Optional[int]] = mapped_column(ForeignKey("organizational_units.unit_id"))
    job_title: Mapped[Optional[str]] = mapped_column(Unicode(100))
    security_clearance: Mapped[SecurityLevel] = mapped_column(Enum(SecurityLevel), default=SecurityLevel.PUBLIC, nullable=False)
    auth_provider: Mapped[str] = mapped_column(String(50), default="local")

    # Relationships (Sử dụng String "OrganizationalUnit" để tránh import chéo)
    org_unit: Mapped[Optional["OrganizationalUnit"]] = relationship("OrganizationalUnit", foreign_keys=[org_unit_id], back_populates="members")
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="user")