from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
from fastapi.responses import StreamingResponse
from typing import List, Optional
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models import User, SecurityLevel
from utils.security import get_current_user
from .service import drive_service
from utils.permission_service import get_user_allowed_tags

router = APIRouter(
    prefix="/drive",
    tags=["Google Drive Security"]
)

# --- SCHEMA MODEL ---
class TaskAssignmentRequest(BaseModel):
    project_id: str             
    task_type: str  # HR, LEGAL, TECH, FINANCE, DEVICE, CONTRACT, OTHER
    template_file_ids: List[str] 

# --- HELPER FUNCTION ---
def _get_folder_tag(folder_name: str) -> Optional[str]:
    """
    Hàm xác định Tag của folder dựa trên tên.
    Dùng để Frontend tự động mở folder tương ứng với loại công việc.
    """
    name_lower = folder_name.lower()
    
    # Mapping: Từ khóa (lowercase) -> TAG
    keywords = {
        "nhân sự": "HR",
        "pháp lý": "LEGAL",
        "biện pháp thi công": "TECH",
        "kỹ thuật": "TECH",
        "tài chính": "FINANCE",
        "máy móc": "DEVICE",
        "thiết bị": "DEVICE",
        "hợp đồng": "CONTRACT",
        "hợp đông": "CONTRACT",
        "khác": "OTHER"
    }
    
    for key, tag in keywords.items():
        if key in name_lower:
            return tag
            
    return None

# =================================================================
# 1. API LẤY DANH SÁCH DỰ ÁN (ROOT)
# =================================================================
@router.get("/projects")
def get_root_projects(current_user: User = Depends(get_current_user)):
    """Chỉ trả về danh sách các Folder dự án ở thư mục gốc"""
    all_items = drive_service.list_files_in_folder(None) # None = Root
    
    visible_items = []
    for item in all_items:
        # Chỉ lấy Folder
        if 'application/vnd.google-apps.folder' in item.get('mimeType', ''):
            visible_items.append({
                "id": item['id'], "name": item['name'], "type": "FOLDER",
                "link": item['webViewLink'], "access": "GRANTED"
            })
            
    return {"current_context": "ROOT_PROJECTS", "total": len(visible_items), "data": visible_items}

# =================================================================
# 2. API LẤY FILE TRONG 1 FOLDER CỤ THỂ (ĐÃ CẬP NHẬT TAG)
# =================================================================
@router.get("/folder/{folder_id}/me")
def get_folder_by_user(
    folder_id: str, 
    project_id: int, # <--- BẮT BUỘC THÊM: Để biết đang ở dự án nào
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db) # <--- Thêm DB Session
):
    """Lấy danh sách file/folder con và CHECK QUYỀN TAG"""
    
    # 1. Lấy thông tin từ Drive
    all_items = drive_service.list_files_in_folder(folder_id)
    
    # 2. Tính toán danh sách TAG mà user này được phép xem
    # Kết quả VD: {'FINANCE', 'LEGAL'}
    allowed_tags = get_user_allowed_tags(db, current_user, project_id)
    
    user_clearance = current_user.security_clearance.value 
    visible_items = []
    
    for item in all_items:
        # A. Xử lý FOLDER
        if 'application/vnd.google-apps.folder' in item.get('mimeType', ''):
            folder_tag = _get_folder_tag(item['name']) # VD: "Hồ sơ tài chính" -> "FINANCE"

            # --- LOGIC CHECK QUYỀN MỚI ---
            # Nếu folder có Tag (là folder nghiệp vụ) VÀ Tag đó không nằm trong danh sách được phép
            # -> Bỏ qua (Ẩn folder đó đi) hoặc đánh dấu "access": "DENIED"
            if folder_tag and folder_tag not in allowed_tags:
                # Cách 1: Ẩn luôn (User không biết sự tồn tại)
                continue 
                
                # Cách 2: Hiện nhưng khóa (nếu muốn)
                # item['access'] = "DENIED" 
            # -----------------------------

            visible_items.append({
                "id": item['id'], 
                "name": item['name'], 
                "type": "FOLDER",
                "link": item['webViewLink'], 
                "access": "GRANTED",
                "tag": folder_tag
            })
            continue

        # B. Xử lý FILE (Giữ nguyên logic cũ theo Security Level)
        props = item.get('properties', {})
        file_level = int(props.get('security_level', 1))
        
        if user_clearance >= file_level:
            visible_items.append({
                "id": item['id'], 
                "name": item['name'], 
                "type": "FILE",
                "mime_type": item.get('mimeType'),
                "link": item['webViewLink'], 
                "level": file_level, 
                "access": "GRANTED",
                "tag": None
            })
    
    return {
        "current_folder_id": folder_id, 
        "project_id": project_id,
        "total_items": len(visible_items), 
        "data": visible_items
    }
    
