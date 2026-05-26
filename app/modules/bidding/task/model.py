from typing import List, Optional, TYPE_CHECKING
from datetime import datetime
from sqlalchemy import Integer, String, Unicode, UnicodeText, DateTime, ForeignKey, JSON, Enum, Boolean
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from app.infrastructure.database.database import Base
from app.core.utils.enum import TaskStatus, TaskPriority, TaskType, TaskTag, TaskAction, AssignmentType, SecurityLevel

if TYPE_CHECKING:
    from modules.users.model import User
    from modules.organization.model import OrganizationalUnit
    from modules.bidding.project.model import BiddingProject

# Templates
class BiddingProjectTemplate(Base):
    __tablename__ = "bidding_project_templates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_name: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    template_file: Mapped[Optional[str]] = mapped_column(Unicode(500))

class BiddingTaskTemplate(Base):
    __tablename__ = "bidding_task_templates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_name: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Unicode(1000))

class TemplateStructure(Base):
    __tablename__ = "template_structure"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_template_id: Mapped[int] = mapped_column(ForeignKey("bidding_project_templates.id"))
    task_template_id: Mapped[int] = mapped_column(ForeignKey("bidding_task_templates.id"))
    default_order: Mapped[int] = mapped_column(Integer, default=0)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    project_template: Mapped["BiddingProjectTemplate"] = relationship("BiddingProjectTemplate")
    task_template: Mapped["BiddingTaskTemplate"] = relationship("BiddingTaskTemplate")

# Main Task Models
class BiddingTask(Base):
    __tablename__ = "bidding_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bidding_project_id: Mapped[int] = mapped_column(ForeignKey("bidding_project.id"))
    parent_task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bidding_task.id"))
    template_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bidding_task_templates.id"), nullable=True)
    
    task_name: Mapped[str] = mapped_column(Unicode(255))
    assignee_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    reviewer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.OPEN)
    priority: Mapped[TaskPriority] = mapped_column(Enum(TaskPriority), default=TaskPriority.MEDIUM)
    task_type: Mapped[TaskType] = mapped_column(Enum(TaskType), default=TaskType.DRAFTING, nullable=False)
    tag: Mapped[Optional[TaskTag]] = mapped_column(Enum(TaskTag), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(UnicodeText, nullable=True)
    attachment_url: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list, nullable=True)
    submission_data: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list, nullable=True)
    source_type: Mapped[Optional[str]] = mapped_column(String(50))
    ai_reasoning: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    draft_content: Mapped[Optional[str]] = mapped_column(UnicodeText, nullable=True)

    # Relationships
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])
    project: Mapped["BiddingProject"] = relationship("BiddingProject", back_populates="tasks")
    assignments: Mapped[List["TaskAssignment"]] = relationship("TaskAssignment", back_populates="task", cascade="all, delete-orphan")
    parent: Mapped[Optional["BiddingTask"]] = relationship("BiddingTask", remote_side=[id], back_populates="sub_tasks")
    sub_tasks: Mapped[List["BiddingTask"]] = relationship("BiddingTask", back_populates="parent", cascade="all, delete-orphan")
    comments: Mapped[List["TaskComment"]] = relationship("TaskComment", back_populates="task", cascade="all, delete-orphan", order_by="TaskComment.created_at.asc()")
    histories: Mapped[List["TaskHistory"]] = relationship("TaskHistory", back_populates="task", cascade="all, delete-orphan")
    assignee: Mapped[Optional["User"]] = relationship("User", foreign_keys=[assignee_id])
    reviewer: Mapped[Optional["User"]] = relationship("User", foreign_keys=[reviewer_id])
    template: Mapped[Optional["BiddingTaskTemplate"]] = relationship("BiddingTaskTemplate")

class TaskAssignment(Base):
    __tablename__ = "task_assignments"

    assignment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("bidding_task.id"), nullable=False)
    assigned_unit_id: Mapped[Optional[int]] = mapped_column(ForeignKey("organizational_units.unit_id"))
    assigned_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.user_id"))
    required_role: Mapped[Optional[str]] = mapped_column(String(50))
    required_min_security: Mapped[SecurityLevel] = mapped_column(Enum(SecurityLevel), default=SecurityLevel.PUBLIC, nullable=False)
    assignment_type: Mapped[AssignmentType] = mapped_column(Enum(AssignmentType), default=AssignmentType.MAIN)
    is_accepted: Mapped[bool] = mapped_column(Boolean, default=False)

    task: Mapped["BiddingTask"] = relationship("BiddingTask", back_populates="assignments")
    unit: Mapped[Optional["OrganizationalUnit"]] = relationship("OrganizationalUnit")
    user: Mapped[Optional["User"]] = relationship("User")

class TaskComment(Base):
    __tablename__ = "task_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("bidding_task.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("task_comments.id"), nullable=True)
    content: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    task: Mapped["BiddingTask"] = relationship("BiddingTask", back_populates="comments")
    author: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    parent: Mapped[Optional["TaskComment"]] = relationship("TaskComment", remote_side=[id], back_populates="replies")
    replies: Mapped[List["TaskComment"]] = relationship("TaskComment", back_populates="parent", cascade="all, delete-orphan")

class TaskHistory(Base):
    __tablename__ = "task_histories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("bidding_task.id", ondelete="CASCADE"), nullable=False)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    action: Mapped[TaskAction] = mapped_column(Enum(TaskAction), nullable=False)
    old_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    new_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    detail: Mapped[Optional[str]] = mapped_column(UnicodeText, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    task: Mapped["BiddingTask"] = relationship("BiddingTask", back_populates="histories")
    actor: Mapped[Optional["User"]] = relationship("User", foreign_keys=[actor_id])