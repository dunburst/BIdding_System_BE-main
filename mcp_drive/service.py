import os
import shutil
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from fastapi import UploadFile

# --- CẤU HÌNH ---
SERVICE_ACCOUNT_FILE = 'service_account.json'
SCOPES = ['https://www.googleapis.com/auth/drive']
SHARED_FOLDER_ID = "1mnemuaGkv16h5jVf-ptBorudAltlxJ8p"  # <--- ID thư mục của bạn

class GoogleDriveService:
    def __init__(self):
        self.creds = None
        self.service = None

        if os.path.exists(SERVICE_ACCOUNT_FILE):
            self.creds = Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE, scopes=SCOPES)
            self.service = build('drive', 'v3', credentials=self.creds)

        else:
            print("❌ Lỗi: Không tìm thấy file service_account.json")

    def upload_file_with_security(self, file: UploadFile, security_level: int = 1):
        """
        Upload file kèm mức độ bảo mật
        security_level: 1 (Public), 2 (Internal), 3 (Confidential), 4 (Secret)
        """
        temp_path = f"temp_{file.filename}"
        media = None
        try:
            with open(temp_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            # Gắn metadata security_level vào properties của file
            file_metadata = {
                'name': file.filename,
                'parents': [SHARED_FOLDER_ID],
                'properties': {
                    'security_level': str(security_level) # Google chỉ cho lưu String
                }
            }
            
            media = MediaFileUpload(temp_path, mimetype=file.content_type, resumable=True)
            
            drive_file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, webViewLink, properties'
            ).execute()

            return drive_file
        except Exception as e:
            print(f"❌ Lỗi upload: {str(e)}")
            return None
        finally:
            if media: del media
            if os.path.exists(temp_path): os.remove(temp_path)

    def list_files_with_metadata(self):
        """Lấy danh sách file kèm thuộc tính bảo mật"""
        try:
            query = f"'{SHARED_FOLDER_ID}' in parents and trashed=false"
            # Lấy thêm trường 'properties' để biết file nào là mật
            results = self.service.files().list(
                q=query,
                pageSize=100,
                fields="files(id, name, webViewLink, properties)",
                orderBy="createdTime desc"
            ).execute()

            return results.get('files', [])
        except Exception as e:
            print(f"❌ Lỗi list file: {str(e)}")
            return []


drive_service = GoogleDriveService()