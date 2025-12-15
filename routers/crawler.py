# routers/crawler.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from crawler_bot import reload_scheduler

from database import get_db
from schemas.base import BaseResponse
from schemas.crawler import (
    CrawlScheduleResponse, CrawlScheduleCreate, CrawlScheduleUpdate,
    CrawlRuleResponse, CrawlRuleCreate, CrawlRuleUpdate
)
import cruds.crawler as crawler_crud

router = APIRouter(
    prefix="/crawler-config",
    tags=["Crawler Configuration"]
)

# ==========================================
# 1. API CHO SCHEDULE (LỊCH TRÌNH)
# ==========================================
@router.get("/schedules", response_model=BaseResponse[List[CrawlScheduleResponse]])
def read_schedules(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    data = crawler_crud.get_schedules(db, skip=skip, limit=limit)
    return BaseResponse(success=True, status=200, message="Lấy danh sách lịch trình thành công", data=data)

@router.post("/schedules", response_model=BaseResponse[CrawlScheduleResponse])
def create_schedule(schedule: CrawlScheduleCreate, db: Session = Depends(get_db)):
    data = crawler_crud.create_schedule(db, schedule)
    return BaseResponse(success=True, status=201, message="Tạo lịch trình thành công", data=data)

@router.put("/schedules/{id}", response_model=BaseResponse[CrawlScheduleResponse])
def update_schedule(id: int, schedule: CrawlScheduleUpdate, db: Session = Depends(get_db)):
    data = crawler_crud.update_schedule(db, id, schedule)
    # 2. TỰ ĐỘNG RELOAD BOT (Thêm dòng này)
    reload_scheduler() 
    if not data:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch trình")
    return BaseResponse(success=True, status=200, message="Cập nhật thành công", data=data)

@router.delete("/schedules/{id}", response_model=BaseResponse[None])
def delete_schedule(id: int, db: Session = Depends(get_db)):
    success = crawler_crud.delete_schedule(db, id)
    if not success:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch trình")
    return BaseResponse(success=True, status=200, message="Xóa thành công", data=None)

# ==========================================
# 2. API CHO RULE (LUẬT TÌM KIẾM)
# ==========================================
@router.get("/rules", response_model=BaseResponse[List[CrawlRuleResponse]])
def read_rules(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    data = crawler_crud.get_rules(db, skip=skip, limit=limit)
    return BaseResponse(success=True, status=200, message="Lấy danh sách luật thành công", data=data)

@router.post("/rules", response_model=BaseResponse[CrawlRuleResponse])
def create_rule(rule: CrawlRuleCreate, db: Session = Depends(get_db)):
    data = crawler_crud.create_rule(db, rule)
    return BaseResponse(success=True, status=201, message="Tạo luật thành công", data=data)

@router.put("/rules/{id}", response_model=BaseResponse[CrawlRuleResponse])
def update_rule(id: int, rule: CrawlRuleUpdate, db: Session = Depends(get_db)):
    data = crawler_crud.update_rule(db, id, rule)
    if not data:
        raise HTTPException(status_code=404, detail="Không tìm thấy luật")
    return BaseResponse(success=True, status=200, message="Cập nhật luật thành công", data=data)

@router.delete("/rules/{id}", response_model=BaseResponse[None])
def delete_rule(id: int, db: Session = Depends(get_db)):
    success = crawler_crud.delete_rule(db, id)
    if not success:
        raise HTTPException(status_code=404, detail="Không tìm thấy luật")
    return BaseResponse(success=True, status=200, message="Xóa luật thành công", data=None)