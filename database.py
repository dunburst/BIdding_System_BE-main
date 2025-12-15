from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
import urllib.parse

# 1. Load biến môi trường
load_dotenv()

server = os.getenv("DB_SERVER")
database = os.getenv("DB_NAME")
username = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")
driver = os.getenv("DB_DRIVER")

# 2. Tạo Connection String chuẩn cho SQL Server
# Sử dụng urllib để encode password nếu có ký tự đặc biệt
params = urllib.parse.quote_plus(
    f"DRIVER={{{driver}}};"
    f"SERVER={server};"
    f"DATABASE={database};"
    f"UID={username};"
    f"PWD={password};"
    "TrustServerCertificate=yes;"  # Cần thiết nếu dùng driver mới (v18+)
)

DATABASE_URL = f"mssql+pyodbc:///?odbc_connect={params}"

# 3. Khởi tạo Engine
# THÊM 'use_setinputsizes=False': Đây là cấu hình quan trọng để sửa lỗi Tiếng Việt với pyodbc
engine = create_engine(
    DATABASE_URL, 
    echo=True, # echo=True để log câu SQL ra màn hình debug
    use_setinputsizes=False 
)

# 4. Tạo Session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 5. Base class cho Models
Base = declarative_base()

# Dependency để lấy DB session trong API
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()