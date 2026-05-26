import os
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

# --- IMPORT ---
# Sửa lại đường dẫn import nếu cần thiết theo cấu trúc dự án của bạn
from app.infrastructure.database.database import get_db
from app.modules.users.model import User
from app.modules.bidding.project.model import BiddingProject 
from app.core.security import get_current_user

# Import service mới
from app.integrations.microsoft.onedrive_service import onedrive_service

router = APIRouter(
    prefix="/onedrive",
    tags=["OneDrive Integration"]
)

class InitProjectRequest(BaseModel):
    project_id: int

# =================================================================
# 1. API LIST FILE & FOLDER (ĐÃ SỬA LỖI HIỂN THỊ)
# =================================================================

@router.get("/projects")
def get_root_projects(current_user: User = Depends(get_current_user)):
    """
    Lấy danh sách tất cả file/folder trong Root.
    """
    # 1. Gọi service để lấy list
    items = onedrive_service.list_files_in_folder(None) # None = Root
    
    # 2. [SỬA LỖI] KHÔNG LỌC NỮA - TRẢ VỀ HẾT
    # Code cũ lọc "projects = [x for x in items if folder...]" nên bị rỗng
    # Bây giờ trả về hết để thấy file PDF
    return {
        "source": "OneDrive Personal",
        "total": len(items),
        "data": items
    }

@router.get("/folder/{folder_id}")
def get_folder_content(folder_id: str, current_user: User = Depends(get_current_user)):
    """Lấy nội dung chi tiết của một folder bất kỳ"""
    items = onedrive_service.list_files_in_folder(folder_id)
    return {
        "current_folder_id": folder_id,
        "total_items": len(items),
        "data": items
    }

# =================================================================
# 2. INIT PROJECT & UPLOAD
# =================================================================

@router.post("/init-project")
def init_project_structure(
    payload: InitProjectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    project = db.query(BiddingProject).filter(BiddingProject.id == payload.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    result = onedrive_service.create_project_tree(project.name)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create OneDrive structure")

    return {"message": "Success", "data": result}

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    folder_id: str = Form(...),
    current_user: User = Depends(get_current_user)
):
    result = await onedrive_service.upload_file_with_security(file, folder_id)
    if not result:
        raise HTTPException(status_code=500, detail="Upload failed")
    return {"message": "Success", "file": result}

@router.get("/stats")
def get_drive_stats(folder_id: Optional[str] = None, current_user: User = Depends(get_current_user)):
    count = onedrive_service.count_files_recursive(folder_id)
    return {"folder_id": folder_id, "total_files_recursive": count}