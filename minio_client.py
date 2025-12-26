from minio import Minio
from minio.deleteobjects import DeleteObject
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
MINIO_BUCKET_JKANCON = "jkancon" # Bucket mới             
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
            # 2. [THÊM] Tạo luôn bucket "jkancon" lúc khởi tạo cho chắc ăn
            if not self.client.bucket_exists(MINIO_BUCKET_JKANCON):
                self.client.make_bucket(MINIO_BUCKET_JKANCON)
                logger.info(f"Đã tạo bucket dự án: {MINIO_BUCKET_JKANCON}")
                
            logger.info("-> MinIO: Kết nối thành công!")
        except Exception as e:
            logger.error(f"-> MinIO LỖI KẾT NỐI: {e}")

    def upload_file(self, file_path, object_name, content_type="application/octet-stream",bucket_name=None):
        if not self.client:
            return None
        
        try:
            target_bucket = bucket_name if bucket_name else MINIO_BUCKET
            # Upload file lên MinIO (MinIO hỗ trợ UTF-8 nên tên file tiếng Việt vẫn OK)
            self.client.fput_object(
                target_bucket,
                object_name,
                file_path,
                content_type=content_type
            )
            
            # [QUAN TRỌNG] Mã hóa URL để đảm bảo an toàn tuyệt đối khi lưu vào DB và click link
            # safe='/' để giữ lại dấu gạch chéo phân cách thư mục
            safe_object_name = quote(object_name, safe='/')

            protocol = "https" if MINIO_SECURE else "http"
            url = f"{protocol}://{MINIO_ENDPOINT}/{target_bucket}/{safe_object_name}"
            return url
        except Exception as e:
            logger.error(f"-> MinIO Upload Lỗi: {e}")
            return None

    def download_file(self, object_name, local_file_path):
        """
        Tải file từ MinIO về máy local.
        :param object_name: Đường dẫn file trên MinIO (VD: ho_so_2025/file.pdf)
        :param local_file_path: Đường dẫn lưu file trên máy (VD: ./temp/file.pdf)
        """
        if not self.client:
            logger.error("Client MinIO chưa được khởi tạo.")
            return False
        
        try:
            # Sử dụng hàm fget_object của thư viện Minio để tải file
            self.client.fget_object(
                bucket_name=MINIO_BUCKET,
                object_name=object_name,
                file_path=local_file_path
            )
            logger.info(f"-> MinIO: Đã tải file thành công về {local_file_path}")
            return True
        except Exception as e:
            logger.error(f"-> MinIO Download Lỗi: {e}")
            return False
        
    def delete_file(self, object_name, bucket_name="jkancon"):
        """
        Xóa file trên MinIO.
        :param object_name: Đường dẫn file (VD: 102/bao_cao.pdf)
        """
        if not self.client:
            return False
            
        try:
            self.client.remove_object(bucket_name, object_name)
            logger.info(f"-> MinIO: Đã xóa file {object_name} trong bucket {bucket_name}")
            return True
        except Exception as e:
            logger.error(f"-> MinIO Delete Error: {e}")
            return False
        
    def delete_folder(self, folder_prefix, bucket_name="jkancon"):
        """
        Xóa toàn bộ file có prefix (coi như là folder).
        """
        if not self.client:
            return False
            
        try:
            # 1. Liệt kê tất cả đối tượng
            objects_to_delete = self.client.list_objects(bucket_name, prefix=folder_prefix, recursive=True)
            
            # --- [SỬA LỖI TẠI ĐÂY] ---
            # Thay vì dùng map/lambda, ta dùng List Comprehension.
            # Logic: "if obj.object_name" đảm bảo tên file không phải None, lúc đó Type Checker sẽ hiểu đây chắc chắn là str.
            delete_list = [
                DeleteObject(obj.object_name) 
                for obj in objects_to_delete 
                if obj.object_name
            ]
            # -------------------------
            
            # Nếu folder rỗng (không có file nào để xóa) thì return True luôn
            if not delete_list:
                return True

            # 2. Thực hiện xóa
            errors = self.client.remove_objects(bucket_name, delete_list)
            
            error_count = 0
            for error in errors:
                logger.error(f"Lỗi khi xóa file {error.name}: {error.message}")
                error_count += 1
            
            if error_count > 0:
                return False
                
            logger.info(f"-> MinIO: Đã dọn sạch folder {folder_prefix} trong bucket {bucket_name}")
            return True

        except Exception as e:
            logger.error(f"-> MinIO Delete Folder Error: {e}")
            return False
minio_handler = MinIOHandler()