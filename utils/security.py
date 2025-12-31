import os
from datetime import datetime, timedelta
from typing import Union, Any
from jose import jwt
from passlib.context import CryptContext
from dotenv import load_dotenv
from database import get_db
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from models import User
from functools import lru_cache
from typing import Optional

load_dotenv() # Load biến từ file .env
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))
ALGORITHM = os.getenv("ALGORITHM", "HS256")
SECRET_KEY = os.getenv("SECRET_KEY", "secret_key_mac_dinh")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """So sánh mật khẩu nhập vào và mật khẩu đã mã hóa"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Mã hóa mật khẩu để lưu vào DB"""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Union[timedelta, None] = None) -> str:
    """Tạo JWT Token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# --- CACHING USER ĐỂ GIẢM TẢI DB ---
# Lưu kết quả query trong 60 giây (hoặc tùy chỉnh)
# Lưu ý: LRU Cache lưu trên RAM, nếu restart server sẽ mất (không sao cả)
@lru_cache(maxsize=100)
def get_cached_user_email(token: str):
    """
    Cache việc giải mã token để tránh decode liên tục nếu token không đổi
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: Optional[str] = payload.get("sub")
        if email is None:
            return None
        return email
    except JWTError:
        return None

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token không hợp lệ hoặc đã hết hạn",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Giải mã token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # --- 3. SỬA LỖI TYPE (SỬA LỖI 2) ---
        # Không dùng: email: str = payload.get("sub") -> Vì nó có thể là None
        email = payload.get("sub") 
        
        if email is None:
            raise credentials_exception
            
    except JWTError:
        raise credentials_exception
    from cruds.user import get_user_by_email
    # Tìm user trong DB
    user = get_user_by_email(db, email=email)
    if user is None:
        raise credentials_exception
    
    if not user.status:
        raise HTTPException(status_code=403, detail="Tài khoản đã bị khóa")
        
    return user