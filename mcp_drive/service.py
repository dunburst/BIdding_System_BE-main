import os
import io
from google.oauth2.credentials import Credentials 
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from fastapi import UploadFile
from dotenv import load_dotenv

load_dotenv() # Load biến môi trường

class GoogleDriveService:
    def __init__(self):
        self.service = None
        self.SHARED_FOLDER_ID = os.getenv("GOOGLE_DRIVE_SHARED_FOLDER_ID")
        
        # Lấy thông tin OAuth 2.0 từ .env
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")

        if client_id and client_secret and refresh_token:
            # Tạo Credentials giả danh User thật
            self.creds = Credentials(
                None, # Access token (để None nó tự lấy lại bằng refresh token)
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=client_secret
            )
            self.service = build('drive', 'v3', credentials=self.creds)
        else:
            print("❌ Lỗi: Thiếu cấu hình OAuth (Client ID/Secret/Refresh Token)")

    async def upload_file_with_security(self, file: UploadFile, security_level: int = 1):
        """
        Upload file từ RAM lên Drive kèm metadata security_level
        """
        if not self.service or not self.SHARED_FOLDER_ID:
            return None

        try:
            # 1. Đọc nội dung file vào RAM (BytesIO)
            file_content = await file.read()
            file_stream = io.BytesIO(file_content)

            # 2. Tạo metadata
            file_metadata = {
                'name': file.filename,
                'parents': [self.SHARED_FOLDER_ID],
                'properties': {
                    'security_level': str(security_level) # Quan trọng: Lưu level vào đây
                }
            }
            
            # 3. Tạo Media Object từ RAM (Không cần lưu file tạm)
            media = MediaIoBaseUpload(
                file_stream, 
                mimetype=file.content_type, 
                resumable=True
            )
            
            # 4. Upload
            drive_file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, webViewLink, properties'
            ).execute()

            return drive_file
            
        except Exception as e:
            print(f"❌ Lỗi upload: {str(e)}")
            return None

    def list_files_with_metadata(self):
        """Lấy danh sách file và lọc theo properties"""
        if not self.service or not self.SHARED_FOLDER_ID: return []
        
        try:
            query = f"'{self.SHARED_FOLDER_ID}' in parents and trashed=false"
            results = self.service.files().list(
                q=query,
                pageSize=100,
                # Lấy thêm properties để biết file này mật hay không
                fields="files(id, name, webViewLink, properties)", 
                orderBy="createdTime desc"
            ).execute()

            return results.get('files', [])
        except Exception as e:
            print(f"❌ Lỗi list file: {str(e)}")
            return []

# Khởi tạo singleton
drive_service = GoogleDriveService()