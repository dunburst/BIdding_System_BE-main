# cruds/crawler.py
from sqlalchemy.orm import Session
from models import CrawlSchedule, CrawlRule
from schemas.crawler import CrawlScheduleCreate, CrawlScheduleUpdate, CrawlRuleCreate, CrawlRuleUpdate

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
def get_rules(db: Session, skip: int = 0, limit: int = 100):
    # Hàm này đã có order_by nên không bị lỗi
    return db.query(CrawlRule).order_by(CrawlRule.priority.desc()).offset(skip).limit(limit).all()

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
        db.delete(db_rule)
        db.commit()
        return True
    return False