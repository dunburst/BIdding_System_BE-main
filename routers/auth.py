from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta # <--- Import để tính thời gian

from cruds import user
from database import get_db
from models import User, UserRole
from cruds.user import get_user_by_email
from utils.security import verify_password, create_access_token, get_password_hash

from schemas.auth import LoginRequest, LoginResponse, RegisterRequest, UserMeResponse, UserInfo
from schemas.base import BaseResponse
from jose import JWTError, jwt
from schemas.auth import RefreshTokenRequest
from utils.security import SECRET_KEY, ALGORITHM, get_current_user

# --- CẤU HÌNH THỜI GIAN ---
# Bạn có thể để số này trong file config, ở đây tôi để tạm 60 phút
ACCESS_TOKEN_EXPIRE_MINUTES = 60 
REFRESH_TOKEN_EXPIRE_DAYS = 7

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

# ==========================================
# 1. ĐĂNG KÝ (REGISTER)
# ==========================================
@router.post("/register", response_model=BaseResponse[LoginResponse]) 
def register(register_data: RegisterRequest, db: Session = Depends(get_db)):
    # 1. Check tồn tại
    existing_user = get_user_by_email(db, email=register_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email này đã được sử dụng",
        )

    # 2. Tạo user
    hashed_password = get_password_hash(register_data.password)
    new_user = User(
        email=register_data.email,
        hashed_password=hashed_password,
        full_name=register_data.full_name,
        role=register_data.role, 
        status=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 3. Tạo Token & Tính thời gian
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    # Access Token
    access_token = create_access_token(
        data={"sub": new_user.email, "user_id": new_user.user_id, "role": new_user.role.value},
        expires_delta=access_token_expires
    )
    
    # Refresh Token (Tạo tương tự nhưng hạn dài hơn)
    refresh_token = create_access_token(
        data={"sub": new_user.email, "type": "refresh"},
        expires_delta=refresh_token_expires
    )

    # 4. Tạo response data
    user_info = UserInfo(
        user_id=new_user.user_id,
        email=new_user.email,
        full_name=new_user.full_name,
        role=new_user.role.value
    )

    # 2. Đưa user_info vào LoginResponse
    response_data = LoginResponse(
        access_token=access_token,
        token_type="bearer",
        refresh_token=refresh_token,      # Chú ý tên biến khớp với schema
        expiresIn=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_info                   # Gán object user vào đây
    )

    return BaseResponse(
        success=True,
        status=200,
        message="Đăng ký tài khoản thành công",
        data=response_data
    )

# ==========================================
# 2. ĐĂNG NHẬP (LOGIN)
# ==========================================
@router.post("/login", response_model=BaseResponse[LoginResponse])
def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    user = get_user_by_email(db, email=login_data.email)

    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email hoặc mật khẩu không chính xác",
        )
    
    if not user.status:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản đã bị khóa",
        )

    role_name = user.role.value if user.role else ""

    # --- TẠO TOKEN MỚI ---
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    access_token = create_access_token(
        data={"sub": user.email, "user_id": user.user_id, "role": role_name},
        expires_delta=access_token_expires
    )
    
    refresh_token = create_access_token(
        data={"sub": user.email, "type": "refresh"},
        expires_delta=refresh_token_expires
    )

    # Tạo data trả về
    user_info = UserInfo(
        user_id=user.user_id,
        email=user.email,
        full_name=user.full_name,
        role=role_name
    )

    # 2. Đưa user_info vào LoginResponse
    response_data = LoginResponse(
        access_token=access_token,
        token_type="bearer",
        refresh_token=refresh_token,      # Chú ý tên biến khớp với schema
        expiresIn=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_info                   # Gán object user vào đây
    )

    return BaseResponse(
        success=True,
        status=200,
        message="Đăng nhập thành công",
        data=response_data
    )
    
@router.post("/refresh", response_model=BaseResponse[LoginResponse])
def refresh_access_token(
    request: RefreshTokenRequest, 
    db: Session = Depends(get_db)
):
    """
    Dùng Refresh Token để lấy lại Access Token mới mà không cần đăng nhập lại.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Refresh token không hợp lệ hoặc đã hết hạn",
    )
    
    # 1. Giải mã token
    try:
        payload = jwt.decode(request.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        token_type = payload.get("type") # Lấy loại token để check
        
        if email is None or token_type != "refresh":
            raise credentials_exception
            
    except JWTError:
        raise credentials_exception

    # 2. Kiểm tra user trong DB
    user = get_user_by_email(db, email=email)
    if not user or not user.status:
        raise credentials_exception

    # 3. Tạo Access Token mới (Hạn 60 phút)
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    role_name = user.role.value if user.role else ""
    
    new_access_token = create_access_token(
        data={"sub": user.email, "user_id": user.user_id, "role": role_name},
        expires_delta=access_token_expires
    )

    # 4. (Tùy chọn) Có thể tạo luôn Refresh Token mới để xoay vòng (Token Rotation)
    # Ở đây tôi giữ nguyên Refresh Token cũ để đơn giản, chỉ trả về Access Token mới
    
    user_info = UserInfo(
        user_id=user.user_id,
        email=user.email,
        full_name=user.full_name,
        role=role_name
    )

    # 2. Đưa user_info vào LoginResponse
    response_data = LoginResponse(
        access_token=new_access_token,
        token_type="bearer",
        refresh_token=request.refresh_token,      # Chú ý tên biến khớp với schema
        expiresIn=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_info                   # Gán object user vào đây
    )

    return BaseResponse(
        success=True,
        status=200,
        message="Làm mới token thành công",
        data=response_data
    )
    
@router.get("/me", response_model=BaseResponse[UserMeResponse])
def get_me(current_user: User = Depends(get_current_user)):
    """
    API lấy thông tin user hiện tại dựa trên Token.
    User phải gửi Header: Authorization: Bearer <token>
    """
    
    # Map dữ liệu từ DB sang Schema
    # Vì trong DB User chưa có avatar, ta để tạm None hoặc link default
    user_data = UserMeResponse(
        id=current_user.user_id,
        email=current_user.email,
        full_name=current_user.full_name, # Pydantic sẽ tự đổi thành fullName nhờ alias
        role=current_user.role.value if current_user.role else "",
        avatar_url=current_user.avatar_url
    )

    return BaseResponse(
        success=True,
        status=200,
        message="Lấy thông tin thành công",
        data=user_data
    )