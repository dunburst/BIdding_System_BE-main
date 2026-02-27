from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form, Path, Body, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse
from typing import List, Optional
from sqlalchemy.orm import Session
from pydantic import BaseModel
import os
import re

from app.infrastructure.database.database import get_db
from app.modules.users.model import User
from app.modules.bidding.project.model import BiddingProject
from app.core.utils.enum import SecurityLevel
from app.core.security import get_current_user
from .service import drive_service
from app.core.permission.permission_service import get_user_allowed_tags_with_name

router = APIRouter(
    prefix="/drive",
    tags=["Google Drive Security"]
)

# --- SCHEMA MODEL ---
class TaskAssignmentRequest(BaseModel):
    project_id: str             
    task_type: str 
    template_file_ids: List[str] 
    
class FolderStat(BaseModel):
    id: str
    name: str
    count: int

class StatsResponse(BaseModel):
    total_repo_files: int          # Tổng số file trong folder đang xem (bao gồm cả con cháu)
    current_folder_files: int      # Số file (cấp 1) nằm ngay ngoài cùng
    folder_id: Optional[str] = None
    breakdown: List[FolderStat] = [] # <--- [MỚI] Danh sách chi tiết từng folder con
    
class CreateFolderRequest(BaseModel):
    parent_id: str
    folder_name: str

# [MỚI] Schema hứng JSON cho API Init Project
class InitProjectRequest(BaseModel):
    project_id: int  # Frontend gửi key là projectId (camelCase)

# [MỚI] Schema hứng JSON cho API Clone File
class CloneFileRequest(BaseModel):
    source_file_id: str
    target_folder_id: str
    newName: Optional[str] = None

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
        "khác": "OTHER",
        # --- [BỔ SUNG TỪ KHÓA MỚI] ---
        "bldt": "DBTC",
        "cktd": "DBTC",
        "bảo lãnh": "DBTC",
        "tín dụng": "DBTC",
        
        "vt": "VT",
        "vật tư": "VT",
        
        "giá": "GIA",
        "gia": "GIA"
    }
    for key, tag in keywords.items():
        if key in name_lower:
            return tag
    return None

# Bảng map chung để tránh viết lại nhiều lần
GLOBAL_FOLDER_MAPPING = {
    "HR": "nhân sự", 
    "LEGAL": "Pháp lý", 
    "TECH": "Biện pháp Thi công",
    "FINANCE": "tài chính", 
    "DEVICE": "máy móc", 
    "CONTRACT": "hợp đồng", # Sửa lại chính tả hợp đồng
    "OTHER": "khác",
    "DBTC": "BLDT",     # Folder cha hoặc con chứa BLDT
    "VT": "Hồ sơ VT",
    "GIA": "Giá"
}
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
                "link": item['webViewLink'], "access": "GRANTED", "updated_at": item.get('modifiedTime')
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
        
        # [MỚI] Lấy thời gian sửa đổi
        updated_at = item.get('modifiedTime')

        # A. Folder con -> Luôn hiện
        if 'application/vnd.google-apps.folder' in item.get('mimeType', ''):
            visible_items.append({
                "id": item['id'], 
                "name": item['name'], 
                "type": "FOLDER",
                "link": web_link, 
                "access": "GRANTED",
                "tag": item_tag # <--- Tag đã được xử lý thừa kế
                ,"updated_at": updated_at
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
                ,"updated_at": updated_at
            })
    
    return {"current_folder_id": folder_id, "total_items": len(visible_items), "data": visible_items}

# =================================================================
# 3. CÁC API NGHIỆP VỤ KHÁC
# =================================================================

