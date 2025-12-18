from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
from typing import List
from sqlalchemy.orm import Session

from database import get_db
from models import User, SecurityLevel
from utils.security import get_current_user # Hàm lấy user hiện tại của bạn
from .service import drive_service

router = APIRouter(
    prefix="/drive",
    tags=["Google Drive Security"]
)

# API Upload file có chọn mức độ mật
@router.post("/upload-secure")
async def upload_secure_file(
    file: UploadFile = File(...),
    security_level: SecurityLevel = Form(SecurityLevel.PUBLIC), # Chọn mức độ từ Dropdown
    current_user: User = Depends(get_current_user), # Chỉ user đăng nhập mới được up
    db: Session = Depends(get_db)
):
    # Logic mở rộng: Chỉ Giám đốc mới được up file Secret (Tùy bạn)
    # if security_level == SecurityLevel.SECRET and current_user.role != "ADMIN":
    #     raise HTTPException(403, "Bạn không đủ quyền upload file mật")

    # Gọi service upload
    # Lưu ý: Convert Enum sang int (security_level.value)
    result = drive_service.upload_file_with_security(file, security_level.value)
    
    if not result:
        raise HTTPException(500, "Lỗi upload lên Google Drive")
        
    return {
        "message": "Upload thành công",
        "file_info": result,
        "security_tag": security_level
    }

# API Xem danh sách (Đã phân quyền)
@router.get("/list-secure")
def get_my_files(
    current_user: User = Depends(get_current_user) # Bắt buộc phải đăng nhập
):
    """
    Chỉ trả về những file có security_level <= security_clearance của User
    """
    # 1. Lấy tất cả file từ Drive
    all_files = drive_service.list_files_with_metadata()
    
    # 2. Lấy quyền của user (VD: Nhân viên=1, Giám đốc=4)
    user_clearance = current_user.security_clearance.value 
    
    visible_files = []
    
    # 3. Lọc file
    for file in all_files:
        # Lấy tag bảo mật của file (mặc định là 1 - Public nếu không có tag)
        props = file.get('properties', {})
        file_level = int(props.get('security_level', 1))
        
        # LOGIC QUAN TRỌNG NHẤT:
        # Nếu quyền user >= độ mật của file thì mới cho xem
        if user_clearance >= file_level:
            visible_files.append({
                "id": file['id'],
                "name": file['name'],
                "link": file['webViewLink'],
                "level": file_level, # Trả về để Frontend hiện màu (Đỏ=Mật, Xanh=Thường)
                "access": "GRANTED"
            })
    
    return {
        "user_role": current_user.role,
        "user_clearance": user_clearance,
        "total_files_on_drive": len(all_files),
        "visible_files_count": len(visible_files),
        "data": visible_files
    }