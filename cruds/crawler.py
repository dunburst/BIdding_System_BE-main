from sqlalchemy.orm import Session
from models import CrawlRule
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
    return db.query(CrawlRule).offset(skip).limit(limit).all()