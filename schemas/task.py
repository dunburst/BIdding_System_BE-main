from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime
from enum import Enum

# Import Enum từ model gốc (giả sử bạn để file model là models.py)
from models import TaskStatus, AssignmentType, TaskPriority, TaskType

# --- 1. SCHEMAS CHO ASSIGNMENT ---
class TaskAssignmentBase(BaseModel):
    assigned_unit_id: Optional[int] = None
    assigned_user_id: Optional[int] = None
    assignment_type: AssignmentType = AssignmentType.MAIN
    required_role: Optional[str] = None
    required_min_security: Optional[int] = None

class TaskAssignmentCreate(TaskAssignmentBase):
    pass

class TaskAssignmentResponse(TaskAssignmentBase):
    assignment_id: int
    is_accepted: bool

    class Config:
        from_attributes = True

# --- 2. SCHEMAS CHO TASK ---
class TaskBase(BaseModel):
    task_name: str
    deadline: Optional[datetime] = None
    status: TaskStatus = TaskStatus.OPEN
    # Thay đổi is_milestone -> priority
    priority: TaskPriority = TaskPriority.MEDIUM
    # --- THÊM TRƯỜNG MỚI ---
    task_type: TaskType = TaskType.DRAFTING
    source_type: Optional[str] = None 

class TaskCreate(TaskBase):
    bidding_project_id: int
    parent_task_id: Optional[int] = None # Nếu có thì là sub-task, không thì là main task
    template_id: Optional[int] = None
    
    # Thêm 2 trường này để giao đích danh ngay khi tạo
    assignee_id: Optional[int] = None 
    reviewer_id: Optional[int] = None
    
    # Cho phép tạo luôn danh sách phân công khi tạo Task
    assignments: List[TaskAssignmentCreate] = []

class TaskUpdate(BaseModel):
    task_name: Optional[str] = None
    deadline: Optional[datetime] = None
    status: Optional[TaskStatus] = None
    assignee_id: Optional[int] = None
    reviewer_id: Optional[int] = None 
    source_type: Optional[str] = None
    # Thêm update priority
    priority: Optional[TaskPriority] = None
    # --- THÊM VÀO ĐÂY (Optional để không bắt buộc gửi lên khi update cái khác) ---
    task_type: Optional[TaskType] = None
    # BỔ SUNG: Cho phép gửi kèm danh sách assignments mới để thay thế danh sách cũ
    assignments: Optional[List[TaskAssignmentCreate]] = None

# --- SCHEMA HIỂN THỊ (QUAN TRỌNG: Cấu trúc cây) ---
class TaskResponse(TaskBase):
    id: int
    bidding_project_id: int
    parent_task_id: Optional[int] = None
    assignee_id: Optional[int] = None
    reviewer_id: Optional[int] = None
    # Danh sách phân công
    assignments: List[TaskAssignmentResponse] = []
    
    # Đệ quy: Task con
    sub_tasks: List['TaskResponse'] = [] 

    class Config:
        from_attributes = True

# Cần thiết cho Pydantic xử lý đệ quy
TaskResponse.update_forward_refs()