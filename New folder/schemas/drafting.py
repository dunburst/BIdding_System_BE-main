from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# --- TEMPLATE SCHEMAS ---
class TemplateBase(BaseModel):
    title: str
    content: str # HTML content
    category: str
    description: Optional[str] = None

class TemplateCreate(TemplateBase):
    pass

class TemplateResponse(TemplateBase):
    id: int
    is_active: bool

    class Config:
        from_attributes = True # Pydantic v2 dùng from_attributes thay cho orm_mode

# --- AI & DRAFTING SCHEMAS ---
class AiAssistRequest(BaseModel):
    prompt: str             # Yêu cầu của user (VD: "Viết đoạn mở bài...")
    current_content: str    # Nội dung HTML hiện tại trong editor
    task_context: Optional[str] = None # Tên dự án/task để AI hiểu ngữ cảnh

class AiAssistResponse(BaseModel):
    generated_content: str  # HTML trả về

class SaveDraftRequest(BaseModel):
    content: str # Nội dung HTML cần lưu
    
# --- THÊM CLASS NÀY ---
class UserDraftResponse(BaseModel):
    id: int              # ID của Task
    task_name: str            # Tên của Task (giả sử model BiddingTask có trường name)
    # draft_content: Optional[str] = None

    class Config:
        from_attributes = True