from sqlalchemy.orm import Session
from models import CrawlRule, CrawlSchedule
from schemas import crawl as schemas

def create_rule(db: Session, rule: schemas.CrawlRuleCreate):
    db_rule = CrawlRule(
        rule_name=rule.rule_name,
        business_field=rule.business_field,
        keywords_include=rule.keywords_include, # SQLA tự convert sang JSON
        keywords_exclude=rule.keywords_exclude,
        min_budget=rule.min_budget,
        max_budget=rule.max_budget,
        locations=rule.locations,
        priority=rule.priority
    )
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)
    return db_rule

def get_rules(db: Session, skip: int = 0, limit: int = 100):
    return db.query(CrawlRule).order_by(CrawlRule.id.desc()).offset(skip).limit(limit).all()

# ==========================================
# SCHEDULE CRUD
# ==========================================
def get_schedules(db: Session, skip: int = 0, limit: int = 100):
    # Luôn phải có order_by trước offset/limit với SQL Server
    return db.query(CrawlSchedule).order_by(CrawlSchedule.id.desc()).offset(skip).limit(limit).all()

def create_schedule(db: Session, schedule: schemas.CrawlScheduleCreate):
    db_sched = CrawlSchedule(**schedule.model_dump())
    db.add(db_sched)
    db.commit()
    db.refresh(db_sched)
    return db_sched

def update_schedule(db: Session, schedule_id: int, schedule_update: schemas.CrawlScheduleUpdate):
    db_sched = db.query(CrawlSchedule).filter(CrawlSchedule.id == schedule_id).first()
    if not db_sched:
        return None
    
    update_data = schedule_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_sched, key, value)
        
    db.add(db_sched)
    db.commit()
    db.refresh(db_sched)
    return db_sched

def delete_schedule(db: Session, schedule_id: int):
    db_sched = db.query(CrawlSchedule).filter(CrawlSchedule.id == schedule_id).first()
    if db_sched:
        db.delete(db_sched)
        db.commit()
        return True
    return False