@router.get("/folder/{folder_id}")
def get_folder_content(folder_id: str, current_user: User = Depends(get_current_user)):
    """Lấy danh sách file/folder con trong folder_id kèm theo TAG phân loại"""
    all_items = drive_service.list_files_in_folder(folder_id)
    user_clearance = current_user.security_clearance.value 
    visible_items = []
    
    for item in all_items:
        # A. Folder con -> Luôn hiện & Tính toán Tag
        if 'application/vnd.google-apps.folder' in item.get('mimeType', ''):
            # Tự động gán tag dựa trên tên folder (VD: "Hồ sơ nhân sự" -> "HR")
            folder_tag = _get_folder_tag(item['name'])

            visible_items.append({
                "id": item['id'], 
                "name": item['name'], 
                "type": "FOLDER",
                "link": item['webViewLink'], 
                "access": "GRANTED",
                "tag": folder_tag  # <--- TRƯỜNG MỚI THÊM ĐỂ FRONTEND DÙNG
            })
            continue

        # B. File -> Check quyền
        props = item.get('properties', {})
        file_level = int(props.get('security_level', 1))
        
        if user_clearance >= file_level:
            visible_items.append({
                "id": item['id'], 
                "name": item['name'], 
                "type": "FILE",
                "mime_type": item.get('mimeType'),
                "link": item['webViewLink'], 
                "level": file_level, 
                "access": "GRANTED",
                "tag": None # File thì không có tag folder
            })
    
    return {"current_folder_id": folder_id, "total_items": len(visible_items), "data": visible_items}

# =================================================================
# 3. CÁC API NGHIỆP VỤ KHÁC
# =================================================================

# Khởi tạo dự án
@router.post("/init-project")
def create_project_structure(
    project_name: str = Form(...),
    current_user: User = Depends(get_current_user)
):
    result = drive_service.create_project_tree(project_name)
    if not result: raise HTTPException(500, "Lỗi tạo cấu trúc dự án")
    return {"message": "Tạo dự án thành công", "data": result}

# Giao việc & Clone file tự động
@router.post("/assign-task-files")
def provision_files_for_task(
    payload: TaskAssignmentRequest,
    current_user: User = Depends(get_current_user)
):
    result = drive_service.clone_files_for_task(
        payload.project_id, payload.task_type, payload.template_file_ids
    )
    if not result: raise HTTPException(500, "Lỗi khi cấp phát tài liệu (Không tìm thấy folder đích)")
    return {"message": "Đã copy tài liệu mẫu thành công", "data": result}

