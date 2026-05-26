from pydantic import BaseModel, Field, validator
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum

# Import Enum từ model gốc (giả sử bạn để file model là models.py)
from app.core.utils.enum import TaskStatus, AssignmentType, TaskPriority, TaskType, TaskTag, TaskAction


# Định nghĩa Schema nhỏ để lấy tên
class SimpleUser(BaseModel):
    user_id: int
    full_name: str
    avatar_url: Optional[str] = None
    class Config:
        from_attributes = True

class SimpleUnit(BaseModel):
    unit_name: str
    class Config:
        from_attributes = True
        
class SubmissionFile(BaseModel):
    file_id: str
    name: str
    url: str
    download_url: Optional[str] = None
    uploaded_by: int
    uploaded_name: Optional[str] = None
    uploaded_at: str
    comment: Optional[str] = None
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
    # Model TaskAssignment có relationship 'user' và 'unit'
    user: Optional[SimpleUser] = None 
    unit: Optional[SimpleUnit] = None

    class Config:
        from_attributes = True

# ==========================================
# 1. SCHEMA CHO COMMENT (Thêm mới)
# ==========================================
class TaskCommentBase(BaseModel):
    content: str

class TaskCommentCreate(TaskCommentBase):
    parent_id: Optional[int] = None # Nếu có thì là reply, không thì là comment gốc
    
class TaskCommentUpdate(BaseModel):
    content: str

# Schema hiển thị thông tin người comment (để FE hiển thị avatar/tên)
class CommentAuthorInfo(BaseModel):
    user_id: int
    full_name: str
    avatar_url: Optional[str] = None
    
    class Config:
        from_attributes = True

class TaskCommentResponse(TaskCommentBase):
    id: int
    task_id: int
    created_at: datetime
    author: CommentAuthorInfo
    
    # Đệ quy: Danh sách câu trả lời
    replies: List['TaskCommentResponse'] = [] 

    class Config:
        from_attributes = True

# Kích hoạt đệ quy
TaskCommentResponse.update_forward_refs()
# --- 2. SCHEMAS CHO TASK ---
class TaskBase(BaseModel):
    task_name: str
    deadline: Optional[datetime] = None
    status: TaskStatus = TaskStatus.OPEN
    # Thay đổi is_milestone -> priority
    priority: TaskPriority = TaskPriority.MEDIUM
    # --- THÊM TRƯỜNG MỚI ---
    task_type: TaskType = TaskType.DRAFTING
    # <--- THÊM MỚI TRƯỜNG TAG TẠI ĐÂY
    tag: Optional[TaskTag] = None
    # --- [NEW] ---
    description: Optional[str] = None
    attachment_url: Optional[List[str]] = []
    # Chứa danh sách file nhân viên nộp bài
    submission_data: Optional[List[SubmissionFile]] = []
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
    # <--- THÊM MỚI: CHO PHÉP UPDATE TAG
    tag: Optional[TaskTag] = None
    # --- [NEW] ---
    description: Optional[str] = None
    attachment_url: Optional[List[str]] = []
    # BỔ SUNG: Cho phép gửi kèm danh sách assignments mới để thay thế danh sách cũ
    assignments: Optional[List[TaskAssignmentCreate]] = None

# --- SCHEMA HIỂN THỊ (QUAN TRỌNG: Cấu trúc cây) ---
class TaskResponse(TaskBase):
    id: int
    bidding_project_id: int
    parent_task_id: Optional[int] = None
    assignee_id: Optional[int] = None
    reviewer_id: Optional[int] = None
    # [NEW]
    created_at: datetime
    # <--- THÊM DÒNG NÀY:
    project_name: Optional[str] = None
    # Danh sách phân công
    assignments: List[TaskAssignmentResponse] = []
    
    # Đệ quy: Task con
    sub_tasks: List['TaskResponse'] = [] 

    class Config:
        from_attributes = True

# Cần thiết cho Pydantic xử lý đệ quy
TaskResponse.update_forward_refs()

# Định nghĩa Schema nhỏ cho Assignment chỉ lấy Unit (để tiết kiệm dữ liệu)
class AssignmentLite(BaseModel):
    unit: Optional[SimpleUnit] = None
    
    class Config:
        from_attributes = True

# --- [MỚI] SCHEMA RÚT GỌN CHO DANH SÁCH ---
class TaskListResponse(BaseModel):
    id: int
    task_name: str
    project_name: Optional[str] = None
    task_type: Optional[TaskType] = None
    deadline: Optional[datetime] = None
    status: TaskStatus
    # [THÊM MỚI] Thông tin người/phòng phụ trách    # Người thực hiện chính
    assignments: List[TaskAssignmentResponse] = []       # Danh sách phòng ban tham gia
    
    # Vẫn cần sub_tasks để hiển thị cây thư mục (nếu dùng endpoint /user/me)
    sub_tasks: List['TaskListResponse'] = []

    class Config:
        from_attributes = True

# Kích hoạt đệ quy cho schema mới
TaskListResponse.update_forward_refs()

# Schema hiển thị thông tin người thao tác
class ActorSimple(BaseModel):
    user_id: int
    full_name: str
    avatar_url: Optional[str] = None
    class Config:
        from_attributes = True

class TaskHistoryResponse(BaseModel):
    id: int
    action: TaskAction
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    detail: Optional[str] = None
    created_at: Optional[datetime] = None
    actor: Optional[ActorSimple] = None
    # [THÊM MỚI] Cờ để FE nhận biết đây là bước tiếp theo
    is_future: bool = False

    class Config:
        from_attributes = True