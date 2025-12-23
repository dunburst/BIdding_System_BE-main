from minio import Minio
import logging
import os
from urllib.parse import quote

# --- CẤU HÌNH MINIO ---
# Nếu chạy bot trên cùng máy cài MinIO thì để localhost.
# Nếu bot chạy máy khác thì thay bằng IP máy chứa MinIO (VD: 192.168.1.xxx)
MINIO_ENDPOINT = "10.10.0.158:9000"  
MINIO_ACCESS_KEY = "admin_user"    
MINIO_SECRET_KEY = "MinioStrongPassword2024!" 
MINIO_BUCKET = "files"             
MINIO_SECURE = False               # False vì chạy http (chưa có SSL)

logger = logging.getLogger("MinIO")

class MinIOHandler:
    def __init__(self):
        self.client = None
        try:
            self.client = Minio(
                MINIO_ENDPOINT,
                access_key=MINIO_ACCESS_KEY,
                secret_key=MINIO_SECRET_KEY,
                secure=MINIO_SECURE
            )
            # Tạo bucket nếu chưa có
            if not self.client.bucket_exists(MINIO_BUCKET):
                self.client.make_bucket(MINIO_BUCKET)
                logger.info(f"Đã tạo bucket: {MINIO_BUCKET}")
            
            logger.info("-> MinIO: Kết nối thành công!")
        except Exception as e:
            logger.error(f"-> MinIO LỖI KẾT NỐI: {e}")

    def upload_file(self, file_path, object_name, content_type="application/octet-stream"):
        if not self.client:
            return None
        
        try:
            # Upload file lên MinIO (MinIO hỗ trợ UTF-8 nên tên file tiếng Việt vẫn OK)
            self.client.fput_object(
                MINIO_BUCKET,
                object_name,
                file_path,
                content_type=content_type
            )
            
            # [QUAN TRỌNG] Mã hóa URL để đảm bảo an toàn tuyệt đối khi lưu vào DB và click link
            # safe='/' để giữ lại dấu gạch chéo phân cách thư mục
            safe_object_name = quote(object_name, safe='/')

            protocol = "https" if MINIO_SECURE else "http"
            url = f"{protocol}://{MINIO_ENDPOINT}/{MINIO_BUCKET}/{safe_object_name}"
            return url
        except Exception as e:
            logger.error(f"-> MinIO Upload Lỗi: {e}")
            return None

    # --- [THÊM MỚI] Hàm này cần thiết cho AI Service để tải file về ---
    def download_file(self, object_name, local_path):
        """
        Tải file từ MinIO về máy local (để AI đọc)
        """
        if not self.client: return False
        try:
            self.client.fget_object(MINIO_BUCKET, object_name, local_path)
            logger.info(f"-> MinIO: Đã tải file về {local_path}")
            return True
        except Exception as e:
            logger.error(f"-> MinIO Download Lỗi: {e}")
            return False

# --- QUAN TRỌNG: Phải khởi tạo instance ở đây để các file khác import được ---
minio_handler = MinIOHandler()