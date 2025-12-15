from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from schemas import crawl as schemas
from cruds import crawler as crud_crawl
from models import CrawlLog
from crawler_bot import reload_scheduler

router = APIRouter(
    prefix="/crawl-rules",
    tags=["Crawl Rules"]
)

@router.post("/schedules/reload")
def reload_schedules_api():
    """API để làm mới lịch chạy sau khi sửa Database"""
    success = reload_scheduler()
    if success:
        return {"message": "Đã cập nhật lịch chạy thành công!", "status": "success"}
    else:
        raise HTTPException(status_code=500, detail="Scheduler chưa chạy hoặc gặp lỗi")
@router.get("/logs", response_model=List[schemas.CrawlLogResponse])
def get_crawl_logs(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    # Sắp xếp log mới nhất lên đầu
    logs = db.query(CrawlLog).order_by(CrawlLog.start_time.desc()).offset(skip).limit(limit).all()
    
    # Mẹo nhỏ: Map thêm rule_name thủ công nếu lười join phức tạp
    # (Hoặc dùng relationship trong model để tự map)
    for log in logs:
        if log.rule:
            log.rule_name = log.rule.rule_name
            
    return logs
@router.post("/", response_model=schemas.CrawlRuleResponse)
def create_rule(rule: schemas.CrawlRuleCreate, db: Session = Depends(get_db)):
    return crud_crawl.create_rule(db=db, rule=rule)

@router.get("/", response_model=List[schemas.CrawlRuleResponse])
def read_rules(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud_crawl.get_rules(db, skip=skip, limit=limit)

# ==========================================
# SCHEDULE API
# ==========================================
@router.post("/schedules", response_model=schemas.CrawlScheduleResponse)
def create_schedule(schedule: schemas.CrawlScheduleCreate, db: Session = Depends(get_db)):
    return crud_crawl.create_schedule(db=db, schedule=schedule)

@router.get("/schedules", response_model=List[schemas.CrawlScheduleResponse])
def read_schedules(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud_crawl.get_schedules(db, skip=skip, limit=limit)

@router.put("/schedules/{schedule_id}", response_model=schemas.CrawlScheduleResponse)
def update_schedule(schedule_id: int, schedule_in: schemas.CrawlScheduleUpdate, db: Session = Depends(get_db)):
    # 1. Update DB như bình thường
    updated_sched = crud_crawl.update_schedule(db, schedule_id, schedule_in)
    if not updated_sched:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch chạy")
    
    # 2. TỰ ĐỘNG RELOAD BOT (Thêm dòng này)
    reload_scheduler() 
    
    return updated_sched

@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    success = crud_crawl.delete_schedule(db, schedule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch chạy để xóa")
    return {"message": "Đã xóa lịch thành công"}