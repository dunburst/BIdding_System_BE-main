import os
import io
import zipfile
from typing import List, Optional, Any
import httplib2
import urllib3
import asyncio

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
                fields='id, name, mimeType, properties'
            ).execute()
        except Exception as e:
            print(f"❌ Lỗi get metadata: {e}")
            return None

    def create_folder(self, folder_name: str, parent_id: Optional[str] = None) -> Optional[str]:
        try:
            target_parent = parent_id if parent_id else self.ROOT_FOLDER_ID
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [target_parent]
            }
            folder = self.service.files().create(
                body=file_metadata, fields='id'
            ).execute()
            return folder.get('id')
        except Exception as e:
            print(f"❌ Lỗi tạo folder: {e}")
            return None

    def create_project_tree(self, project_name: str):
        project_id = self.create_folder(project_name, self.ROOT_FOLDER_ID)
        if not project_id: return None

        sub_folders_list = [
            "01. Hồ sơ Pháp lý & Năng lực",
            "02. Hồ sơ nhân sự",
            "03. Biện pháp Thi công",
            "04. Hồ sơ tài chính",
            "05. Hồ sơ máy móc thiết bị",
            "06. Hồ sơ hợp đông tương tự",
            "07. Hồ sơ khác"
        ]

        created_folders = []
        for folder_name in sub_folders_list:
            sub_id = self.create_folder(folder_name, project_id)
            if sub_id:
                created_folders.append({"name": folder_name, "id": sub_id})
            
        return {
            "project_name": project_name,
            "project_id": project_id,
            "sub_folders": created_folders
        }

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
                fields="files(id, name, mimeType, webViewLink, properties)", 
                orderBy="folder, createdTime desc"
            ).execute()
            return results.get('files', [])
        except Exception as e:
            print(f"❌ Lỗi list file: {str(e)}")
            return []

    # --- NHÓM 2: NGHIỆP VỤ MỞ RỘNG ---

    def search_files(self, query_name: str, folder_id: Optional[str] = None) -> List[dict]:
        if not self.service: return []
        try:
            # Câu truy vấn cơ bản
            q_parts = [f"name contains '{query_name}'", "trashed=false"]
            
            # --- LOGIC MỚI: Nếu có folder_id thì thêm điều kiện tìm trong folder đó ---
            if folder_id:
                # Lưu ý: 'in parents' của Google chỉ tìm trong folder cha trực tiếp (Cấp 1)
                # Google Drive API không hỗ trợ native query "tìm trong folder và tất cả folder con" 
                # mà phải dùng logic code phức tạp hơn. Cách này là tìm trong folder hiện tại.
                q_parts.append(f"'{folder_id}' in parents")
            
            # Nối các điều kiện lại bằng 'and'
            final_query = " and ".join(q_parts)

            results = self.service.files().list(
                q=final_query, 
                pageSize=50,
                fields="files(id, name, mimeType, webViewLink, createdTime, parents, properties)", 
                orderBy="folder, createdTime desc"
            ).execute()
            return results.get('files', [])
        except Exception as e:
            print(f"❌ Lỗi search: {e}")
            return []

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

drive_service = GoogleDriveService()