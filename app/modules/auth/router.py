import logging
import os
import httpx
import base64
import secrets
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import timedelta # <--- Import để tính thời gian

from app.modules.users import crud
from app.infrastructure.database.database import get_db
from app.modules.users.model import User
from app.core.utils.enum import UserRole, SecurityLevel
from app.modules.users.crud import get_user_by_email
from app.core.security import create_refresh_token, verify_password, create_access_token, get_password_hash, SECURE_COOKIE

from app.modules.auth.schema import LoginRequest, LoginResponse, RegisterRequest, UserMeResponse, UserInfo
from app.core.utils.base_model import BaseResponse
from jose import JWTError, jwt
from app.modules.auth.schema import RefreshTokenRequest
from app.core.security import SECRET_KEY, ALGORITHM, get_current_user, decode_token

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
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://ai-dauthau-lab.pc1group.vn")
IS_PROD = os.getenv("ENV") == "production"
if IS_PROD:
    # URL cho môi trường Production (Server)
    REDIRECT_URI = "https://ai-dauthau-lab.pc1group.vn/auth/microsoft/callback"
else:
    # URL cho môi trường Dev (Localhost)
    # Lưu ý: Port 43210 hay 8000 tùy vào port backend của bạn
    REDIRECT_URI = os.getenv("MS_REDIRECT_URI", "https://accomplish-ssl-ecology-grove.trycloudflare.com/auth/microsoft/callback")
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

# 1. API tạo đường dẫn để Frontend nhấn vào "Login with Microsoft"    
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
# 1. API chuyển hướng người dùng sang Microsoft Login
@router.get("/microsoft/login")
def login_microsoft(request: Request, remember: bool = True):
    # 1. Tạo State ngẫu nhiên
    state = secrets.token_urlsafe(32)
    
    scopes = ["User.Read", "profile", "openid", "email"]

    # ✅ FIX 1: URL TUYỆT ĐỐI (ABSOLUTE URL)
    # Phải có https://login.microsoftonline.com ở đầu
    authority_host = "https://login.microsoftonline.com"
    endpoint = f"/{TENANT_ID}/oauth2/v2.0/authorize"
    full_auth_url = f"{authority_host}{endpoint}"

    # 🔍 DEBUG: Log tất cả biến quan trọng
    logger.info("=" * 80)
    logger.info("DEBUG - Microsoft OAuth URL Generation")
    logger.info(f"CLIENT_ID: {CLIENT_ID}")
    logger.info(f"TENANT_ID: {TENANT_ID}")
    logger.info(f"REDIRECT_URI: {REDIRECT_URI}")
    logger.info(f"IS_PROD: {IS_PROD}")
    logger.info(f"authority_host: {authority_host}")
    logger.info(f"endpoint: {endpoint}")
    logger.info(f"full_auth_url: {full_auth_url}")
    logger.info("=" * 80)

    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI, # <--- Biến này đã được xử lý logic ở trên
        "response_mode": "query",
        "scope": " ".join(scopes),
        "state": state,
    }

    # ✅ FIX 3: Dùng urlencode để encode params đúng cách
    url_params = urlencode(params)
    final_url = f"{full_auth_url}?{url_params}"

    # 🔍 DEBUG: Log URL và response
    logger.info("=" * 80)
    logger.info("DEBUG - Final URL and Response")
    logger.info(f"url_params: {url_params}")
    logger.info(f"final_url: {final_url}")
    logger.info("=" * 80)

    response = RedirectResponse(url=final_url)

    # 🔍 DEBUG: Log response details
    logger.info("=" * 80)
    logger.info("DEBUG - Response Details")
    logger.info(f"Response status_code: {response.status_code}")
    logger.info(f"Response headers: {dict(response.headers)}")
    logger.info(f"Redirect location: {response.headers.get('location')}")
    logger.info("=" * 80)
    
    # Lưu state vào cookie (5 phút)
    response.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        secure=IS_PROD,
        samesite="none",
        max_age=300
    )
    
    # Lưu trạng thái remember
    response.set_cookie(
        key="oauth_remember",
        value=str(remember).lower(),
        httponly=True,
        secure=IS_PROD,
        samesite="none",
        max_age=300
    )

    return response

