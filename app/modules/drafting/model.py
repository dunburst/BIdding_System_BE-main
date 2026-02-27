from typing import Optional
from datetime import datetime
from sqlalchemy import Integer, String, Boolean, Unicode, UnicodeText, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.infrastructure.database.database import Base

class DocumentTemplate(Base):
    __tablename__ = "document_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    content: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    description: Mapped[Optional[str]] = mapped_column(Unicode(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class DocumentRegistry(Base):
    __tablename__ = "document_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_file: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    legal_level: Mapped[str] = mapped_column(String(50))
    legal_priority: Mapped[int] = mapped_column(Integer)
    promulgation_year: Mapped[int] = mapped_column(Integer)
    ingest_status: Mapped[str] = mapped_column(String(20))
    total_chunks: Mapped[int] = mapped_column(Integer, default=0)
    collection_name: Mapped[str] = mapped_column(String(100), default="legal_docs")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())