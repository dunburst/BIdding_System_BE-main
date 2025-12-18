from fastapi import APIRouter, HTTPException
from .service import drive_service

router = APIRouter(
    prefix="/drive",
    tags=["Google Drive MCP"]
)

@router.get("/list")
def get_all_files():
    """
    API xem danh sách file trong thư mục Google Drive cấu hình
    """
    files = drive_service.list_files()
    
    if files is None:
        raise HTTPException(status_code=500, detail="Lỗi kết nối Google Drive")
        
    return {
        "success": True,
        "total": len(files),
        "folder_id": drive_service.SHARED_FOLDER_ID if hasattr(drive_service, 'SHARED_FOLDER_ID') else "Default",
        "data": files
    }