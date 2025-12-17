from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from models import UserRole, SecurityLevel # Import Enum từ models

# --- BASE SCHEMA (Dùng chung) ---
class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: UserRole = UserRole.ENGINEER
    
    # [MỚI] Các trường ABAC
    org_unit_id: Optional[int] = Field(None, description="ID Phòng/Ban")
    job_title: Optional[str] = None
    security_clearance: SecurityLevel = SecurityLevel.PUBLIC
    status: bool = True

# --- CREATE SCHEMA (Dùng cho tạo mới/đăng ký) ---
class UserCreate(UserBase):
    password: str = Field(..., min_length=6)

# --- UPDATE SCHEMA (Dùng cho chỉnh sửa) ---
class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    
    org_unit_id: Optional[int] = None
    job_title: Optional[str] = None
    security_clearance: Optional[SecurityLevel] = None
    status: Optional[bool] = None
    
    # Optional: Nếu muốn cho phép đổi mật khẩu ở đây thì thêm field password
    # password: Optional[str] = None 

# --- RESPONSE SCHEMA (Trả về client) ---
class UserResponse(UserBase):
    user_id: int
    
    # Có thể thêm thông tin OrgUnit nếu muốn hiển thị tên phòng ban (cần config ORM)
    # org_unit_name: Optional[str] = None 

    class Config:
        from_attributes = True