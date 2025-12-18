from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import inspect
from database import get_db  # Import hàm get_db từ file cấu hình của bạn

router = APIRouter(prefix="/system", tags=["System"])

@router.get("/tables")
def get_all_table_names(db: Session = Depends(get_db)):
    """
    API lấy danh sách tất cả các bảng đang có trong Database thực tế.
    """
    # 1. Lấy Engine từ Session hiện tại
    engine = db.get_bind()
    
    # 2. Khởi tạo Inspector
    inspector = inspect(engine)
    
    # 3. Lấy danh sách tên bảng
    # Đối với SQL Server, nó sẽ mặc định lấy schema 'dbo'
    table_names = inspector.get_table_names()
    
    return {
        "count": len(table_names),
        "tables": table_names
    }