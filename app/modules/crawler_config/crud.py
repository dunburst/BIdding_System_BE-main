# cruds/crawler.py
from sqlalchemy.orm import Session
from app.modules.crawler_config.model import CrawlSchedule, CrawlRule, CrawlLog
from app.modules.crawler_config.schema import CrawlScheduleCreate, CrawlScheduleUpdate, CrawlRuleCreate, CrawlRuleUpdate
from typing import Optional
from sqlalchemy import desc

# === SCHEDULE CRUD ===
def get_schedules(db: Session, skip: int = 0, limit: int = 100):
    # FIX: Thêm .order_by(CrawlSchedule.id.desc()) trước .offset
    return db.query(CrawlSchedule).order_by(CrawlSchedule.id.desc()).offset(skip).limit(limit).all()

def get_schedule_by_id(db: Session, schedule_id: int):
    return db.query(CrawlSchedule).filter(CrawlSchedule.id == schedule_id).first()

def create_schedule(db: Session, schedule: CrawlScheduleCreate):
    db_schedule = CrawlSchedule(**schedule.model_dump())
    db.add(db_schedule)
    db.commit()
    db.refresh(db_schedule)
    return db_schedule

def update_schedule(db: Session, schedule_id: int, schedule_update: CrawlScheduleUpdate):
    db_schedule = get_schedule_by_id(db, schedule_id)
    if not db_schedule:
        return None
    
    update_data = schedule_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_schedule, key, value)
    
    db.commit()
    db.refresh(db_schedule)
    return db_schedule

def delete_schedule(db: Session, schedule_id: int):
    db_schedule = get_schedule_by_id(db, schedule_id)
    if db_schedule:
        db.delete(db_schedule)
        db.commit()
        return True
    return False

# === RULE CRUD ===
def get_rules(db: Session, skip: int = 0, limit: int = 100, is_active: Optional[bool] = None):
    """
    Lấy danh sách Rule, hỗ trợ lọc theo trạng thái is_active
    """
    query = db.query(CrawlRule)
    
    # --- [BỔ SUNG MỚI] ---
    if is_active is not None:
        query = query.filter(CrawlRule.is_active == is_active)
        
    return query.order_by(CrawlRule.priority.desc()).offset(skip).limit(limit).all()

def get_rule_by_id(db: Session, rule_id: int):
    return db.query(CrawlRule).filter(CrawlRule.id == rule_id).first()

def create_rule(db: Session, rule: CrawlRuleCreate):
    db_rule = CrawlRule(**rule.model_dump())
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)
    return db_rule

def update_rule(db: Session, rule_id: int, rule_update: CrawlRuleUpdate):
    db_rule = get_rule_by_id(db, rule_id)
    if not db_rule:
        return None
    
    update_data = rule_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_rule, key, value)
        
    db.commit()
    db.refresh(db_rule)
    return db_rule

def delete_rule(db: Session, rule_id: int):
    db_rule = get_rule_by_id(db, rule_id)
    if db_rule:
        db.query(CrawlLog).filter(CrawlLog.rule_id == rule_id).delete()
        db.delete(db_rule)
        db.commit()
        return True
    return False

# ==========================================
# CRAWL LOG CRUD
# ==========================================

# 1. Lấy danh sách Log (Có phân trang & Lọc)
def get_logs(
    db: Session, 
    skip: int = 0, 
    limit: int = 100, 
    status: Optional[str] = None, 
    rule_id: Optional[int] = None
):
    query = db.query(CrawlLog)
    
    # --- Filter (Lọc dữ liệu) ---
    if status:
        query = query.filter(CrawlLog.status == status)
    if rule_id:
        query = query.filter(CrawlLog.rule_id == rule_id)
        
    # --- Sort & Pagination ---
    # Luôn sắp xếp start_time giảm dần (mới nhất lên đầu) để tránh lỗi SQL Server
    logs = query.order_by(desc(CrawlLog.start_time))\
                .offset(skip)\
                .limit(limit)\
                .all()
    
    # [Mẹo] Gán thủ công tên rule để Schema nhận diện được trường 'rule_name'
    for log in logs:
        if log.rule:
            log.rule_name = log.rule.rule_name
            
    return logs

# 2. Tìm kiếm chi tiết Log theo ID
def get_log(db: Session, log_id: int):
    log = db.query(CrawlLog).filter(CrawlLog.id == log_id).first()
    
    # Gán tên rule nếu tìm thấy log
    if log and log.rule:
        log.rule_name = log.rule.rule_name
        
    return log