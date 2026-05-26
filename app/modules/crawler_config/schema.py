# schemas/crawler.py
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List, Any
from decimal import Decimal
from datetime import datetime

# --- SCHEMAS CHO CRAWL SCHEDULE (Giữ nguyên) ---
class CrawlScheduleBase(BaseModel):
    source_url: str = Field(..., description="Link nguồn dữ liệu (VD: https://muasamcong.mpi.gov.vn...)")
    cron_expression: str = Field(..., description="Chuỗi cron (VD: '0 */2 * * *')")
    description: Optional[str] = None
    is_active: bool = True

class CrawlScheduleCreate(CrawlScheduleBase):
    pass

class CrawlScheduleUpdate(BaseModel):
    source_url: Optional[str] = None
    cron_expression: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class CrawlScheduleResponse(CrawlScheduleBase):
    id: int

    class Config:
        from_attributes = True

# --- SCHEMAS CHO CRAWL RULE (CẬP NHẬT) ---
class CrawlRuleBase(BaseModel):
    rule_name: str
    business_field: Optional[str] = None
    
    # Cập nhật: Thêm Optional để tránh lỗi validate ban đầu
    keywords_include: Optional[List[str]] = Field(default_factory=list)
    keywords_exclude: Optional[List[str]] = Field(default_factory=list)
    
    min_budget: Optional[Decimal] = None
    max_budget: Optional[Decimal] = None
    
    # Cập nhật: Thêm Optional
    locations: Optional[List[str]] = Field(default_factory=list)
    # --- [BỔ SUNG MỚI] ---
    investor: Optional[List[str]] = Field(default_factory=list, description="Chủ đầu tư")
    commune: Optional[List[str]] = Field(default_factory=list, description="Xã/Phường")
    priority: int = 1
    # --- [BỔ SUNG MỚI] ---
    is_active: bool = True

    # Cập nhật Validator để xử lý None -> [] cho 2 trường mới
    @field_validator('keywords_include', 'keywords_exclude', 'locations', 'investor', 'commune', mode='before')
    @classmethod
    def convert_none_to_list(cls, v: Any):
        if v is None:
            return []
        # Nếu người dùng gửi chuỗi string (VD: "EVN") thay vì list, tự convert thành ["EVN"]
        if isinstance(v, str):
            return [v] 
        return v

class CrawlRuleCreate(CrawlRuleBase):
    pass

class CrawlRuleUpdate(BaseModel):
    rule_name: Optional[str] = None
    business_field: Optional[str] = None
    keywords_include: Optional[List[str]] = None
    keywords_exclude: Optional[List[str]] = None
    min_budget: Optional[Decimal] = None
    max_budget: Optional[Decimal] = None
    locations: Optional[List[str]] = None
    # --- [BỔ SUNG MỚI] ---
    investor: Optional[List[str]] = None
    commune: Optional[List[str]] = None
    priority: Optional[int] = None
    # --- [BỔ SUNG MỚI] ---
    is_active: bool = True

class CrawlRuleResponse(CrawlRuleBase):
    id: int

    class Config:
        from_attributes = True
        
class CrawlLogBase(BaseModel):
    rule_id: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: str
    packages_found: int = 0
    error_message: Optional[str] = None
    
class CrawlLogResponse(CrawlLogBase):
    id: int
    
    # Để hiển thị tên Rule thay vì chỉ hiện ID (Optional - cho Frontend dễ nhìn)
    rule_name: Optional[str] = None 
    
    model_config = ConfigDict(from_attributes=True)

# Nếu bạn muốn API trả về kèm cả thông tin chi tiết của Rule bên trong Log
# Bạn có thể dùng class này (Advanced)
class CrawlLogWithRuleResponse(CrawlLogResponse):
    rule: Optional["CrawlRuleResponse"] = None