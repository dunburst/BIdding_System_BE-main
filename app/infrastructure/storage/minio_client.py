from minio import Minio
from minio.deleteobjects import DeleteObject
import logging
import os
from urllib.parse import quote

# --- CẤU HÌNH MINIO ---
# Nếu chạy bot trên cùng máy cài MinIO thì để localhost.
# Nếu bot chạy máy khác thì thay bằng IP máy chứa MinIO (VD: 192.168.1.xxx)
# --- CẤU HÌNH MINIO (Ưu tiên lấy từ biến môi trường Docker, nếu không có mới lấy giá trị mặc định) ---
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000").strip()
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin_user").strip()
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "MinioStrongPassword2024!").strip()
MINIO_PUBLIC_URL = os.getenv("MINIO_PUBLIC_URL", "").strip()  # URL public cho frontend truy cập
MINIO_BUCKET = "files"
MINIO_BUCKET_JKANCON = "jkancon"
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").strip().lower() == "true"

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

    def upload_file(self, file_path, object_name, content_type="application/octet-stream", bucket_name=None):
        if not self.client:
            return None
        try:
            target_bucket = bucket_name if bucket_name else MINIO_BUCKET
            # Upload file lên MinIO
            self.client.fput_object(
                target_bucket,
                object_name,
                file_path,
                content_type=content_type
            )


            # Mã hóa URL
            safe_object_name = quote(object_name, safe='/')
            protocol = "https" if MINIO_SECURE else "http"
            base = MINIO_PUBLIC_URL if MINIO_PUBLIC_URL else f"{protocol}://{MINIO_ENDPOINT}"
            url = f"{base}/{target_bucket}/{safe_object_name}"
            return url
        except Exception as e:
            logger.error(f"-> MinIO Upload Lỗi: {e}")
            return None

    # [MỚI] Hàm này dùng để upload file từ API (dạng bytes/stream)
    def upload_file_obj(self, file_data, length, object_name, content_type="application/octet-stream", bucket_name=None):
        if not self.client:
            return None

        try:
            target_bucket = bucket_name if bucket_name else MINIO_BUCKET
        
            # Sử dụng put_object thay vì fput_object
            self.client.put_object(
                bucket_name=target_bucket,
                object_name=object_name,
                data=file_data,
                length=length,
                content_type=content_type
            )

           

            # Tạo URL trả về
            safe_object_name = quote(object_name, safe='/')
            protocol = "https" #if MINIO_SECURE else "http"
            url = f"{protocol}://{MINIO_ENDPOINT}/{target_bucket}/{safe_object_name}"
            return url
        except Exception as e:
            logger.error(f"-> MinIO Upload Stream Lỗi: {e}")
            return None

    def download_file(self, object_name, local_file_path):
        """
        Tải file từ MinIO về máy local.
        """
        if not self.client:
            logger.error("Client MinIO chưa được khởi tạo.")
            return False
    
        try:
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
    
    def extract_object_name_from_url(self, file_url: str, bucket_name: str = None) -> str | None:
        """Trích xuất object_name từ URL đã lưu trong DB."""
        target_bucket = bucket_name or MINIO_BUCKET
        marker = f"/{target_bucket}/"
        idx = file_url.find(marker)
        if idx == -1:
            return None
        from urllib.parse import unquote
        return unquote(file_url[idx + len(marker):])

    def get_object_stream(self, object_name: str, bucket_name: str = None):
        """Trả về (response, stat) để streaming file qua backend."""
        if not self.client:
            return None, None
        try:
            target_bucket = bucket_name or MINIO_BUCKET
            stat = self.client.stat_object(target_bucket, object_name)
            response = self.client.get_object(target_bucket, object_name)
            return response, stat
        except Exception as e:
            logger.error(f"-> MinIO GetObject Error: {e}")
            return None, None

    def delete_file(self, object_name, bucket_name="jkancon"):
        """
        Xóa file trên MinIO.
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
           
            delete_list = [
                DeleteObject(obj.object_name)
                for obj in objects_to_delete
                if obj.object_name
            ]
           
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