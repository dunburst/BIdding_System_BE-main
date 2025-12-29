from sqlalchemy.orm import Session
from models import DocumentTemplate, BiddingTask
from schemas.drafting import TemplateCreate
from typing import Optional
# 1. Lấy danh sách template (có lọc theo category)
def get_templates(db: Session, category: Optional[str] = None):
    query = db.query(DocumentTemplate).filter(DocumentTemplate.is_active == True)
    if category:
        query = query.filter(DocumentTemplate.category == category.upper())
    return query.all()

# 2. Lấy chi tiết 1 template
def get_template(db: Session, template_id: int):
    return db.query(DocumentTemplate).filter(DocumentTemplate.id == template_id).first()

# 3. Tạo template (Dùng cho admin hoặc seed data)
def create_template(db: Session, template: TemplateCreate):
    db_template = DocumentTemplate(**template.model_dump())
    db.add(db_template)
    db.commit()
    db.refresh(db_template)
    return db_template

# 4. Lưu bản nháp vào Task
def save_task_draft(db: Session, task_id: int, content: str):
    # Sửa truy vấn dùng BiddingTask
    task = db.query(BiddingTask).filter(BiddingTask.id == task_id).first()
    if task:
        task.draft_content = content
        db.commit()
        db.refresh(task)
    return task