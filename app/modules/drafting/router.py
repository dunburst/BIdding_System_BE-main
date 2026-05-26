from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import List, Optional

from app.infrastructure.database.database import get_db
from app.modules.users.model import User
from app.modules.bidding.task.model import BiddingTask
from app.core.security import get_current_user
from app.modules.drafting.schema import TemplateResponse, AiAssistRequest, AiAssistResponse, SaveDraftRequest, UserDraftResponse
import app.modules.drafting.crud as drafting_crud
import app.integrations.ai.agent.drafting as drafting_service

router = APIRouter(
    prefix="/drafting",
    tags=["Drafting Workspace"]
)

# 1. Lấy danh sách Template (Theo category: HR, TECH...)
@router.get("/templates", response_model=List[TemplateResponse])
def get_templates(
    category: Optional[str] = None, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return drafting_crud.get_templates(db, category)

# 2. AI Hỗ trợ soạn thảo
@router.post("/ai-assist", response_model=AiAssistResponse)
def ai_assist(
    payload: AiAssistRequest,
    current_user: User = Depends(get_current_user)
):
    result_html = drafting_service.process_drafting_with_ai(
        prompt=payload.prompt,
        current_html=payload.current_content,
        context=payload.task_context or ""
    )
    return {"generated_content": result_html}

# 3. Lưu bản nháp vào Task
@router.post("/task/{task_id}/save", response_model=dict)
def save_draft(
    task_id: int,
    payload: SaveDraftRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    task = drafting_crud.save_task_draft(db, task_id, payload.content)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Draft saved successfully", "updated_at": str(task.updated_at if hasattr(task, 'updated_at') else "")}

# 4. Lấy bản nháp đã lưu
@router.get("/task/{task_id}/load", response_model=dict)
def load_draft(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Sửa truy vấn dùng BiddingTask
    task = db.query(BiddingTask).filter(BiddingTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {"draft_content": task.draft_content}

# 5. Lấy danh sách tất cả bản nháp của user đang đăng nhập
@router.get("/my-drafts", response_model=List[UserDraftResponse])
def get_my_drafts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Truyền user_id của người đang đăng nhập vào CRUD
    drafts = drafting_crud.get_user_drafts(db, user_id=current_user.user_id)
    return drafts