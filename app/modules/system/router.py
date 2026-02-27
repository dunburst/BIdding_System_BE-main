from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import inspect
from app.core.utils.base_model import BaseResponse
from app.core.permission.constants import AbacAction
from typing import List
from app.infrastructure.database.database import get_db  # Import hàm get_db từ file cấu hình của bạn
from app.core.utils.base_model import BaseResponse
from app.core.permission.constants import AbacAction
from typing import List
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
    
@router.get("/actions", response_model=BaseResponse[List[str]])
def get_system_actions():
    """
    Trả về danh sách tất cả các Action có trong hệ thống.
    Dùng để Frontend render dropdown hoặc check quyền.
    """
    # Gọi hàm list_all() có sẵn trong class của bạn
    actions = AbacAction.list_all()
    
    return BaseResponse(
        success=True,
        status=200,
        message="Lấy danh sách hành động thành công",
        data=actions
    )