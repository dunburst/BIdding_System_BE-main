from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional, List
from decimal import Decimal
from datetime import datetime

class CrawlRuleBase(BaseModel):
    rule_name: str
    business_field: Optional[str] = None
    keywords_include: List[str] = []
    keywords_exclude: List[str] = []
    min_budget: Optional[Decimal] = None
    max_budget: Optional[Decimal] = None
    locations: List[str] = []
    priority: int = 1

class CrawlRuleCreate(CrawlRuleBase):
    pass

class CrawlRuleUpdate(BaseModel):
    rule_name: Optional[str] = None
    business_field: Optional[str] = None
    keywords_include: Optional[List[str]] = []
    keywords_exclude: List[str] = []
    min_budget: Optional[Decimal] = None
    max_budget: Optional[Decimal] = None
    locations: List[str] = []
    priority: int = 1

class CrawlRuleResponse(CrawlRuleBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# Validator này giúp biến đổi NULL từ DB thành [] rỗng
    @field_validator('keywords_include', 'keywords_exclude', 'locations', mode='before')
    def parse_empty_list(cls, v):
        if v is None:
            return []
        # Nếu SQL Server trả về chuỗi JSON string thay vì list object (trường hợp hiếm)
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except:
                return []
        return v

# ==========================================
# CRAWL SCHEDULE SCHEMAS
# ==========================================
class CrawlScheduleBase(BaseModel):
    source_id: int
    cron_expression: str
    description: Optional[str] = None
    is_active: bool = True

class CrawlScheduleCreate(CrawlScheduleBase):
    pass

class CrawlScheduleUpdate(BaseModel):
    source_id: Optional[int] = None
    cron_expression: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class CrawlScheduleResponse(CrawlScheduleBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

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