from sqlalchemy.orm import Session
from models import User 

def get_user_by_email(db: Session, email: str):
    """Tìm user trong DB dựa theo email"""
    return db.query(User).filter(User.email == email).first()