# 2. API Callback xử lý sau khi đăng nhập thành công
@router.get("/microsoft/callback")
async def microsoft_callback(
    request: Request, 
    code: str, 
    state: str, 
    db: Session = Depends(get_db)
):
    # --- BƯỚC 1: VERIFY STATE ---
    cookie_state = request.cookies.get("oauth_state")
    remember_cookie = request.cookies.get("oauth_remember")
    
    # Xóa cookie tạm ngay lập tức để sạch sẽ
    response_fail = RedirectResponse(f"{FRONTEND_URL}/auth/callback?error=InvalidState")
    response_fail.delete_cookie("oauth_state")
    response_fail.delete_cookie("oauth_remember")

    # if not cookie_state or cookie_state != state:
    #     logger.error("Invalid OAuth State")
    #     return response_fail

    remember = remember_cookie == 'true'
    refresh_max_age = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60 if remember else 24 * 60 * 60

    # --- BƯỚC 2: TRAO ĐỔI CODE LẤY TOKEN ---
    async with httpx.AsyncClient() as client:
        token_data = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        }
        
        token_res = await client.post(TOKEN_URL, data=token_data)
        ms_tokens = token_res.json()
        
        if "error" in ms_tokens:
             logger.error(f"Microsoft Token Error: {ms_tokens}")
             return RedirectResponse(f"{FRONTEND_URL}/auth/callback?error=MicrosoftTokenError")

        ms_access_token = ms_tokens["access_token"]

        # --- BƯỚC 3: LẤY INFO USER ---
        headers = {'Authorization': f'Bearer {ms_access_token}'}
        user_res = await client.get(USER_INFO_URL, headers=headers)
        ms_user = user_res.json()
        
        # Lấy Avatar (nếu cần thì bỏ comment dòng dưới)
        avatar_base64 = await get_ms_user_photo(ms_access_token)
        # avatar_base64 = None

    # --- BƯỚC 4: XỬ LÝ DATABASE ---
    email = ms_user.get("mail") or ms_user.get("userPrincipalName")
    full_name = ms_user.get("displayName")
    ms_job_title = ms_user.get("jobTitle") or ""
    
    # Sử dụng hàm map role đã định nghĩa
    assigned_role = map_ms_job_to_role(ms_job_title)

    user_obj = db.query(User).filter(User.email == email).first()

    if not user_obj:
        # Tạo mật khẩu ngẫu nhiên cho user OAuth (vì họ không dùng pass để login)
        random_password = secrets.token_urlsafe(16)
        hashed_password = get_password_hash(random_password)

        user_obj = User(
            email=email,
            hashed_password=hashed_password, # ✅ Thêm trường này để tránh lỗi DB not null
            full_name=full_name,
            job_title=ms_job_title,
            role=assigned_role,
            auth_provider="microsoft",
            security_clearance=SecurityLevel.PUBLIC,
            status=True,
            avatar_url=avatar_base64
        )
        db.add(user_obj)
        db.commit()
        db.refresh(user_obj)
    else:
        # Cập nhật thông tin mới nhất từ Microsoft
        user_obj.full_name = full_name
        user_obj.job_title = ms_job_title
        user_obj.avatar_url = avatar_base64 # Update avatar nếu cần
        db.commit()

    # --- BƯỚC 5: TẠO TOKEN ---
    access_token = create_access_token(
        data={"sub": user_obj.email, "id": user_obj.user_id, "role": user_obj.role.value},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    refresh_token = create_refresh_token(
        data={"sub": user_obj.email, "id": user_obj.user_id, "type": "refresh"},
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )

    # Thay vì set_cookie, ta bắn token thẳng lên URL để Frontend hứng
    target_url = (
        f"{FRONTEND_URL}/auth/callback"
        f"?access_token={access_token}"
        f"?refresh_token={refresh_token}" # Lưu ý: Frontend cần xử lý cắt chuỗi khéo léo hoặc dùng &
    )
    
    # Sửa lại format URL cho chuẩn:
    target_url = f"{FRONTEND_URL}/auth/callback?access_token={access_token}&refresh_token={refresh_token}"

    response = RedirectResponse(url=target_url)

    # # --- BƯỚC 6: REDIRECT & SET COOKIE ---
    # frontend_callback = f"{FRONTEND_URL}/auth/callback?state=success"
    # response = RedirectResponse(url=frontend_callback)

    # response.set_cookie(
    #     key="access_token",
    #     value=access_token,
    #     httponly=True,
    #     secure=IS_PROD,
    #     samesite="none",
    #     max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    #     path="/"
    # )

    # response.set_cookie(
    #     key="refresh_token",
    #     value=refresh_token,
    #     httponly=True,
    #     secure=IS_PROD,
    #     samesite="none",
    #     max_age=refresh_max_age,
    #     path="/"
    # )
    
    # Xóa state cookies
    response.delete_cookie("oauth_state")
    response.delete_cookie("oauth_remember")

    return response