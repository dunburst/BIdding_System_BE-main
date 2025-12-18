import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# --- CẤU HÌNH ---
SERVICE_ACCOUNT_FILE = 'service_account.json'
SCOPES = ['https://www.googleapis.com/auth/drive']

# 👇 DÁN ID THƯ MỤC CỦA BẠN VÀO ĐÂY (Thư mục đã share quyền Editor cho email Service Account)
SHARED_FOLDER_ID = "1mnemuaGkv16h5jVf-ptBorudAltlxJ8p" 

class GoogleDriveService:
    def __init__(self):
        self.creds = None
        self.service = None
        
        if os.path.exists(SERVICE_ACCOUNT_FILE):
            self.creds = Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE, scopes=SCOPES)
            self.service = build('drive', 'v3', credentials=self.creds)
            print("✅ Kết nối Google Drive Service Account thành công!")
        else:
            print("❌ Lỗi: Không tìm thấy file service_account.json")

    def list_files(self, folder_id=None):
        """Liệt kê tất cả file trong thư mục"""
        # Nếu không truyền folder_id thì lấy thư mục mặc định trong cấu hình
        target_id = folder_id if folder_id else SHARED_FOLDER_ID
        
        if "Dien_ID" in target_id:
             print("⚠️ Cảnh báo: Bạn chưa điền SHARED_FOLDER_ID trong code!")
             return []

        try:
            # Query: Lấy file trong thư mục cha, không lấy file trong thùng rác
            query = f"'{target_id}' in parents and trashed=false"
            
            results = self.service.files().list(
                q=query,
                pageSize=100, # Lấy tối đa 100 file mỗi lần
                fields="nextPageToken, files(id, name, mimeType, webViewLink, createdTime, webContentLink)",
                orderBy="createdTime desc" # Sắp xếp mới nhất lên đầu
            ).execute()
            
            return results.get('files', [])
        except Exception as e:
            print(f"❌ Lỗi khi lấy danh sách file: {str(e)}")
            return []

# Instance dùng chung
drive_service = GoogleDriveService()