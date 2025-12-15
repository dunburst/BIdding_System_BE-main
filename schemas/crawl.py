from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from decimal import Decimal

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
    keywords_include: Optional[List[str]] = None
    keywords_exclude: List[str] = []
    min_budget: Optional[Decimal] = None
    max_budget: Optional[Decimal] = None
    locations: List[str] = []
    priority: int = 1

class CrawlRuleResponse(CrawlRuleBase):
    id: int
    model_config = ConfigDict(from_attributes=True)