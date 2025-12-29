from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form, Path
from fastapi.responses import StreamingResponse
from typing import List, Optional
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models import User, SecurityLevel, BiddingProject
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
            
        web_link = item.get('webViewLink', '#')

        # A. Folder con -> Luôn hiện
        if 'application/vnd.google-apps.folder' in item.get('mimeType', ''):
            visible_items.append({
                "id": item['id'], 
                "name": item['name'], 
                "type": "FOLDER",
                "link": web_link, 
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
                "link": web_link, 
                "level": file_level, 
                "access": "GRANTED",
                "tag": item_tag # <--- File con cũng thừa kế Tag của folder cha
            })
    
    return {"current_folder_id": folder_id, "total_items": len(visible_items), "data": visible_items}

# =================================================================
# 3. CÁC API NGHIỆP VỤ KHÁC (GIỮ NGUYÊN)
# =================================================================

@router.post("/init-project")
def create_project_structure(
    project_id: int = Form(...),  # <--- Thay đổi: Nhận ID thay vì Name
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. Tìm dự án trong Database dựa vào ID
    project = db.query(BiddingProject).filter(BiddingProject.id == project_id).first()
    
    if not project:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dự án với ID: {project_id}")

    # 2. Lấy tên dự án từ DB để tạo folder
    project_name = project.name
    
    # 3. Gọi service tạo cấu trúc trên Google Drive
    drive_result = drive_service.create_project_tree(project_name)
    
    if not drive_result: 
        raise HTTPException(500, "Lỗi tạo cấu trúc dự án trên Google Drive")
    
    # 4. (Tùy chọn) Cập nhật lại Drive ID vào Database nếu Model có cột này
    # Lưu ý: Trong model bạn gửi chưa có cột drive_folder_id, bạn nên thêm vào.
    project.drive_folder_id = drive_result["project_id"] 
    db.commit() 

    # 5. Trả về kết quả
    return {
        "message": "Đã khởi tạo folder dự án trên Drive thành công",
        "project_id": project.id,              # ID trong Database
        "project_name": project.name,          # Tên lấy từ DB
        "drive_folder_id": drive_result["project_id"], # ID trên Google Drive
        "drive_data": drive_result
    }

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


# [Thêm vào New folder/mcp_drive/router.py]

@router.get("/project/{project_folder_id}/me/target-folder")
def get_current_user_target_folder(
    project_folder_id: str,
    project_id: int, # ID trong Database để check quyền
    category: Optional[str] = None, # Tùy chọn: Nếu user có nhiều quyền (VD: vừa HR vừa Legal) thì cần truyền vào
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Lấy target_folder_id của đúng thư mục mà User hiện tại có quyền thao tác.
    Dùng để làm đích đến cho hành động Clone File.
    """
    
    # 1. Lấy danh sách quyền (Tag) của User trong dự án này
    # Kết quả trả về dạng: {'HR': 'Tên Dự Án', 'TECH': 'Tên Dự Án'}
    allowed_tags_map = get_user_allowed_tags_with_name(db, current_user, project_id)
    
    if not allowed_tags_map:
        raise HTTPException(status_code=403, detail="Bạn không được phân công nhiệm vụ nào trong dự án này.")

    # 2. Xác định Tag (Danh mục) cụ thể
    selected_tag = None
    available_tags = list(allowed_tags_map.keys())

    if category:
        # Nếu Client truyền category lên, check xem User có quyền đó không
        if category.upper() in available_tags:
            selected_tag = category.upper()
        else:
            raise HTTPException(status_code=403, detail=f"Bạn không có quyền truy cập vào thư mục '{category}' trong dự án này.")
    else:
        # Nếu Client KHÔNG truyền category
        if len(available_tags) == 1:
            # Nếu User chỉ có đúng 1 quyền -> Tự động chọn
            selected_tag = available_tags[0]
        else:
            # Nếu User có nhiều quyền (VD: Manager có cả HR, TECH, FINANCE) -> Bắt buộc chọn
            return {
                "success": False,
                "message": "Bạn có quyền ở nhiều bộ phận, vui lòng chỉ định rõ 'category' muốn lưu file.",
                "available_categories": available_tags,
                "folder_id": None
            }

    # 3. Map từ Tag sang Tên thư mục thực tế trên Drive
    # (Mapping này phải đồng bộ với hàm _get_folder_tag hoặc get_project_category_folder)
    FOLDER_MAPPING = {
        "HR": "nhân sự", 
        "LEGAL": "Pháp lý", 
        "TECH": "Biện pháp Thi công",
        "FINANCE": "tài chính", 
        "DEVICE": "máy móc", 
        "CONTRACT": "hợp đông", 
        "OTHER": "khác"
    }
    
    folder_keyword = FOLDER_MAPPING.get(selected_tag)
    if not folder_keyword:
        raise HTTPException(status_code=400, detail=f"Không tìm thấy cấu hình tên thư mục cho tag: {selected_tag}")

    # 4. Tìm ID thư mục con trong Drive
    target_folder_id = drive_service.get_subfolder_id_by_name(project_folder_id, folder_keyword)
    
    if not target_folder_id:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy thư mục '{folder_keyword}' trên Drive của dự án này.")

    return {
        "success": True,
        "project_id": project_id,
        "category": selected_tag,
        "folder_name_keyword": folder_keyword,
        "target_folder_id": target_folder_id # <--- Đây là cái bạn cần cho API clone
    }