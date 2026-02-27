from pydantic import BaseModel, EmailStr, Field, computed_field
from typing import Optional, Any
from app.core.utils.enum import SecurityLevel, UserRole

# --- BASE SCHEMA (Dùng chung) ---
class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: UserRole = UserRole.ENGINEER
    avatar_url: Optional[str] = None
    
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
    avatar_url: Optional[str] = None
    org_unit_id: Optional[int] = None
    job_title: Optional[str] = None
    security_clearance: Optional[SecurityLevel] = None
    status: Optional[bool] = None
    
    # Optional: Nếu muốn cho phép đổi mật khẩu ở đây thì thêm field password
    # password: Optional[str] = None 

# --- RESPONSE SCHEMA (Trả về client) ---

# [MỚI] Schema dùng cho hành động đổi mật khẩu
class UserChangePassword(BaseModel):
    # old_password: str = Field(..., description="Mật khẩu hiện tại")
    new_password: str = Field(..., min_length=6, description="Mật khẩu mới")
    confirm_password: str = Field(..., min_length=6, description="Nhập lại mật khẩu mới")

    # (Tùy chọn) Validate khớp password ngay tại schema
    @computed_field
    def check_passwords_match(self) -> None:
        if self.new_password != self.confirm_password:
            raise ValueError('Mật khẩu mới và xác nhận mật khẩu không khớp')
class UserResponse(UserBase):
    user_id: int
    
    # Có thể thêm thông tin OrgUnit nếu muốn hiển thị tên phòng ban (cần config ORM)
    # org_unit_name: Optional[str] = None 
    org_unit: Optional[Any] = Field(None, exclude=True)

    class Config:
        from_attributes = True
        
    @computed_field
    @property
    def org_unit_name(self) -> Optional[str]:
        """
        Tự động lấy tên phòng ban từ quan hệ org_unit.
        Nếu user chưa gán phòng ban, trả về None.
        """
        # self.org_unit là truy cập vào relationship trong Model
        if hasattr(self, "org_unit") and self.org_unit:
            return self.org_unit.unit_name
        return None
    # --- [MỚI] THÊM PHẦN NÀY ---
    @computed_field
    @property
    def parent_org_unit_name(self) -> Optional[str]:
        """Lấy tên phòng ban CHA (nếu có)"""
        # Kiểm tra user có phòng ban không -> Kiểm tra phòng ban đó có cha không
        if (
            hasattr(self, "org_unit") 
            and self.org_unit 
            and hasattr(self.org_unit, "parent") 
            and self.org_unit.parent
        ):
            return self.org_unit.parent.unit_name
        return None