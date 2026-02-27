from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.core.utils.enum import AttributeType, AbacAction, PolicyEffect  # Import Enum từ file models của bạn
from app.core.permission.constants import AbacAction 
# ==========================================
# SCHEMAS CHO ABAC ATTRIBUTE
# ==========================================

class AbacAttributeBase(BaseModel):
    attr_key: str = Field(..., description="Tên biến dùng trong JSON, VD: user.org_unit_id")
    attr_type: AttributeType = Field(default=AttributeType.STRING, description="Kiểu dữ liệu")
    source_table: Optional[str] = Field(None, description="Bảng nguồn dữ liệu")
    description: Optional[str] = Field(None, description="Mô tả chi tiết")
    mapping_path: Optional[str] = Field(
        None, 
        description="Đường dẫn ánh xạ dữ liệu trong code Python. VD: 'org_unit.unit_type' hoặc 'role'")

class AbacAttributeCreate(AbacAttributeBase):
    pass

class AbacAttributeUpdate(BaseModel):
    attr_key: Optional[str] = None
    attr_type: Optional[AttributeType] = None
    source_table: Optional[str] = None
    description: Optional[str] = None
    mapping_path: Optional[str] = None

class AbacAttributeResponse(AbacAttributeBase):
    id: int
    
    model_config = ConfigDict(from_attributes=True)

# ==========================================
# SCHEMAS CHO ABAC POLICY
# ==========================================

class AbacPolicyBase(BaseModel):
    name: str = Field(..., description="Tên chính sách")
    description: Optional[str] = None
    target_resource: str = Field(..., description="Đối tượng chịu tác động, VD: bidding_package")
    # --- THAY ĐỔI Ở ĐÂY ---
    # Chấp nhận List[str]. 
    action: List[str] = Field(
        ..., 
        description="Danh sách hành động cho phép/cấm (Dùng constant AbacAction)",
        json_schema_extra={
            "example": [AbacAction.VIEW, AbacAction.APPROVE_BID] 
        }
    )
    effect: PolicyEffect = Field(default=PolicyEffect.ALLOW)
    priority: int = Field(default=1, description="Độ ưu tiên, số càng lớn càng ưu tiên")
    condition_json: Dict[str, Any] = Field(
        ..., 
        description="Cấu trúc logic JSON",
        json_schema_extra={
            "example": {
                "condition": "AND",
                "rules": [
                    {"field": "user.role", "operator": "eq", "value": "MANAGER"},
                    {"field": "user.org_unit_id", "operator": "eq", "value": "resource.unit_id"}
                ]
            }
        }
    )
    is_active: bool = True

class AbacPolicyCreate(AbacPolicyBase):
    pass

class AbacPolicyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    target_resource: Optional[str] = None
    action: Optional[List[str]] = None
    effect: Optional[PolicyEffect] = None
    priority: Optional[int] = None
    condition_json: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

class AbacPolicyResponse(AbacPolicyBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)