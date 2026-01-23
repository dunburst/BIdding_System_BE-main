import logging
import os
import httpx
import base64
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import timedelta # <--- Import để tính thời gian

from cruds import user
from database import get_db
from models import SecurityLevel, User, UserRole
from cruds.user import get_user_by_email
from utils.security import verify_password, create_access_token, get_password_hash, SECURE_COOKIE

from schemas.auth import LoginRequest, LoginResponse, RegisterRequest, UserMeResponse, UserInfo
from schemas.base import BaseResponse
from jose import JWTError, jwt
from schemas.auth import RefreshTokenRequest
from utils.security import SECRET_KEY, ALGORITHM, get_current_user

# Thiết lập log để debug
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CẤU HÌNH THỜI GIAN ---
# Bạn có thể để số này trong file config, ở đây tôi để tạm 60 phút
ACCESS_TOKEN_EXPIRE_MINUTES = 60 
REFRESH_TOKEN_EXPIRE_DAYS = 7
REMEMBER_ME_DAYS = 30 # Nếu chọn ghi nhớ thì lưu 30 ngày

# Cấu hình từ môi trường
CLIENT_ID = os.getenv("MS_CLIENT_ID")
CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
TENANT_ID = os.getenv("MS_TENANT_ID", "common")
REDIRECT_URI = os.getenv("MS_REDIRECT_URI")

# URL của Microsoft
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
AUTH_URL = f"{AUTHORITY}/oauth2/v2.0/authorize"
TOKEN_URL = f"{AUTHORITY}/oauth2/v2.0/token"
USER_INFO_URL = "https://graph.microsoft.com/v1.0/me"
# Link API Microsoft Graph
USER_INFO_URL = "https://graph.microsoft.com/v1.0/me"
USER_PHOTO_URL = "https://graph.microsoft.com/v1.0/me/photo/$value"


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
# 2. ĐĂNG NHẬP (LOGIN) - UPDATE LOGIC COOKIE
# ==========================================
@router.post("/login", response_model=BaseResponse[LoginResponse])
def login(
    login_data: LoginRequest, 
    response: Response,  # Inject Response object để set cookie
    db: Session = Depends(get_db)
):
    user = get_user_by_email(db, email=login_data.email)

    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email hoặc mật khẩu không chính xác",
        )
    
    if not user.status:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tài khoản đã bị khóa")

    role_name = user.role.value if user.role else ""

    # --- XỬ LÝ THỜI GIAN SỐNG CỦA TOKEN/COOKIE ---
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Mặc định refresh token sống 7 ngày
    refresh_expires_duration = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    # Nếu chọn "Ghi nhớ đăng nhập" -> Tăng thời gian sống lên 30 ngày cho Cookie
    if login_data.remember_me:
        cookie_max_age = 3600 # 1 hour in seconds
        refresh_expires_duration = timedelta(hours=1)
    else:
        cookie_max_age = None # Session Cookie (Xóa khi tắt trình duyệt)
        refresh_expires_duration = timedelta(days=7)

    # Tạo JWT
    access_token = create_access_token(
        data={"sub": user.email, "user_id": user.user_id, "role": role_name},
        expires_delta=access_token_expires
    )
    refresh_token = create_access_token(
        data={"sub": user.email, "type": "refresh"},
        expires_delta=refresh_expires_duration
    )

    # --- SET COOKIE HTTPONLY ---
    # 1. Access Token Cookie
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,      # JS không đọc được (Chống XSS)
        max_age=cookie_max_age, # Thời gian sống (None = Session)
        expires=cookie_max_age,
        samesite="lax",     # Chống CSRF cơ bản
        secure=SECURE_COOKIE # True nếu chạy HTTPS production
    )

    # 2. Refresh Token Cookie (Quan trọng để giữ phiên đăng nhập lâu dài)
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=cookie_max_age,
        expires=cookie_max_age,
        samesite="lax",
        secure=SECURE_COOKIE
    )

    user_info = UserInfo(
        user_id=user.user_id,
        email=user.email,
        full_name=user.full_name,
        role=role_name
    )

    # Vẫn trả về JSON để Frontend có thể lấy info hiển thị ngay lập tức
    response_data = LoginResponse(
        access_token=access_token,
        token_type="bearer",
        refresh_token=refresh_token,
        expiresIn=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_info
    )

    return BaseResponse(
        success=True, status=200, message="Đăng nhập thành công", data=response_data
    )

