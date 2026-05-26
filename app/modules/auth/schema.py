from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from app.core.utils.enum import UserRole # Import enum Role từ models

# Dữ liệu người dùng gửi lên để đăng nhập
class LoginRequest(BaseModel):
    email: str
    password: str
    remember_me: bool = False

class UserInfo(BaseModel):
    user_id: int
    email: str
    full_name: Optional[str] = None
    role: str

# 2. Cập nhật LoginResponse để nhúng UserInfo vào
class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    refresh_token: str
    expiresIn: int
    
    # Thay vì để rời rạc, ta gom vào biến 'user'
    user: UserInfo

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    # Mặc định là SPECIALIST nếu không gửi lên
    role: UserRole = UserRole.ENGINEER
    
class UserMeResponse(BaseModel):
    id: int
    email: str
    # Dùng Field(..., alias="...") để đổi tên biến khi trả về JSON
    # Python dùng snake_case (full_name), JSON trả về camelCase (fullName)
    full_name: Optional[str] = Field(None, serialization_alias="fullName")
    role: str
    avatar_url: Optional[str] = Field(None, serialization_alias="avatarUrl")
    status: bool

    class Config:
        # Cho phép map từ object ORM sang Pydantic
        from_attributes = True
        # Cho phép sử dụng alias khi serialize
        populate_by_name = True
        
class RefreshTokenRequest(BaseModel):
    refresh_token: Optional[str] = None # Cho phép None vì có thể lấy từ Cookie