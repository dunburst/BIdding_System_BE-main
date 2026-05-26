import os
import io
import zipfile
from typing import List, Optional, Any
import httplib2
import urllib3
import asyncio
import tempfile

# --- CÁC IMPORT CHÍNH ---
from google.oauth2.credentials import Credentials 
from google_auth_httplib2 import AuthorizedHttp
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from fastapi import UploadFile
from dotenv import load_dotenv
import requests
from collections import defaultdict, deque
import json
from googleapiclient.errors import HttpError

# # --- THÊM ĐOẠN NÀY ĐỂ BỎ QUA PROXY CỦA HỆ THỐNG ---
# os.environ.pop("HTTP_PROXY", None)
# os.environ.pop("HTTPS_PROXY", None)
# os.environ.pop("http_proxy", None)
# os.environ.pop("https_proxy", None)

load_dotenv()

# --- TẮT CẢNH BÁO SSL (GIÚP LOG SẠCH VÀ NHANH HƠN) ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
class RequestsShim(object):
    def __init__(self):
        self.session = requests.Session()
        
        # --- CẤU HÌNH "VƯỢT TƯỜNG LỬA" ---
        self.session.verify = False       # TẮT HOÀN TOÀN xác thực SSL (Chấp nhận chứng chỉ lỗi)
        self.session.trust_env = False    # TẮT HOÀN TOÀN việc đọc Proxy từ hệ thống (Bỏ qua setting máy)
        
        # Giả danh trình duyệt Chrome để Firewall không chặn
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

    def request(self, uri, method="GET", body=None, headers=None, redirections=5, connection_type=None):
        # Chuyển đổi gọi hàm từ giao thức cũ (httplib2) sang requests
        try:
            # Thực hiện request bằng thư viện requests mạnh mẽ hơn
            response = self.session.request(
                method, 
                uri, 
                data=body, 
                headers=headers, 
                timeout=120,
                allow_redirects=False  # <--- QUAN TRỌNG: Phải chặn auto redirect
            )
            
            # Cần gói lại kết quả theo đúng format mà Google API mong đợi
            # (Google API mong đợi 1 tuple gồm: (headers_object, content_bytes))
            
            class Httplib2Response(dict):
                def __init__(self, headers, status, reason):
                    super().__init__(headers)
                    self.status = status
                    self.reason = reason
            
            # Gom headers và status code lại giả làm httplib2
            resp_headers = Httplib2Response(dict(response.headers), response.status_code, response.reason)
            
            return (resp_headers, response.content)
            
        except Exception as e:
            print(f"❌ Lỗi mạng tầng RequestsShim: {str(e)}")
            raise e
        