# ==========================================
# 3. LÀM MỚI TOKEN (REFRESH) - UPDATE ĐỌC COOKIE
# ==========================================
@router.post("/refresh", response_model=BaseResponse[LoginResponse])
def refresh_access_token(
    request: Request,
    response: Response,
    body_request: RefreshTokenRequest, # Có thể gửi body rỗng nếu dùng cookie
    db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Refresh token không hợp lệ hoặc đã hết hạn",
    )
    
    # 1. Ưu tiên lấy Refresh Token từ Cookie
    refresh_token_str = request.cookies.get("refresh_token")
    
    # 2. Nếu không có cookie, lấy từ body JSON
    if not refresh_token_str:
        refresh_token_str = body_request.refresh_token
        
    if not refresh_token_str:
        raise credentials_exception

    try:
        payload = jwt.decode(refresh_token_str, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        token_type = payload.get("type")
        
        if email is None or token_type != "refresh":
            raise credentials_exception
            
    except JWTError:
        raise credentials_exception

    user = get_user_by_email(db, email=email)
    if not user or not user.status:
        raise credentials_exception

    # Tạo Access Token mới
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    role_name = user.role.value if user.role else ""
    new_access_token = create_access_token(
        data={"sub": user.email, "user_id": user.user_id, "role": role_name},
        expires_delta=access_token_expires
    )

    # Cập nhật lại Cookie Access Token
    response.set_cookie(
        key="access_token",
        value=new_access_token,
        httponly=True,
        samesite="lax",
        secure=SECURE_COOKIE
        # Không set max_age ở đây để nó theo session hoặc giữ nguyên expire cũ của refresh
    )

    user_info = UserInfo(
        user_id=user.user_id,
        email=user.email,
        full_name=user.full_name,
        role=role_name
    )

    response_data = LoginResponse(
        access_token=new_access_token,
        token_type="bearer",
        refresh_token=refresh_token_str,
        expiresIn=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_info
    )

    return BaseResponse(
        success=True, status=200, message="Làm mới token thành công", data=response_data
    )

# ==========================================
# 4. ĐĂNG XUẤT (LOGOUT) - MỚI
# ==========================================
@router.post("/logout")
def logout(response: Response):
    # Xóa Cookie bằng cách set expire về quá khứ
    response.delete_cookie(key="access_token")
    response.delete_cookie(key="refresh_token")
    
    return BaseResponse(
        success=True,
        status=200,
        message="Đăng xuất thành công",
        data=None
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
        avatar_url=current_user.avatar_url,
        status=current_user.status
    )

    return BaseResponse(
        success=True,
        status=200,
        message="Lấy thông tin thành công",
        data=user_data
    )
    
def map_ms_job_to_role(job_title: str) -> UserRole:
    if not job_title:
        return UserRole.ENGINEER
    
    jt = job_title.lower()
    # Nếu trong jobTitle có chữ "quản trị" hoặc "admin" -> ADMIN
    if "admin" in jt or "quản trị" in jt: 
        return UserRole.ADMIN
    # Nếu có chữ "giám đốc" hoặc "manager" -> MANAGER
    if "giám đốc" in jt or "manager" in jt: 
        return UserRole.MANAGER
    if "thầu" in jt : 
        return UserRole.BID_MANAGER
    # Nếu có chữ "trưởng phòng"
    if "trưởng" in jt or "lead" in jt: 
        return UserRole.SPECIALIST
    # Mặc định còn lại (bao gồm "nhân viên") -> ENGINEER
    return UserRole.ENGINEER
    
async def get_ms_user_photo(access_token: str) -> str:
    """Lấy ảnh đại diện và chuyển sang Base64"""
    # Endpoint lấy nội dung ảnh (binary)
    PHOTO_URL = "https://graph.microsoft.com/v1.0/me/photo/$value"
    
    async with httpx.AsyncClient() as client:
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            photo_res = await client.get(PHOTO_URL, headers=headers)
            
            if photo_res.status_code == 200:
                # Nếu thành công, chuyển binary sang base64
                encoded_string = base64.b64encode(photo_res.content).decode("utf-8")
                logger.info("Lấy ảnh Microsoft thành công!")
                return f"data:image/jpeg;base64,{encoded_string}"
            else:
                # Thường trả về 404 nếu người dùng chưa bao giờ upload ảnh lên Office 365
                logger.warning(f"Không tìm thấy ảnh (Status: {photo_res.status_code})")
                return None # type: ignore
        except Exception as e:
            logger.error(f"Lỗi khi gọi API lấy ảnh: {str(e)}")
            return None # type: ignore
# 1. API tạo đường dẫn để Frontend nhấn vào "Login with Microsoft"
@router.get("/microsoft/login")
def get_microsoft_auth_url():
    # Sửa lỗi: scope phải cách nhau bằng dấu cách
    # Thêm openid và profile để lấy đầy đủ thông tin định danh
    scopes = ["User.Read", "profile", "openid"]
    scope_param = " ".join(scopes)
    
    params = (
        f"client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_mode=query"
        f"&scope={scope_param}"
    )
    return {"url": f"{AUTH_URL}?{params}"}

@router.get("/microsoft/callback")
async def microsoft_callback(code: str, db: Session = Depends(get_db)):
    # 1. Đổi code lấy Access Token
    async with httpx.AsyncClient() as client:
        token_data = {
            "client_id": CLIENT_ID,
            "scope": "User.Read profile openid",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
            "client_secret": CLIENT_SECRET,
        }
        token_res = await client.post(TOKEN_URL, data=token_data)
        ms_tokens = token_res.json()
        
        if "error" in ms_tokens:
            raise HTTPException(status_code=400, detail=ms_tokens.get("error_description"))

        ms_access_token = ms_tokens["access_token"]

        # 2. Lấy thông tin User & Ảnh
        headers = {'Authorization': f'Bearer {ms_access_token}'}
        user_res = await client.get(USER_INFO_URL, headers=headers)
        ms_user = user_res.json()
        avatar_base64 = await get_ms_user_photo(ms_access_token)

    # 3. Trích xuất và Map thông tin
    email = ms_user.get("mail") or ms_user.get("userPrincipalName")
    full_name = ms_user.get("displayName")
    ms_job_title = ms_user.get("jobTitle") or "Nhân viên"
    
    # Thực hiện MAP sang hệ thống Role của mình
    assigned_role = map_ms_job_to_role(ms_job_title)

    # 4. Xử lý Database
    user_obj = db.query(User).filter(User.email == email).first()

    if not user_obj:
        # Tạo mới: Job Title giữ nguyên tiếng Việt, Role lưu Enum
        user_obj = User(
            email=email,
            full_name=full_name,
            job_title=ms_job_title,    # Lưu: "Nhân viên" hoặc "Quản trị viên"
            role=assigned_role,        # Lưu: UserRole.ENGINEER hoặc UserRole.ADMIN
            avatar_url=avatar_base64,
            auth_provider="microsoft",
            security_clearance=SecurityLevel.PUBLIC,
            status=True
        )
        db.add(user_obj)
    else:
        # Cập nhật thông tin mới nhất khi login lại
        user_obj.full_name = full_name
        user_obj.job_title = ms_job_title
        user_obj.role = assigned_role 
        if avatar_base64:
            user_obj.avatar_url = avatar_base64
    
    db.commit()
    db.refresh(user_obj)

    # --- [BƯỚC 5: TẠO TOKEN NỘI BỘ] ---
    internal_token = create_access_token(
        data={
            "sub": user_obj.email, 
            "user_id": user_obj.user_id, 
            "role": user_obj.role.value
        }
    )

    # --- [BƯỚC 6: TẠO REDIRECT VÀ SET COOKIE] ---
    
    # 1. Đích đến mong muốn của Frontend (trang chủ hoặc dashboard)
    frontend_dashboard_url = "http://10.10.0.158:3000/dashboard"
    
    # 2. Khởi tạo đối tượng RedirectResponse (Mã 302)
    response = RedirectResponse(url=frontend_dashboard_url)

    # 3. Gói token vào Cookie
    response.set_cookie(
        key="access_token",        # Tên cookie phải khớp với bên xử lý Auth
        value=internal_token,      # Giá trị token JWT
        httponly=True,             # JavaScript không thể đọc được (Chống XSS)
        secure=False,              # Để False nếu đang chạy HTTP (localhost), True nếu chạy HTTPS
        samesite="lax",            # Giúp cookie gửi được khi chuyển hướng từ Microsoft về
        max_age=3600 * 24,          # Thời hạn 1 ngày (tùy chỉnh)
        path="/"     # Đảm bảo cookie có hiệu lực trên toàn bộ trang web
    )
    
    return response