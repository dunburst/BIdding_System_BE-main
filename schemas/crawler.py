# schemas/crawler.py
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Any
from decimal import Decimal

# --- SCHEMAS CHO CRAWL SCHEDULE (Giữ nguyên) ---
class CrawlScheduleBase(BaseModel):
    source_id: int = Field(..., description="ID nguồn dữ liệu (1: Muasamcong, v.v.)")
    cron_expression: str = Field(..., description="Chuỗi cron (VD: '0 */2 * * *')")
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
    priority: int = 1

    # QUAN TRỌNG: Validator để chuyển None -> []
    @field_validator('keywords_include', 'keywords_exclude', 'locations', mode='before')
    @classmethod
    def convert_none_to_list(cls, v: Any):
        if v is None:
            return []
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
    priority: Optional[int] = None

class CrawlRuleResponse(CrawlRuleBase):
    id: int

    class Config:
        from_attributes = True