class GoogleDriveService:
    def __init__(self):
        self.service: Any = None
        self.ROOT_FOLDER_ID: Optional[str] = os.getenv("GOOGLE_DRIVE_SHARED_FOLDER_ID")
        self.PROJECT_CONTAINER_ID: Optional[str] = os.getenv("GOOGLE_PROJECT_CONTAINER_ID")
        
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")

        if client_id and client_secret and refresh_token:
            # 1. Tạo đối tượng Credentials
            self.creds = Credentials(
                None, 
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=client_secret
            )
            
            # 2. Refresh token nếu hết hạn
            if self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                except Exception as e:
                    print(f"⚠️ Lỗi refresh token: {e}")

            try:
                # --- THAY ĐỔI QUAN TRỌNG NHẤT Ở ĐÂY ---
                # Dùng RequestsShim thay vì httplib2 mặc định
                http_shim = RequestsShim()
                
                # Bọc nó bằng AuthorizedHttp để tự động gắn Token
                authorized_http = AuthorizedHttp(self.creds, http=http_shim)

                # Truyền vào build
                self.service = build(
                    'drive', 'v3', 
                    http=authorized_http, # Google sẽ dùng requests thông qua lớp vỏ bọc này
                    cache_discovery=False,
                    static_discovery=False 
                )
                print("✅ Kết nối Drive thành công (Mode: Requests Shim - Bypass Proxy 100%)!")
            except Exception as e:
                print(f"❌ Lỗi kết nối Drive: {e}")
        else:
            print("❌ Lỗi: Thiếu cấu hình OAuth")
            
    # --- HÀM HỖ TRỢ CHẠY ASYNC (TRÁNH BLOCK SERVER) ---
    async def _run_in_thread(self, func, *args, **kwargs):
        """Chạy hàm blocking của Google trong thread riêng"""
        return await asyncio.to_thread(func, *args, **kwargs)

    # --- NHÓM 1: QUẢN LÝ FOLDER & FILE CƠ BẢN ---
    
    # [MỚI] Hàm lấy thông tin chi tiết của 1 file/folder (Để check tên folder cha)
    def get_file_metadata(self, file_id: str):
        if not self.service: return None
        try:
            return self.service.files().get(
                fileId=file_id, 
                fields='id, name, mimeType, webViewLink,properties, modifiedTime',
            ).execute()
        except Exception as e:
            print(f"❌ Lỗi get metadata: {e}")
            return None

    # [CẬP NHẬT 1] Sửa hàm create_folder để nhận thêm tham số 'tag'
    def create_folder(self, folder_name: str, parent_id: Optional[str] = None, tag: Optional[str] = None) -> Optional[str]:
        try:
            target_parent = parent_id if parent_id else self.ROOT_FOLDER_ID
            
            # Metadata cơ bản
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [target_parent]
            }

            # [QUAN TRỌNG] Nếu có tag, lưu vào properties để sau này code khác đọc được chính xác
            if tag:
                file_metadata['properties'] = {
                    'project_tag': tag
                }

            folder = self.service.files().create(
                body=file_metadata, fields='id'
            ).execute()
            
            return folder.get('id')
        except Exception as e:
            print(f"❌ Lỗi tạo folder '{folder_name}': {e}")
            return None

    # [CẬP NHẬT 2] Sửa hàm create_project_tree với cấu trúc và tag mới
    def create_project_tree(self, project_name: str):
        # 1. Xác định nơi chứa dự án
        # Nếu có cấu hình Container riêng thì dùng, nếu không thì dùng Root mặc định
        target_parent_id = self.PROJECT_CONTAINER_ID if self.PROJECT_CONTAINER_ID else self.ROOT_FOLDER_ID
        
        # 2. Tạo folder gốc dự án (nằm trong target_parent_id)
        print(f"🔨 Init project '{project_name}' inside folder ID: {target_parent_id}")
        project_id = self.create_folder(project_name, target_parent_id)
        if not project_id: return None

        # 2. Định nghĩa Cấu trúc Folder + Tag
        # Cấu trúc: Mỗi phần tử là một folder cha, chứa danh sách 'children' (folder con)
        structure_config = [
            {
                "name": "1. HSPL, BCTC, HDTT, TTLD",
                "tag": None, # Folder vỏ này không cần tag, hoặc bạn có thể gán nếu muốn
                "children": [
                    {"name": "Hồ sơ pháp lý",   "tag": "LEGAL"},
                    {"name": "Báo cáo tài chính", "tag": "FINANCE"},
                    {"name": "Hợp đồng tương tự", "tag": "CONTRACT"}
                ]
            },
            {
                "name": "2. BLDT, CKTD",
                "tag": "DBTC", # Tag cho cả folder cha này
                "children": [] 
            },
            {
                "name": "3. BPTC",
                "tag": None,
                "children": [
                    {"name": "Nhân sự",          "tag": "HR"},
                    {"name": "Máy móc",          "tag": "DEVICE"},
                    {"name": "Biện pháp thi công", "tag": "TECH"}
                ]
            },
            {
                "name": "4. Hồ sơ VT",
                "tag": "VT",
                "children": []
            },
            {
                "name": "5. Giá",
                "tag": "GIA",
                "children": []
            }
        ]

        created_folders_log = []

        try:
            # 3. Vòng lặp tạo folder
            for parent_config in structure_config:
                p_name = parent_config["name"]
                p_tag = parent_config["tag"]
                
                # A. Tạo Folder Cha
                print(f"📂 Creating Parent: {p_name} (Tag: {p_tag})")
                parent_id = self.create_folder(p_name, project_id, tag=p_tag)
                
                if parent_id:
                    created_folders_log.append({
                        "name": p_name, "id": parent_id, "type": "PARENT", "tag": p_tag
                    })

                    # B. Tạo Folder Con (nếu có)
                    for child in parent_config["children"]:
                        c_name = child["name"]
                        c_tag = child["tag"]
                        
                        print(f"  └── Creating Child: {c_name} (Tag: {c_tag})")
                        child_id = self.create_folder(c_name, parent_id, tag=c_tag)
                        
                        if child_id:
                            created_folders_log.append({
                                "name": c_name, "id": child_id, "type": "CHILD", "parent": p_name, "tag": c_tag
                            })

            return {
                "project_name": project_name,
                "project_id": project_id,
                "structure_log": created_folders_log
            }
        except Exception as e:
            print(f"❌ Lỗi tạo cấu trúc cây thư mục: {e}")
            return None
    async def upload_file_with_security(self, file: UploadFile, folder_id: str, security_level: int):
        try:
            # 1. Đọc nội dung file
            # Lưu ý: file.read() sẽ đưa toàn bộ file vào RAM. 
            # Với file >100MB nên cân nhắc dùng SpooledTemporaryFile nhưng cách này ổn với file nhỏ.
            file_content = await file.read()
            
            # 2. Định nghĩa hàm xử lý upload gói gọn để chạy trong thread khác
            def _blocking_upload():
                file_metadata = {
                    'name': file.filename,
                    'parents': [folder_id] if folder_id else []
                }
                
                media = MediaIoBaseUpload(
                    io.BytesIO(file_content),
                    mimetype=file.content_type,
                    resumable=False # Resumable cần allow_redirects=False ở Shim
                )

                # Gọi lệnh execute()
                return self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id, name, webViewLink, webContentLink'
                ).execute()

            # 3. Chạy hàm blocking trong thread pool để không chặn FastAPI
            # Sử dụng self._run_in_thread bạn đã định nghĩa
            file_drive = await self._run_in_thread(_blocking_upload)

            # 4. Trả kết quả
            return {
                "id": file_drive.get("id"),
                "name": file_drive.get("name"),
                "status": "uploaded_success",
                "link": file_drive.get("webViewLink"),
                "download_link": file_drive.get("webContentLink")
            }

        except HttpError as error:
            # --- LOG CHI TIẾT HƠN ---
            print(f"❌ Google API Error Code: {error.resp.status}") 
            print(f"❌ Error Reason: {error.resp.reason}")
            try:
                # Cố gắng decode nội dung lỗi nếu có
                content = error.content.decode('utf-8')
                print(f"❌ Error Content: {content}")
            except:
                print(f"❌ Error Content: (Empty or Binary data)")
            return None

    async def update_file(self, file_id: str, new_name: Optional[str] = None, new_file: Optional[UploadFile] = None, security_level: Optional[int] = None):
        try:
            body = {}
            if new_name: body['name'] = new_name
            if security_level is not None: body['properties'] = {'security_level': str(security_level)}

            if body:
                self.service.files().update(fileId=file_id, body=body).execute()

            if new_file:
                content = await new_file.read()
                file_stream = io.BytesIO(content)
                media = MediaIoBaseUpload(file_stream, mimetype=new_file.content_type, resumable=True)
                self.service.files().update(fileId=file_id, media_body=media).execute()
            return True
        except Exception as e:
            print(f"❌ Lỗi update file: {e}")
            return False

    def list_files_in_folder(self, folder_id: Optional[str] = None):
        target_folder = folder_id if folder_id else self.ROOT_FOLDER_ID
        if not self.service: return []
        try:
            query = f"'{target_folder}' in parents and trashed=false"
            results = self.service.files().list(
                q=query, pageSize=1000,
                fields="files(id, name, mimeType, webViewLink, properties, modifiedTime)", 
                orderBy="folder, modifiedTime desc"
            ).execute()
            return results.get('files', [])
        except Exception as e:
            print(f"❌ Lỗi list file: {str(e)}")
            return []

    # --- NHÓM 2: NGHIỆP VỤ MỞ RỘNG ---
    # --- HÀM MỚI: KIỂM TRA ĐỆ QUY XEM FILE CÓ THUỘC FOLDER GỐC KHÔNG ---
    def is_file_in_folder_recursive(self, file_id: str, target_folder_id: str, parent_cache: Optional[dict] = None) -> bool:
        """
        Dò ngược từ file lên các đời cha ông để xem nó có nằm trong target_folder_id không.
        Sử dụng parent_cache để tránh gọi API nhiều lần cho cùng một nhánh folder.
        """
        if parent_cache is None: parent_cache = {}
        
        current_id = file_id
        
        # Giới hạn độ sâu để tránh loop vô tận (ví dụ 10 cấp)
        for _ in range(10): 
            # 1. Nếu đã chạm đến folder đích -> Đúng
            if current_id == target_folder_id:
                return True
                
            # 2. Nếu là Root hoặc không có cha -> Sai
            if not current_id or current_id == self.ROOT_FOLDER_ID:
                return False

            # 3. Check Cache xem folder này đã từng được verify chưa
            if current_id in parent_cache:
                # Nếu cache lưu ID cha của nó, ta nhảy cóc lên cha luôn
                current_id = parent_cache[current_id]
                continue

            # 4. Gọi API lấy thông tin cha
            try:
                # Lấy parents của folder/file hiện tại
                meta = self.service.files().get(
                    fileId=current_id, fields='parents', supportsAllDrives=True
                ).execute()
                
                parents = meta.get('parents', [])
                
                if not parents:
                    parent_cache[current_id] = None # Đánh dấu là hết đường
                    return False
                
                # Google Drive file có thể có nhiều cha, nhưng thường chỉ có 1. Lấy cái đầu tiên.
                first_parent_id = parents[0]
                
                # Lưu vào cache: "Cha của current_id là first_parent_id"
                parent_cache[current_id] = first_parent_id
                
                # Leo lên 1 cấp
                current_id = first_parent_id
                
            except Exception as e:
                print(f"⚠️ Lỗi check parent của {current_id}: {e}")
                return False
                
        return False

    # --- SỬA LẠI HÀM SEARCH ---
    # --- SỬA LẠI HÀM SEARCH (STRICT MODE) ---
    def search_files(self, query_name: str, folder_id: Optional[str] = None) -> List[dict]:
        if not self.service: return []
        try:
            # 1. Query Google (Vẫn phải search rộng trước vì API hạn chế)
            safe_query_name = query_name.replace("'", "\\'")
            q_parts = [f"name contains '{safe_query_name}'", "trashed=false"]
            final_query = " and ".join(q_parts)

            filtered_results = [] 
            ancestry_cache = {} 
            page_token = None
            api_call_count = 0 
            MAX_API_CALLS = 10 

            # print(f"🔍 Debug: Tìm '{query_name}' trong folder '{folder_id}'")

            while True:
                api_call_count += 1
                
                # Gọi Google API (Nó sẽ trả về cả những file ở ngoài folder_id)
                results = self.service.files().list(
                    q=final_query, 
                    pageSize=50, 
                    fields="nextPageToken, files(id, name, mimeType, webViewLink, createdTime, parents, properties)", 
                    orderBy="folder, createdTime desc",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                    pageToken=page_token
                ).execute()
                
                candidates = results.get('files', [])
                
                # --- LOGIC LỌC NGHIÊM NGẶT ---
                for item in candidates:
                    is_match = False
                    parents = item.get('parents', [])

                    if not folder_id:
                        # Case 1: Tìm toàn bộ Drive (không truyền folder_id) -> Lấy hết
                        is_match = True
                    else:
                        # Case 2: Tìm trong folder cụ thể
                        
                        if not parents:
                            # [QUAN TRỌNG] Nếu file không có cha (như file "siêu cấp..." của bạn)
                            # -> Nó chắc chắn KHÔNG nằm trong folder con nào cả.
                            # -> LOẠI BỎ NGAY (trừ khi folder_id chính là root ảo, nhưng thường API drive trả về ID cụ thể)
                            is_match = False
                            
                        elif folder_id in parents:
                             # Nếu cha trực tiếp chính là folder đang tìm -> Lấy
                             is_match = True
                        else:
                             # Check đệ quy ngược lên trên
                             if self.is_file_in_folder_recursive(parents[0], folder_id, ancestry_cache):
                                 is_match = True
                    
                    if is_match:
                        filtered_results.append(item)
                
                # Điều kiện dừng
                if len(filtered_results) >= 50 or not results.get('nextPageToken') or api_call_count >= MAX_API_CALLS:
                    break
                
                page_token = results.get('nextPageToken')

            return filtered_results

        except Exception as e:
            print(f"❌ Lỗi search: {e}")
            return []
        
        
    # --- [CẬP NHẬT] HÀM SEARCH FOLDER ĐỆ QUY (DEEP SEARCH) ---
    def search_folders_by_keywords(self, root_folder_id: str, keywords: List[str]):
        """
        Tìm kiếm folder chứa từ khóa NẰM SÂU bất kỳ đâu trong dự án.
        Chiến thuật: Search tên trước -> Check tổ tiên sau.
        """
        if not self.service or not keywords:
            return []

        try:
            # 1. QUERY RỘNG: Chỉ tìm theo TÊN (Bỏ điều kiện parents)
            base_query = "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            
            # Escape dấu nháy đơn trong keyword để tránh lỗi cú pháp query
            safe_keywords = [kw.replace("'", "\\'") for kw in keywords]
            name_conditions = [f"name contains '{kw}'" for kw in safe_keywords]
            name_query = " or ".join(name_conditions)
            
            final_query = f"{base_query} and ({name_query})"
            
            # Lấy nhiều kết quả một chút để lọc (ví dụ 100)
            results = self.service.files().list(
                q=final_query,
                pageSize=100, 
                fields="files(id, name, mimeType, webViewLink, parents, properties)",
                orderBy="folder, createdTime desc",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()
            
            candidates = results.get('files', [])
            
            # 2. FILTER HẸP: Kiểm tra đệ quy xem có thuộc root_folder_id không
            final_results = []
            ancestry_cache = {} # Cache để tối ưu tốc độ check parent

            print(f"🔍 Tìm thấy {len(candidates)} folder tiềm năng, đang check quan hệ cha-con...")

            for folder in candidates:
                # Nếu folder đó chính là root (hiếm khi nhưng có thể trùng tên)
                if folder['id'] == root_folder_id:
                    continue

                # Sử dụng hàm check đệ quy bạn đã viết sẵn
                if self.is_file_in_folder_recursive(folder['id'], root_folder_id, ancestry_cache):
                    final_results.append(folder)
            
            print(f"✅ Kết quả cuối cùng: {len(final_results)} folder thuộc dự án.")
            return final_results

        except Exception as e:
            print(f"❌ Lỗi search folder deep: {str(e)}")
            return []
        
    # --- [THÊM VÀO GoogleDriveService] ---
    def find_deep_folder(self, project_root_id: str, tag: str, keyword_name: str) -> Optional[str]:
        """
        Tìm kiếm folder con nằm sâu bên trong cây thư mục dự án.
        Ưu tiên 1: Tìm theo property 'project_tag'.
        Ưu tiên 2: Tìm theo tên (name contains).
        Sau đó xác thực folder tìm thấy thực sự thuộc về project_root_id.
        """
        if not self.service or not project_root_id: return None

        try:
            # 1. Tạo Query tìm kiếm rộng (Không giới hạn parents ngay lập tức vì API search parents đệ quy rất khó)
            # Tìm Folder có (Tag khớp) HOẶC (Tên chứa từ khóa)
            # Lưu ý: properties has ... là cú pháp tìm theo metadata
            
            # Escape dấu nháy đơn trong keyword nếu có
            safe_keyword = keyword_name.replace("'", "\\'")
            
            query = (
                "mimeType = 'application/vnd.google-apps.folder' "
                "and trashed = false "
                f"and (properties has {{ key='project_tag' and value='{tag}' }} "
                f"or name contains '{safe_keyword}')"
            )

            # 2. Thực hiện search
            results = self.service.files().list(
                q=query,
                pageSize=50, # Lấy 50 kết quả tiềm năng nhất
                fields="files(id, name, parents, properties)",
                orderBy="createdTime desc", # Ưu tiên folder mới tạo
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()

            candidates = results.get('files', [])
            
            # 3. Lọc kết quả: Chỉ lấy folder nào thực sự là con cháu của project_root_id
            ancestry_cache = {} 
            
            for folder in candidates:
                # Kiểm tra Tag trước (Nếu khớp Tag thì lấy luôn, rất chính xác)
                props = folder.get('properties', {})
                if props.get('project_tag') == tag:
                    # Check xem có thuộc dự án không
                    if self.is_file_in_folder_recursive(folder['id'], project_root_id, ancestry_cache):
                        return folder['id']
            
            # Nếu không tìm thấy bằng Tag, tìm bằng Tên (Fallback)
            for folder in candidates:
                if keyword_name.lower() in folder['name'].lower():
                    if self.is_file_in_folder_recursive(folder['id'], project_root_id, ancestry_cache):
                        return folder['id']

            return None

        except Exception as e:
            print(f"❌ Lỗi tìm deep folder: {e}")
            return None
        
    # [MỚI] Hàm lấy tên folder (dùng cache đơn giản để tránh gọi nhiều nếu cần)
    def get_folder_name(self, folder_id: str) -> str:
        if not self.service or not folder_id: return "Unknown"
        try:
            # Gọi nhẹ API để lấy đúng field name
            res = self.service.files().get(
                fileId=folder_id, 
                fields='name'
            ).execute()
            return res.get('name', 'Unknown')
        except Exception:
            return "Unknown (Restricted)"

    def copy_file(self, file_id: str, target_folder_id: str, new_name: Optional[str] = None):
        try:
            source = self.service.files().get(fileId=file_id, fields='name, properties').execute()
            file_metadata = {
                'parents': [target_folder_id],
                'name': new_name if new_name else source.get('name'),
                'properties': source.get('properties', {})
            }
            new_file = self.service.files().copy(
                fileId=file_id, body=file_metadata, fields='id, name, webViewLink, properties'
            ).execute()
            return new_file
        except Exception as e:
            print(f"❌ Lỗi copy file: {e}")
            return None
        
    def delete_file(self, file_id: str):
        try:
            self.service.files().update(fileId=file_id, body={'trashed': True}).execute()
            return True
        except Exception as e:
            print(f"❌ Lỗi xóa file: {e}")
            return False
        
    def zip_folder(self, folder_id: str):
        try:
            files = self.list_files_in_folder(folder_id)
            if not files: return None

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                for file in files:
                    if 'application/vnd.google-apps.folder' in file['mimeType']: continue
                    print(f"⬇️ Zipping: {file['name']}")
                    request = self.service.files().get_media(fileId=file['id'])
                    file_io = io.BytesIO()
                    downloader = MediaIoBaseDownload(file_io, request)
                    done = False
                    while not done: _, done = downloader.next_chunk()
                    file_io.seek(0)
                    zip_file.writestr(file['name'], file_io.read())
            zip_buffer.seek(0)
            return zip_buffer
        except Exception as e:
            print(f"❌ Lỗi zip folder: {e}")
            return None
        
    # --- [HÀM MỚI] Tải và nén toàn bộ Folder (Đệ quy + Temp File) ---
    def zip_folder_recursive(self, root_folder_id: str):
        """
        Nén toàn bộ folder và sub-folder thành file zip lưu tạm trên ổ cứng.
        Trả về đường dẫn file tạm.
        """
        if not self.service:
            return None

        # 1. Tạo file tạm trên ổ cứng để tránh tràn RAM
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        temp_zip_path = temp_zip.name
        temp_zip.close() # Đóng lại để zipfile mở ra ghi

        try:
            with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
                
                # 2. Sử dụng hàng đợi để duyệt cây thư mục (BFS)
                # Cấu trúc item trong queue: (folder_id, đường_dẫn_tương_đối_trong_zip)
                queue = deque([(root_folder_id, "")])
                
                # Cache tên file để xử lý trùng lặp
                # Key: "path/to/folder/", Value: {filename1, filename2...}
                path_cache = {} 

                while queue:
                    current_folder_id, current_path = queue.popleft()
                    
                    # Lấy danh sách file trong folder hiện tại
                    # Lưu ý: pageSize=1000 để lấy tối đa, cần loop nếu folder >1000 file (đã tối giản cho demo)
                    query = f"'{current_folder_id}' in parents and trashed=false"
                    results = self.service.files().list(
                        q=query, 
                        fields="files(id, name, mimeType)", 
                        pageSize=1000
                    ).execute()
                    
                    items = results.get('files', [])

                    for item in items:
                        item_id = item['id']
                        original_name = item['name']
                        item_type = item['mimeType']
                        
                        # Xử lý trùng tên file trong cùng 1 folder (Google cho phép, Zip thì không)
                        safe_name = original_name
                        if current_path not in path_cache:
                            path_cache[current_path] = set()
                        
                        counter = 1
                        while safe_name in path_cache[current_path]:
                            name_parts = os.path.splitext(original_name)
                            safe_name = f"{name_parts[0]}_{counter}{name_parts[1]}"
                            counter += 1
                        path_cache[current_path].add(safe_name)

                        # Tạo đường dẫn đầy đủ trong file zip
                        zip_entry_path = os.path.join(current_path, safe_name)

                        # TRƯỜNG HỢP 1: LÀ FOLDER
                        if item_type == 'application/vnd.google-apps.folder':
                            # Thêm vào hàng đợi để duyệt tiếp
                            queue.append((item_id, zip_entry_path))
                            # Tạo folder rỗng trong zip (để folder trống vẫn hiện diện)
                            zip_info = zipfile.ZipInfo(zip_entry_path + "/")
                            zip_file.writestr(zip_info, "")
                            print(f"📂 Added folder: {zip_entry_path}")

                        # TRƯỜNG HỢP 2: LÀ FILE
                        else:
                            print(f"⬇️ Downloading: {zip_entry_path}")
                            try:
                                request = self.service.files().get_media(fileId=item_id)
                                file_io = io.BytesIO()
                                downloader = MediaIoBaseDownload(file_io, request)
                                
                                done = False
                                while not done:
                                    _, done = downloader.next_chunk()
                                
                                file_io.seek(0)
                                # Ghi nội dung vào zip
                                zip_file.writestr(zip_entry_path, file_io.read())
                                file_io.close()
                            except Exception as e:
                                print(f"❌ Lỗi tải file {original_name}: {e}")
                                # Có thể ghi 1 file text báo lỗi vào zip thay thế
                                zip_file.writestr(zip_entry_path + ".ERROR.txt", f"Failed to download: {str(e)}")

            return temp_zip_path

        except Exception as e:
            print(f"❌ Critical Error Zipping: {e}")
            if os.path.exists(temp_zip_path):
                os.remove(temp_zip_path) # Xóa file tạm nếu lỗi
            return None

    def get_subfolder_id_by_name(self, project_id: str, folder_keyword: str):
        if not self.service: return None
        try:
            query = f"'{project_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed=false"
            results = self.service.files().list(q=query, fields="files(id, name)").execute()
            for f in results.get('files', []):
                if folder_keyword.lower() in f['name'].lower():
                    return f['id']
            return None
        except Exception as e:
            print(f"❌ Lỗi tìm folder con: {e}")
            return None

    def clone_files_for_task(self, project_id: str, category: str, source_file_ids: list):
        FOLDER_MAPPING = {
            "HR": "nhân sự", "LEGAL": "Pháp lý", "TECH": "Biện pháp Thi công",
            "FINANCE": "tài chính", "DEVICE": "máy móc", "CONTRACT": "hợp đông", "OTHER": "khác"
        }
        target_keyword = FOLDER_MAPPING.get(category)
        if not target_keyword: return None
        target_folder_id = self.get_subfolder_id_by_name(project_id, target_keyword)
        if not target_folder_id: return None
        cloned_files = []
        for file_id in source_file_ids:
            new_file = self.copy_file(file_id, target_folder_id)
            if new_file: cloned_files.append(new_file)
        return {"category": category, "target_folder_id": target_folder_id, "files": cloned_files}
    # --- NHÓM 3: THỐNG KÊ (STATISTICS) ---
    def _count_files_recursive(self, query: str) -> int:
        """
        Hàm nội bộ để đếm file dựa trên query.
        Sử dụng pageSize=1000 và chỉ lấy field 'id' để tối ưu tốc độ.
        """
        if not self.service: return 0
        
        count = 0
        page_token = None
        
        try:
            while True:
                # Chỉ lấy files(id) để giảm dung lượng response
                response = self.service.files().list(
                    q=query,
                    spaces='drive',
                    fields='nextPageToken, files(id)',
                    pageSize=1000, 
                    pageToken=page_token
                ).execute()
                
                files = response.get('files', [])
                count += len(files)
                
                page_token = response.get('nextPageToken', None)
                if page_token is None:
                    break
                    
            return count
        except Exception as e:
            print(f"❌ Lỗi đếm file: {e}")
            return 0
    def count_files_recursive_under_folder(self, root_folder_id: Optional[str]) -> int:
        """
        Đếm tổng số file (không tính folder) nằm bên trong root_folder_id 
        và TẤT CẢ các folder con cháu của nó.
        """
        # [SỬA ĐỔI 2]: Kiểm tra None ngay đầu hàm
        if not self.service or not root_folder_id: 
            return 0

        try:
            # BƯỚC 1: Lấy toàn bộ items
            query = "trashed = false"
            
            all_items = []
            page_token = None
            
            while True:
                response = self.service.files().list(
                    q=query,
                    fields='nextPageToken, files(id, parents, mimeType)',
                    pageSize=1000,
                    pageToken=page_token
                ).execute()
                
                all_items.extend(response.get('files', []))
                page_token = response.get('nextPageToken')
                if not page_token:
                    break
            
            # BƯỚC 2: Xây dựng bản đồ cha-con
            parents_map = defaultdict(list)
            for item in all_items:
                parents = item.get('parents', [])
                if parents:
                    parent_id = parents[0]
                    parents_map[parent_id].append(item)

            # BƯỚC 3: Duyệt cây (BFS)
            count = 0
            queue = deque([root_folder_id])
            
            while queue:
                current_folder_id = queue.popleft()
                children = parents_map.get(current_folder_id, [])
                
                for child in children:
                    if child['mimeType'] == 'application/vnd.google-apps.folder':
                        queue.append(child['id'])
                    else:
                        count += 1
                        
            return count

        except Exception as e:
            print(f"❌ Lỗi đếm đệ quy: {e}")
            return 0

    def get_repository_statistics(self, specific_folder_id: Optional[str] = None):
        """
        Lấy thống kê.
        Logic MỚI:
        - Nếu có specific_folder_id: Đếm đệ quy TẤT CẢ file nằm trong folder đó (Total) 
                                     và đếm file cấp 1 (Current).
        - Nếu không có (None): Mới lấy theo ROOT_FOLDER_ID của hệ thống.
        """
        
        # 1. Xác định "Gốc" để đếm tổng
        # Nếu người dùng đang chọn folder cụ thể -> Gốc là folder đó
        # Nếu không -> Gốc là System Root (trong .env)
        target_root_id = specific_folder_id if specific_folder_id else self.ROOT_FOLDER_ID
        
        # 2. Đếm đệ quy (Recursive) từ Gốc đã xác định
        # Hàm này sẽ trả về tổng số file trong folder mẹ + các sub-folder con cháu
        total_recursive = self.count_files_recursive_under_folder(target_root_id)
        
        # 3. Đếm file cấp 1 (Direct children only) - Để hiển thị số file nhìn thấy ngay
        current_folder_count = 0
        if specific_folder_id:
            q = f"'{specific_folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
            current_folder_count = self._count_files_recursive(q)
            
        return {
            "total_repository_files": total_recursive, # <--- Giờ nó sẽ là tổng file của folder bạn chọn
            "current_folder_files": current_folder_count
        }
        
    # --- [HÀM MỚI] THỐNG KÊ CHI TIẾT ---
    def get_detailed_statistics(self, root_folder_id: Optional[str] = None):
        """
        Tính toán thống kê chi tiết:
        - Tổng file.
        - Số file trong từng folder con cấp 1.
        
        Logic tối ưu: Chỉ gọi API list file 1 lần duy nhất để lấy toàn bộ map, 
        sau đó tính toán trong RAM bằng đệ quy.
        """
        target_root = root_folder_id if root_folder_id else self.ROOT_FOLDER_ID
        
        if not self.service or not target_root: 
            return {"total_files": 0, "root_files_count": 0, "breakdown": []}

        try:
            # BƯỚC 1: LẤY TOÀN BỘ DỮ LIỆU CÂY THƯ MỤC (Chỉ 1 lần quét)
            # Query tìm tất cả file/folder là hậu duệ của target_root thì rất khó với API Drive chuẩn.
            # Cách tốt nhất: Tìm tất cả file không ở thùng rác, sau đó lọc cha-con trong code.
            # (Lưu ý: Nếu kho quá lớn >100k file, cần giải pháp index DB riêng. Với <10k file, cách này vẫn nhanh).
            
            # Để tối ưu, ta chỉ lấy id, name, parents, mimeType
            query = "trashed = false" 
            
            # Hàm list_all_files này bạn có thể tận dụng logic của count_files_recursive_under_folder cũ
            # nhưng sửa lại để return list thay vì count.
            all_items = []
            page_token = None
            
            while True:
                response = self.service.files().list(
                    q=query,
                    fields='nextPageToken, files(id, name, parents, mimeType)',
                    pageSize=1000,
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True
                ).execute()
                all_items.extend(response.get('files', []))
                page_token = response.get('nextPageToken')
                if not page_token: break

            # BƯỚC 2: XÂY DỰNG CÂY (PARENT MAP) TRONG RAM
            # Key: Parent_ID -> Value: List of Children Items
            parents_map = defaultdict(list)
            item_map = {} # Để tra cứu thông tin item theo ID

            for item in all_items:
                item_map[item['id']] = item
                parents = item.get('parents', [])
                if parents:
                    # Một file có thể có nhiều cha, nhưng ta lấy cha đầu tiên làm chính
                    p_id = parents[0]
                    parents_map[p_id].append(item)

            # BƯỚC 3: HÀM ĐỆ QUY ĐẾM FILE (INTERNAL)
            def count_files_in_subtree(current_id):
                count = 0
                # Lấy danh sách con trực tiếp của folder này từ map
                children = parents_map.get(current_id, [])
                
                for child in children:
                    is_folder = 'application/vnd.google-apps.folder' in child['mimeType']
                    if is_folder:
                        # Nếu là folder -> Đệ quy cộng dồn con cháu nó
                        count += count_files_in_subtree(child['id'])
                    else:
                        # Nếu là file -> Cộng 1
                        count += 1
                return count

            # BƯỚC 4: TÍNH TOÁN KẾT QUẢ
            
            # A. Tổng số file toàn bộ cây (Total recursive)
            total_files = count_files_in_subtree(target_root)
            
            # B. Xử lý breakdown cho các con trực tiếp của Root
            breakdown = []
            root_files_count = 0 # Số file lẻ nằm ngay ở root
            
            direct_children = parents_map.get(target_root, [])
            
            for child in direct_children:
                is_folder = 'application/vnd.google-apps.folder' in child['mimeType']
                
                if is_folder:
                    # Nếu là Folder con (VD: Hồ sơ nhân sự) -> Tính tổng recursive bên trong nó
                    sub_count = count_files_in_subtree(child['id'])
                    breakdown.append({
                        "id": child['id'],
                        "name": child['name'],
                        "count": sub_count
                    })
                else:
                    # Nếu là File lẻ -> Cộng vào root_files_count
                    root_files_count += 1
            
            # Sắp xếp breakdown theo tên cho đẹp
            breakdown.sort(key=lambda x: x['name'])

            return {
                "total_files": total_files,
                "root_files_count": root_files_count,
                "breakdown": breakdown
            }

        except Exception as e:
            print(f"❌ Lỗi thống kê chi tiết: {e}")
            return {"total_files": 0, "root_files_count": 0, "breakdown": []}

drive_service = GoogleDriveService()