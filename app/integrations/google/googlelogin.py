from fastapi import APIRouter, FastAPI, Depends, HTTPException
from starlette.requests import Request
from starlette.config import Config # Bắt buộc có cái này
from authlib.integrations.starlette_client import OAuth
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import timedelta
import os


from app.infrastructure.database.database import get_db
from app.modules.users.model import User
from app.core.utils.enum import UserRole 
from app.core.security import create_access_token

router = APIRouter(
    prefix="/googlelogin",
    tags=["Google Login"]
)
# 2. Cấu hình OAuth Google
oauth = OAuth()

# Truyền trực tiếp client_id và client_secret vào đây để tránh lỗi None
oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

# 3. API Login (Redirect sang Google)
@router.get("/login/google")
async def login_google(request: Request):
    # Sử dụng create_client thay vì oauth.google để an toàn hơn
    google = oauth.create_client('google')
    
    # Kiểm tra lại lần nữa cho chắc chắn
    if not google:
        raise HTTPException(status_code=500, detail="Google Client configuration error")
        
    redirect_uri = request.url_for('auth_google_callback')
    return await google.authorize_redirect(request, redirect_uri)

# 4. API Callback (Xử lý lưu DB và trả về JWT)
@router.get("/auth/google/callback")
async def auth_google_callback(request: Request, db: Session = Depends(get_db)):
    try:
        google = oauth.create_client('google')
        
        # --- TYPE GUARD: Kiểm tra lại lần nữa ---
        if google is None:
            raise HTTPException(status_code=500, detail="Lỗi cấu hình: Google Client bị thiếu.")
        # ----------------------------------------
        
        # Lấy token (Lúc này trình soạn thảo sẽ không báo lỗi nữa)
        token = await google.authorize_access_token(request)
        
        # Lấy thông tin user
        user_info = token.get('userinfo')
        if not user_info:
             # Nếu thư viện chưa tự parse, gọi thủ công endpoint Google
             user_info = await google.userinfo(token=token)

        # Lấy email từ kết quả
        # Lưu ý: user_info có thể là dict hoặc object tùy version, dùng .get cho an toàn
        email = user_info.get('email') if isinstance(user_info, dict) else user_info['email']
        name = user_info.get('name') if isinstance(user_info, dict) else user_info['name']

        if not email:
            raise HTTPException(status_code=400, detail="Google không trả về Email.")

        # --- LOGIC DATABASE (Tìm hoặc Tạo user) ---
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            # Tạo user mới nếu chưa có
            user = User(
                email=email,
                full_name=name,
                role=UserRole.ENGINEER,
                status=True,
                auth_provider="google",
                hashed_password=None # Google user không có pass
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        
        # --- TẠO JWT TOKEN (Phần bạn cần) ---
        jwt_payload = {
            "sub": str(user.user_id),
            "email": user.email,
            "role": user.role.value
        }
        
        # Gọi hàm tạo token (đảm bảo bạn đã định nghĩa hàm này ở trên)
        access_token = create_access_token(jwt_payload)
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user_info": {
                "id": user.user_id,
                "name": user.full_name,
                "role": user.role
            }
        }

    except Exception as e:
        # In lỗi ra terminal để dễ debug
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"Lỗi xác thực: {str(e)}")