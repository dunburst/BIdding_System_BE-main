import os
from datetime import datetime, timedelta
from typing import Union, Any
from jose import jwt
from passlib.context import CryptContext
from dotenv import load_dotenv
from app.infrastructure.database.database import get_db
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from app.modules.users.model import User
from functools import lru_cache
from typing import Optional

load_dotenv() # Load biến từ file .env
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))
ALGORITHM = os.getenv("ALGORITHM", "HS256")
SECRET_KEY = os.getenv("SECRET_KEY", "secret_key_mac_dinh")

# Quan trọng: Nếu chạy HTTPS thì set True, Localhost thì False
SECURE_COOKIE = os.getenv("SECURE_COOKIE", "False").lower() == "true"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False) # auto_error=False để tự xử lý

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

# --- LOGIC MỚI: LẤY TOKEN TỪ COOKIE HOẶC HEADER ---
async def get_current_user(
    request: Request, 
    token_header: str = Depends(oauth2_scheme), 
    db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token không hợp lệ hoặc đã hết hạn",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1. Ưu tiên lấy từ Cookie (HttpOnly)
    token = request.cookies.get("access_token")
    
    # 2. Nếu không có Cookie, lấy từ Header (Bearer ...)
    if not token:
        token = token_header

    if not token:
        raise credentials_exception
    
    # --- [QUAN TRỌNG] Xử lý tiền tố Bearer ---
    # Cookie có thể chứa "Bearer eyJ...", cần lọc bỏ
    if token.startswith("Bearer "):
        token = token.split(" ")[1]

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    from app.modules.users.crud import get_user_by_email
    user = get_user_by_email(db, email=email)
    if user is None:
        raise credentials_exception
    
    if not user.status:
        raise HTTPException(status_code=403, detail="Tài khoản đã bị khóa")
        
    return user

# --- BỔ SUNG 1: HÀM TẠO REFRESH TOKEN ---
def create_refresh_token(data: dict, expires_delta: Union[timedelta, None] = None) -> str:
    """Tạo Refresh Token (thời hạn dài hơn Access Token)"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        # Mặc định 7 ngày hoặc 30 ngày tùy config
        expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({"exp": expire, "type": "refresh"}) # Thêm type để phân biệt
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# --- BỔ SUNG 2: HÀM DECODE TOKEN (Dùng cho Refresh Flow) ---
def decode_token(token: str) -> dict:
    """
    Giải mã token mà không check DB. Dùng để verify refresh token.
    Ném lỗi nếu token hết hạn hoặc không hợp lệ.
    """
    try:
        # Xử lý nếu token có prefix "Bearer "
        if token.startswith("Bearer "):
            token = token.split(" ")[1]
            
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None #type: ignore