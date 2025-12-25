from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
from fastapi.responses import StreamingResponse
from typing import List, Optional
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models import User, SecurityLevel
from utils.security import get_current_user
from .service import drive_service
from utils.permission_service import get_user_allowed_tags_with_name

router = APIRouter(
    prefix="/drive",
    tags=["Google Drive Security"]
)

# --- SCHEMA MODEL ---
class TaskAssignmentRequest(BaseModel):
    project_id: str             
    task_type: str 
    template_file_ids: List[str] 

# --- HELPER FUNCTION ---
def _get_folder_tag(folder_name: str) -> Optional[str]:
    """
    Hàm xác định Tag dựa trên tên.
    """
    name_lower = folder_name.lower()
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
    all_items = drive_service.list_files_in_folder(None) # None = Root
    visible_items = []
    for item in all_items:
        if 'application/vnd.google-apps.folder' in item.get('mimeType', ''):
            visible_items.append({
                "id": item['id'], "name": item['name'], "type": "FOLDER",
                "link": item['webViewLink'], "access": "GRANTED"
            })
    return {"current_context": "ROOT_PROJECTS", "total": len(visible_items), "data": visible_items}

# =================================================================
# 2. API LẤY FILE TRONG 1 FOLDER CỤ THỂ (LOGIC INHERITANCE)
# =================================================================
@router.get("/folder/{folder_id}/me")
def get_folder_by_user(
    folder_id: str, 
    project_id: int, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lấy danh sách file/folder con và CHECK QUYỀN TAG + Trả về Tên Project"""
    
    # 1. Lấy thông tin từ Drive
    all_items = drive_service.list_files_in_folder(folder_id)
    
    # 2. Lấy danh sách quyền (Dạng Dict: {'TAG': 'Tên Project'})
    # VD: allowed_tags = {'FINANCE': 'Dự án Cầu Đường', 'HR': 'Dự án Cầu Đường'}
    allowed_tags_map = get_user_allowed_tags_with_name(db, current_user, project_id)
    
    user_clearance = current_user.security_clearance.value 
    visible_items = []
    
    for item in all_items:
        # A. Xử lý FOLDER
        if 'application/vnd.google-apps.folder' in item.get('mimeType', ''):
            folder_tag = _get_folder_tag(item['name']) 

            # Biến lưu tên project cấp quyền (mặc định là None)
            granted_by_project_name = None

            # --- LOGIC CHECK QUYỀN ---
            if folder_tag:
                # Lấy tên project từ dictionary quyền
                granted_by_project_name = allowed_tags_map.get(folder_tag)
                
                # Nếu folder có Tag mà user không có quyền (không tìm thấy trong map) -> Ẩn
                if not granted_by_project_name:
                    continue 
            # -------------------------

            visible_items.append({
                "id": item['id'], 
                "name": item['name'], 
                "type": "FOLDER",
                "link": item['webViewLink'], 
                "access": "GRANTED",
                "tag": folder_tag,
                
                # <--- BỔ SUNG DÒNG NÀY ĐỂ TRẢ VỀ TÊN PROJECT
                "granted_by_project": granted_by_project_name 
            })
            continue

        # B. Xử lý FILE (Giữ nguyên)
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
                "tag": None,
                "granted_by_project": None # File thì không có project tag context
            })
    
    return {
        "current_folder_id": folder_id, 
        "project_id": project_id,
        "total_items": len(visible_items), 
        "data": visible_items
    }
    
@router.get("/folder/{folder_id}")
def get_folder_content(folder_id: str, current_user: User = Depends(get_current_user)):
    """
    Lấy danh sách file/folder con.
    Logic Tag: Nếu folder CHA đã có Tag (VD: HR) -> Tất cả con đều thừa kế Tag HR.
    """
    
    # 1. Kiểm tra Folder CHA là ai? (Để xem có Tag không)
    parent_meta = drive_service.get_file_metadata(folder_id)
    parent_tag = None
    if parent_meta:
        parent_tag = _get_folder_tag(parent_meta.get('name', ''))

    # 2. Lấy danh sách con
    all_items = drive_service.list_files_in_folder(folder_id)
    user_clearance = current_user.security_clearance.value 
    visible_items = []
    
    for item in all_items:
        # Xử lý Tag cho item này
        # Nếu cha đã có tag -> Con thừa kế luôn (Bất kể tên con là gì)
        item_tag = parent_tag
        
        # Nếu cha chưa có tag (VD: Root Project) -> Con tự check tên nó (Chỉ áp dụng cho Folder)
        if not item_tag and 'application/vnd.google-apps.folder' in item.get('mimeType', ''):
            item_tag = _get_folder_tag(item['name'])

        # A. Folder con -> Luôn hiện
        if 'application/vnd.google-apps.folder' in item.get('mimeType', ''):
            visible_items.append({
                "id": item['id'], 
                "name": item['name'], 
                "type": "FOLDER",
                "link": item['webViewLink'], 
                "access": "GRANTED",
                "tag": item_tag # <--- Tag đã được xử lý thừa kế
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
                "tag": item_tag # <--- File con cũng thừa kế Tag của folder cha
            })
    
    return {"current_folder_id": folder_id, "total_items": len(visible_items), "data": visible_items}

# =================================================================
# 3. CÁC API NGHIỆP VỤ KHÁC (GIỮ NGUYÊN)
# =================================================================

@router.post("/init-project")
def create_project_structure(project_name: str = Form(...), current_user: User = Depends(get_current_user)):
    result = drive_service.create_project_tree(project_name)
    if not result: raise HTTPException(500, "Lỗi tạo cấu trúc dự án")
    return {"message": "Tạo dự án thành công", "data": result}

@router.post("/assign-task-files")
def provision_files_for_task(payload: TaskAssignmentRequest, current_user: User = Depends(get_current_user)):
    result = drive_service.clone_files_for_task(payload.project_id, payload.task_type, payload.template_file_ids)
    if not result: raise HTTPException(500, "Lỗi khi cấp phát tài liệu")
    return {"message": "Đã copy tài liệu mẫu thành công", "data": result}

@router.post("/upload-secure")
async def upload_secure_file(
    file: UploadFile = File(...), folder_id: str = Form(None), 
    security_level: SecurityLevel = Form(SecurityLevel.PUBLIC),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    result = await drive_service.upload_file_with_security(file, folder_id, security_level.value)
    if not result: raise HTTPException(500, "Lỗi upload")
    return {"message": "Upload thành công", "file_info": result}

@router.put("/update/{file_id}")
async def update_drive_file(
    file_id: str, new_name: Optional[str] = Form(None), security_level: Optional[int] = Form(None),
    file: Optional[UploadFile] = File(None), current_user: User = Depends(get_current_user)
):
    success = await drive_service.update_file(file_id, new_name, file, security_level)
    if not success: raise HTTPException(500, "Lỗi cập nhật file")
    return {"message": "Cập nhật thành công", "updated_fields": {"name": new_name, "level": security_level}}

@router.get("/search-repo")
def search_repository(query: str, current_user: User = Depends(get_current_user)):
    flat_results = drive_service.search_files(query)
    item_map = {}
    for item in flat_results:
        is_folder = 'application/vnd.google-apps.folder' in item.get('mimeType', '')
        clean_item = {
            "id": item['id'], "name": item['name'], "type": "FOLDER" if is_folder else "FILE",
            "mime_type": item.get('mimeType'), "link": item['webViewLink'],
            "created_at": item.get('createdTime'), "parents": item.get('parents', []), "children": []
        }
        item_map[item['id']] = clean_item

    tree_roots = []
    for item_id, item in item_map.items():
        parent_id = item['parents'][0] if item['parents'] else None
        if parent_id and parent_id in item_map: item_map[parent_id]['children'].append(item)
        else: tree_roots.append(item)

    return {"query": query, "total_matches": len(flat_results), "tree_roots_count": len(tree_roots), "data": tree_roots}

@router.post("/clone-file")
def clone_file_to_project(source_file_id: str = Form(...), target_folder_id: str = Form(...), new_name: Optional[str] = Form(None), current_user: User = Depends(get_current_user)):
    result = drive_service.copy_file(source_file_id, target_folder_id, new_name)
    if not result: raise HTTPException(500, "Lỗi copy")
    return {"message": "Clone thành công", "file": result}

@router.get("/package-zip/{folder_id}")
def download_folder_as_zip(folder_id: str, current_user: User = Depends(get_current_user)):
    zip_stream = drive_service.zip_folder(folder_id)
    if not zip_stream: raise HTTPException(404, "Không tìm thấy file")
    return StreamingResponse(zip_stream, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename=Project_{folder_id}.zip"})

@router.delete("/delete/{file_id}")
def delete_drive_file(file_id: str, current_user: User = Depends(get_current_user)):
    if drive_service.delete_file(file_id): return {"message": "Đã chuyển vào thùng rác", "file_id": file_id}
    raise HTTPException(404, "Lỗi xóa file")

@router.get("/project/{project_folder_id}/category-folder")
def get_project_category_folder(project_folder_id: str, category: str, current_user: User = Depends(get_current_user)):
    FOLDER_MAPPING = {
        "HR": "nhân sự", "LEGAL": "Pháp lý", "TECH": "Biện pháp Thi công",
        "FINANCE": "tài chính", "DEVICE": "máy móc", "CONTRACT": "hợp đông", "OTHER": "khác"
    }
    keyword = FOLDER_MAPPING.get(category.upper())
    if not keyword: raise HTTPException(400, f"Không hỗ trợ danh mục: {category}")
    target_folder_id = drive_service.get_subfolder_id_by_name(project_folder_id, keyword)
    if not target_folder_id: raise HTTPException(404, f"Không tìm thấy folder {category}")
    return {"category": category, "folder_id": target_folder_id, "folder_keyword": keyword}