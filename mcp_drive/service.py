import os
import io
import zipfile
from typing import List, Optional, Any

# --- CÁC IMPORT CHÍNH ---
from google.oauth2.credentials import Credentials 
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from fastapi import UploadFile
from dotenv import load_dotenv

load_dotenv()

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

            # 3. Tạo Http object với cấu hình BỎ QUA kiểm tra SSL
            # disable_ssl_certificate_validation=True là chìa khóa
            try:
                self.service = build(
                    'drive', 'v3', 
                    credentials=self.creds, # Truyền thẳng credentials
                    cache_discovery=False,
                    static_discovery=False 
                )
                print("✅ Kết nối Drive thành công (Native Mode)!")
            except Exception as e:
                print(f"❌ Lỗi kết nối Drive: {e}")
        else:
            print("❌ Lỗi: Thiếu cấu hình OAuth")

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

    async def upload_file_with_security(self, file: UploadFile, folder_id: Optional[str] = None, security_level: int = 1):
        target_folder = folder_id if folder_id else self.ROOT_FOLDER_ID
        if not self.service or not target_folder: return None

        try:
            file_content = await file.read()
            file_stream = io.BytesIO(file_content)

            file_metadata = {
                'name': file.filename,
                'parents': [target_folder],
                'properties': {'security_level': str(security_level)}
            }
            
            media = MediaIoBaseUpload(file_stream, mimetype=file.content_type, resumable=True)
            
            drive_file = self.service.files().create(
                body=file_metadata, media_body=media, fields='id, name, webViewLink, properties'
            ).execute()

            return drive_file
        except Exception as e:
            print(f"❌ Lỗi upload: {str(e)}")
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

    def search_files(self, query_name: str) -> List[dict]:
        if not self.service: return []
        try:
            q = f"name contains '{query_name}' and trashed=false"
            results = self.service.files().list(
                q=q, pageSize=50,
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

drive_service = GoogleDriveService()