# Upload file thủ công
@router.post("/upload-secure")
async def upload_secure_file(
    file: UploadFile = File(...),
    folder_id: str = Form(None), 
    security_level: SecurityLevel = Form(SecurityLevel.PUBLIC),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    result = await drive_service.upload_file_with_security(file, folder_id, security_level.value)
    if not result: raise HTTPException(500, "Lỗi upload lên Google Drive")
    return {"message": "Upload thành công", "file_info": result}

# Cập nhật file
@router.put("/update/{file_id}")
async def update_drive_file(
    file_id: str,
    new_name: Optional[str] = Form(None),       # Sửa tên
    security_level: Optional[int] = Form(None), # Sửa level (VD: 1, 2, 3, 4)
    file: Optional[UploadFile] = File(None),    # Sửa nội dung (Option)
    current_user: User = Depends(get_current_user)
):
    """
    API sửa file đa năng:
    - Có thể chỉ sửa tên
    - Có thể chỉ sửa level
    - Có thể up file mới đè lên file cũ
    - Hoặc làm cả 3 cùng lúc
    """
    success = await drive_service.update_file(file_id, new_name, file, security_level)
    
    if not success:
        raise HTTPException(500, "Lỗi cập nhật file trên Google Drive")
        
    return {
        "message": "Cập nhật thành công",
        "updated_fields": {
            "name": new_name,
            "level": security_level,
            "content_updated": file is not None
        }
    }

# Tìm kiếm tài liệu kho (Cả File và Folder)
@router.get("/search-repo")
def search_repository(query: str, current_user: User = Depends(get_current_user)):
    flat_results = drive_service.search_files(query)
    
    item_map = {}
    for item in flat_results:
        is_folder = 'application/vnd.google-apps.folder' in item.get('mimeType', '')
        
        # Với kết quả tìm kiếm, ta cũng có thể gán tag nếu cần (nhưng ở đây giữ đơn giản)
        clean_item = {
            "id": item['id'],
            "name": item['name'],
            "type": "FOLDER" if is_folder else "FILE",
            "mime_type": item.get('mimeType'),
            "link": item['webViewLink'],
            "created_at": item.get('createdTime'),
            "parents": item.get('parents', []),
            "children": []
        }
        item_map[item['id']] = clean_item

    tree_roots = []
    for item_id, item in item_map.items():
        parent_id = item['parents'][0] if item['parents'] else None
        if parent_id and parent_id in item_map:
            item_map[parent_id]['children'].append(item)
        else:
            tree_roots.append(item)

    return {
        "query": query,
        "total_matches": len(flat_results),
        "tree_roots_count": len(tree_roots),
        "data": tree_roots
    }

# Clone file thủ công
@router.post("/clone-file")
def clone_file_to_project(
    source_file_id: str = Form(...), target_folder_id: str = Form(...),
    new_name: Optional[str] = Form(None), current_user: User = Depends(get_current_user)
):
    result = drive_service.copy_file(source_file_id, target_folder_id, new_name)
    if not result: raise HTTPException(500, "Lỗi khi copy file")
    return {"message": "Clone thành công", "file": result}

# Đóng gói dự án ZIP
@router.get("/package-zip/{folder_id}")
def download_folder_as_zip(folder_id: str, current_user: User = Depends(get_current_user)):
    zip_stream = drive_service.zip_folder(folder_id)
    if not zip_stream: raise HTTPException(404, "Không tìm thấy file để nén")
    return StreamingResponse(
        zip_stream, media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=Project_{folder_id}.zip"}
    )

# Xóa file
@router.delete("/delete/{file_id}")
def delete_drive_file(
    file_id: str,
    current_user: User = Depends(get_current_user)
):
    success = drive_service.delete_file(file_id)
    if not success:
        raise HTTPException(404, "Lỗi: File không tồn tại hoặc không thể xóa") 
    return {"message": "Đã chuyển file vào thùng rác thành công", "file_id": file_id}

# [API DỰ PHÒNG] Tìm Folder con theo Category
# (Giữ lại để tương thích nếu cần dùng sau này, nhưng Frontend hiện tại sẽ dùng Tag từ API trên)
@router.get("/project/{project_folder_id}/category-folder")
def get_project_category_folder(
    project_folder_id: str,
    category: str,
    current_user: User = Depends(get_current_user)
):
    FOLDER_MAPPING = {
        "HR": "nhân sự",             
        "LEGAL": "Pháp lý",          
        "TECH": "Biện pháp Thi công",
        "FINANCE": "tài chính",      
        "DEVICE": "máy móc",         
        "CONTRACT": "hợp đông",      
        "OTHER": "khác"              
    }
    
    keyword = FOLDER_MAPPING.get(category.upper())
    if not keyword:
        raise HTTPException(400, f"Không hỗ trợ danh mục: {category}")

    target_folder_id = drive_service.get_subfolder_id_by_name(project_folder_id, keyword)
    
    if not target_folder_id:
        raise HTTPException(404, f"Không tìm thấy folder cho danh mục {category} ({keyword})")
        
    return {"category": category, "folder_id": target_folder_id, "folder_keyword": keyword}