# [UPDATED] Nhận JSON Body thay vì Form
@router.post("/init-project")
def create_project_structure(
    payload: InitProjectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project_id = payload.project_id
    
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
    
    # 4. Cập nhật lại Drive ID vào Database
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
def search_repository(
    query: str, 
    folder_id: Optional[str] = None, 
    current_user: User = Depends(get_current_user)
):
    clean_results = drive_service.search_files(query, folder_id=folder_id)
    
    parent_names_cache = {} 
    if folder_id:
        root_name_meta = drive_service.get_file_metadata(folder_id)
        if root_name_meta:
             parent_names_cache[folder_id] = root_name_meta.get('name')

    item_map = {}

    for item in clean_results:
        parents_list = item.get('parents', [])
        direct_parent_id = parents_list[0] if parents_list else None
        
        parent_name = "Unknown"
        if direct_parent_id:
            if direct_parent_id in parent_names_cache:
                parent_name = parent_names_cache[direct_parent_id]
            else:
                meta = drive_service.get_file_metadata(direct_parent_id)
                if meta:
                    fetched_name = meta.get('name')
                    parent_names_cache[direct_parent_id] = fetched_name
                    parent_name = fetched_name
        
        is_folder = 'application/vnd.google-apps.folder' in item.get('mimeType', '')
        
        clean_item = {
            "id": item['id'], 
            "name": item['name'], 
            "type": "FOLDER" if is_folder else "FILE",
            "mime_type": item.get('mimeType'), 
            "link": item['webViewLink'],
            "created_at": item.get('createdTime'), 
            "parents": parents_list,
            "parent_id": direct_parent_id,
            "parent_name": parent_name, 
            "children": []
        }
        item_map[item['id']] = clean_item

    return {
        "query": query, 
        "scope": folder_id if folder_id else "Global",
        "total_matches": len(clean_results), 
        "data": list(item_map.values()) 
    }

# [UPDATED] Nhận JSON Body thay vì Form
@router.post("/clone-file")
def clone_file_to_project(
    payload: CloneFileRequest,
    current_user: User = Depends(get_current_user)
):
    result = drive_service.copy_file(payload.source_file_id, payload.target_folder_id, payload.newName)
    if not result: raise HTTPException(500, "Lỗi copy file trên Google Drive")
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
def get_project_category_folder(
    project_folder_id: str, 
    category: str, 
    current_user: User = Depends(get_current_user)
):
    tag = category.upper()
    keyword = GLOBAL_FOLDER_MAPPING.get(tag)
    
    if not keyword: 
        raise HTTPException(400, f"Không hỗ trợ danh mục: {category}")
    
    # SỬ DỤNG HÀM TÌM KIẾM MỚI (DEEP SEARCH)
    target_folder_id = drive_service.find_deep_folder(project_folder_id, tag, keyword)
    
    if not target_folder_id: 
        # Thử tìm lỏng lẻo hơn chỉ bằng keyword nếu tìm deep thất bại
        target_folder_id = drive_service.get_subfolder_id_by_name(project_folder_id, keyword)

    if not target_folder_id:
        raise HTTPException(404, f"Không tìm thấy folder cho danh mục '{category}' (Tag: {tag}, Keyword: {keyword}) trong dự án.")
    
    # 2. [MỚI] Lấy thông tin chi tiết để có ngày sửa đổi
    meta = drive_service.get_file_metadata(target_folder_id)
    updated_at = meta.get('modifiedTime') if meta else None
    link = meta.get('webViewLink') if meta else None
        
    return {
        "category": tag, 
        "folder_id": target_folder_id, 
        "folder_keyword": keyword,
        "link": link,
        "updated_at": updated_at
    }

@router.get("/project/{project_folder_id}/me/target-folder")
def get_current_user_target_folder(
    project_folder_id: str,
    project_id: int, 
    category: Optional[str] = None, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Lấy target_folder_id cho User. Hỗ trợ tìm kiếm folder nằm sâu trong cấu trúc.
    """
    
    # 1. Lấy quyền của User
    allowed_tags_map = get_user_allowed_tags_with_name(db, current_user, project_id)
    
    if not allowed_tags_map:
        raise HTTPException(status_code=403, detail="Bạn không được phân công nhiệm vụ nào trong dự án này.")

    # 2. Xác định Tag cần lấy
    selected_tag = None
    available_tags = list(allowed_tags_map.keys())

    if category:
        if category.upper() in available_tags:
            selected_tag = category.upper()
        else:
            raise HTTPException(status_code=403, detail=f"Bạn không có quyền truy cập vào folder '{category}'.")
    else:
        if len(available_tags) == 1:
            selected_tag = available_tags[0]
        else:
            return {
                "success": False,
                "message": "Vui lòng chọn folder đích cụ thể.",
                "available_categories": available_tags,
                "folder_id": None
            }

    # 3. Lấy keyword từ Mapping
    folder_keyword = GLOBAL_FOLDER_MAPPING.get(selected_tag)
    if not folder_keyword:
        # Fallback nếu tag không có trong map (tránh crash)
        folder_keyword = selected_tag 

    # 4. TÌM KIẾM FOLDER (DEEP SEARCH)
    # Hàm này sẽ quét toàn bộ cây thư mục con của project_folder_id để tìm folder có khớp Tag hoặc Tên
    target_folder_id = drive_service.find_deep_folder(project_folder_id, selected_tag, folder_keyword)
    
    if not target_folder_id:
        raise HTTPException(
            status_code=404, 
            detail=f"Không tìm thấy thư mục trên Drive khớp với '{selected_tag}' hoặc tên chứa '{folder_keyword}'."
        )
        
    # 5. [MỚI] Lấy Metadata để có updated_at
    meta = drive_service.get_file_metadata(target_folder_id)
    updated_at = meta.get('modifiedTime') if meta else None
    link = meta.get('webViewLink') if meta else None

    return {
        "success": True,
        "project_id": project_id,
        "category": selected_tag,
        "folder_name_keyword": folder_keyword,
        "target_folder_id": target_folder_id
        ,"link": link
        ,"updated_at": updated_at
    }
    
# 2. CẬP NHẬT ENDPOINT
@router.get("/stats/count", response_model=StatsResponse)
def get_file_statistics(
    folder_id: Optional[str] = None, 
    current_user: User = Depends(get_current_user)
):
    """
    Trả về thống kê số lượng file:
    1. Tổng số file trong cây thư mục này.
    2. Số file lẻ ở ngoài.
    3. Chi tiết số lượng file trong từng folder con (VD: Hồ sơ nhân sự: 10, Pháp lý: 5...)
    """
    # Gọi hàm mới trong service (đã được tối ưu)
    stats = drive_service.get_detailed_statistics(folder_id)
    
    return {
        "total_repo_files": stats["total_files"],
        "current_folder_files": stats["root_files_count"],
        "folder_id": folder_id,
        "breakdown": stats["breakdown"]
    }

@router.post("/create-subfolder")
def create_custom_subfolder(
    payload: CreateFolderRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Tạo một folder con bên trong một folder cha bất kỳ.
    - parent_id: ID của folder cha (trên Google Drive)
    - folder_name: Tên folder muốn tạo
    """
    if not payload.parent_id or not payload.folder_name:
        raise HTTPException(status_code=400, detail="Thiếu parent_id hoặc folder_name")

    # Gọi hàm create_folder có sẵn trong service (hàm này đã support parent_id)
    new_folder_id = drive_service.create_folder(payload.folder_name, payload.parent_id)

    if not new_folder_id:
        raise HTTPException(status_code=500, detail="Không thể tạo folder trên Google Drive. Vui lòng kiểm tra log.")

    return {
        "message": "Tạo folder thành công",
        "data": {
            "id": new_folder_id,
            "name": payload.folder_name,
            "parent_id": payload.parent_id
        }
    }
    
# --- HÀM HỖ TRỢ: LÀM SẠCH TÊN FILE ---
def sanitize_filename(name: str) -> str:
    """
    Chuyển tên dự án tiếng Việt có dấu thành tên file an toàn.
    VD: "Dự án Xây lắp 01/2025" -> "Du_an_Xay_lap_01_2025"
    """
    # Bạn có thể dùng thư viện unidecode nếu muốn bỏ dấu tiếng Việt
    # Ở đây dùng regex đơn giản để giữ an toàn
    safe_name = re.sub(r'[\\/*?:"<>|]', "", name) # Bỏ ký tự cấm của Windows/Linux
    safe_name = safe_name.replace(" ", "_")
    return safe_name

# --- API MỚI: DOWNLOAD ZIP THEO PROJECT ID ---
@router.get("/download-project-zip/{project_id}")
def download_project_by_id(
    project_id: int, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    1. Tìm Project trong DB theo ID.
    2. Lấy drive_folder_id.
    3. Zip toàn bộ và trả về.
    """
    # 1. Truy vấn Database để lấy thông tin Dự án
    project = db.query(BiddingProject).filter(BiddingProject.id == project_id).first()
    
    if not project:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dự án ID: {project_id}")
    
    # 2. Kiểm tra xem dự án đã có Folder Drive chưa
    folder_id = project.drive_folder_id
    if not folder_id:
        raise HTTPException(status_code=400, detail="Dự án này chưa được khởi tạo thư mục trên Google Drive.")

    # 3. Gọi Service để nén file (Hàm zip_folder_recursive đã viết ở bước trước)
    # Lưu ý: Hàm này tốn thời gian, với folder lớn client sẽ phải chờ server xử lý
    print(f"⏳ Đang nén folder ID: {folder_id} cho dự án: {project.name}")
    zip_path = drive_service.zip_folder_recursive(folder_id)
    
    if not zip_path or not os.path.exists(zip_path):
        raise HTTPException(status_code=500, detail="Lỗi trong quá trình nén file từ Google Drive.")

    # 4. Định nghĩa tên file tải về (Lấy theo tên dự án cho đẹp)
    safe_name = sanitize_filename(project.name)
    zip_filename = f"{safe_name}.zip"

    # 5. Dọn dẹp file tạm sau khi gửi xong
    def cleanup_temp_file(path: str):
        try:
            if os.path.exists(path):
                os.remove(path)
                print(f"🧹 Đã xóa file tạm: {path}")
        except Exception as e:
            print(f"⚠️ Lỗi xóa file tạm: {e}")

    background_tasks.add_task(cleanup_temp_file, zip_path)

    # 6. Trả về file
    return FileResponse(
        path=zip_path, 
        filename=zip_filename, 
        media_type='application/zip'
    )