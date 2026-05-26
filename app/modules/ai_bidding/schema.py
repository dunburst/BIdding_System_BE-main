# app/modules/ai_bidding/schema.py
from pydantic import BaseModel
from typing import Optional, List

class DraftingRequest(BaseModel):
    project_name: str
    reference_file: Optional[str] = None
    thread_id: Optional[str] = None         # Nếu null -> Tạo mới. Nếu có -> Resume.
    approved_outline: Optional[List[dict]] = None # Nếu có -> User đã duyệt dàn ý này.

class SearchRequest(BaseModel):
    query: str