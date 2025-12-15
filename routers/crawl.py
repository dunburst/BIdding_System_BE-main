from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from schemas import crawl as schemas
from cruds import crawler as crud_crawl

router = APIRouter(
    prefix="/crawl-rules",
    tags=["Crawl Rules"]
)

@router.post("/", response_model=schemas.CrawlRuleResponse)
def create_rule(rule: schemas.CrawlRuleCreate, db: Session = Depends(get_db)):
    return crud_crawl.create_rule(db=db, rule=rule)

@router.get("/", response_model=List[schemas.CrawlRuleResponse])
def read_rules(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud_crawl.get_rules(db, skip=skip, limit=limit)