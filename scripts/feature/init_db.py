# init_db.py
import logging
from app.infrastructure.database.database import engine, Base
from app.modules.users.model import User  # <--- BẮT BUỘC PHẢI IMPORT MODELS ĐỂ SQLALCHEMY NHẬN DIỆN LỚP

# Cấu hình log đơn giản
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("InitDB")

def init_db():
    try:
        logger.info("Đang kết nối và tạo bảng trong Database...")
        
        # Dòng lệnh này sẽ quét tất cả các class kế thừa từ Base (trong models.py)
        # và tạo bảng tương ứng trong SQL Server nếu chưa có.
        Base.metadata.create_all(bind=engine)
        
        logger.info("✅ TẠO BẢNG THÀNH CÔNG! (Tables created)")
    except Exception as e:
        logger.error(f"❌ LỖI TẠO BẢNG: {e}")

if __name__ == "__main__":
    init_db()