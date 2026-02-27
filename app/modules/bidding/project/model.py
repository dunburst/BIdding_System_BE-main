from typing import List, Optional, TYPE_CHECKING
from datetime import datetime
from sqlalchemy import Integer, String, Unicode, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from app.infrastructure.database.database import Base

if TYPE_CHECKING:
    from modules.users.model import User
    from modules.bidding.package.model import BiddingPackage
    from modules.bidding.task.model import BiddingTask

class BiddingProject(Base):
    __tablename__ = "bidding_project"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"))
    bid_team_leader_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.user_id"))
    name: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    status: Mapped[Optional[str]] = mapped_column(String(50))
    drive_folder_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # String relationships
    packages: Mapped[List["BiddingPackage"]] = relationship("BiddingPackage", back_populates="project")
    tasks: Mapped[List["BiddingTask"]] = relationship("BiddingTask", back_populates="project", cascade="all, delete-orphan")
    host: Mapped["User"] = relationship("User", foreign_keys=[host_id])
    team_leader: Mapped[Optional["User"]] = relationship("User", foreign_keys=[bid_team_leader_id])
    submit_logs: Mapped[List["BidSubmitLog"]] = relationship("BidSubmitLog", back_populates="project", cascade="all, delete-orphan")

class BidSubmitLog(Base):
    __tablename__ = "bid_submit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bidding_project_id: Mapped[int] = mapped_column(ForeignKey("bidding_project.id"))
    snapshot_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    snapshot_data: Mapped[Optional[dict]] = mapped_column(JSON)
    archive_file_path: Mapped[Optional[str]] = mapped_column(Unicode(500))
    file_checksum: Mapped[Optional[str]] = mapped_column(String(64))

    project: Mapped["BiddingProject"] = relationship("BiddingProject", back_populates="submit_logs")