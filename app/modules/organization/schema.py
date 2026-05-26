from pydantic import BaseModel, Field
from typing import Optional, List
from app.core.utils.enum import UnitType # Import Enum từ models

# --- BASE SCHEMA ---
class OrganizationalUnitBase(BaseModel):
    unit_name: str = Field(..., description="Tên đơn vị (VD: Ban Tài chính)")
    unit_code: str = Field(..., description="Mã định danh (VD: FIN_DEPT)")
    parent_unit_id: Optional[int] = Field(None, description="ID đơn vị cấp trên (NULL nếu là cấp cao nhất)")
    unit_type: UnitType = Field(..., description="Loại đơn vị: GROUP, BLOCK, BOARD...")
    description: Optional[str] = None
    manager_id: Optional[int] = Field(None, description="ID User trưởng đơn vị")

# --- CREATE SCHEMA ---
class OrganizationalUnitCreate(OrganizationalUnitBase):
    pass

# --- UPDATE SCHEMA ---
class OrganizationalUnitUpdate(BaseModel):
    unit_name: Optional[str] = None
    unit_code: Optional[str] = None
    parent_unit_id: Optional[int] = None
    unit_type: Optional[UnitType] = None
    description: Optional[str] = None
    manager_id: Optional[int] = None

# --- RESPONSE SCHEMA (FLAT) ---
class OrganizationalUnitResponse(OrganizationalUnitBase):
    unit_id: int

    class Config:
        from_attributes = True

# --- RESPONSE SCHEMA (TREE - ĐỆ QUY) ---
# Dùng để hiển thị cây sơ đồ tổ chức
class OrganizationalUnitTreeResponse(OrganizationalUnitResponse):
    children: List["OrganizationalUnitTreeResponse"] = [] # Tự tham chiếu chính nó
    
class UserOrgResponse(BaseModel):
    user_id: int
    full_name: str
    email: str
    job_title: Optional[str] = None
    role: str  # Trả về UserRole (enum) dạng string
    
    class Config:
        from_attributes = True