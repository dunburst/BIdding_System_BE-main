# Import service đã khởi tạo của bạn
from app.integrations.google.mcp_drive.service import drive_service

def check_file_location(file_id):
    try:
        # 1. Lấy thông tin Parents của file
        file_meta = drive_service.service.files().get(
            fileId=file_id, 
            fields='id, name, parents'
        ).execute()
        
        print(f"📄 File: {file_meta.get('name')}")
        
        parents = file_meta.get('parents', [])
        if not parents:
            print("⚠️ File này nằm ở Root (My Drive) hoặc không có cha.")
            return

        # 2. Lấy tên của Folder cha
        parent_id = parents[0]
        parent_meta = drive_service.service.files().get(
            fileId=parent_id, 
            fields='id, name'
        ).execute()
        
        print(f"📂 Đang nằm trong Folder: [{parent_meta.get('name')}]")
        print(f"🔑 ID Folder cha: {parent_id}")
        
    except Exception as e:
        print(f"Lỗi: {e}")

# Chạy thử với ID file vừa upload
check_file_location("1tcr_1HaLfXWJV652Fifb3v4WjzN3yRq1")