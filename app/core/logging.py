from sqlalchemy.orm import Session
from app.modules.users.model import User
from app.modules.organization.model import AuditLog
from fastapi.encoders import jsonable_encoder
from typing import Any, Dict, Optional

def create_audit_log(
    db: Session,
    user: User,
    action: str,
    entity_table: str,
    entity_id: Optional[int],
    old_value: Optional[Dict[str, Any]] = None,
    new_value: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None  # <--- [BỔ SUNG] Thêm tham số này
    # detail: Optional[str] = None
):
    """
    Hàm tiện ích để ghi log hệ thống.
    """
    try:
        # Xử lý dữ liệu để đảm bảo lưu được vào JSON (loại bỏ các object không serialize được như datetime)
        safe_old = jsonable_encoder(old_value) if old_value else None
        safe_new = jsonable_encoder(new_value) if new_value else None

        log_entry = AuditLog(
            user_id=user.user_id,
            action=action,
            entity_table=entity_table,
            entity_id=entity_id,
            old_value=safe_old,
            new_value=safe_new,
            ip_address=ip_address,  # <--- [BỔ SUNG] Thêm tham số này
            # Nếu bạn muốn lưu detail, bạn có thể thêm cột detail vào model AuditLog 
            # hoặc nhét nó vào new_value dưới dạng key đặc biệt
        )
        
        db.add(log_entry)
        db.commit()
    except Exception as e:
        # Quan trọng: Không để lỗi ghi log làm crash luồng nghiệp vụ chính
        print(f"FAILED TO WRITE AUDIT LOG: {e}")
        db.rollback()
        
from fastapi import Request

def get_client_ip(request: Request) -> str:
    # 1. Ưu tiên lấy từ Header 'X-Forwarded-For' (nếu chạy sau Proxy/Load Balancer)
    x_forwarded = request.headers.get("X-Forwarded-For")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    
    # 2. Nếu không có proxy, lấy từ request.client
    if request.client:
        return request.client.host
    
    # 3. Trường hợp xấu nhất (request.client bị None)
    return "0.0.0.0"  # Hoặc "unknown"