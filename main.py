import os
from dotenv import load_dotenv

# Core Modules
from app.modules.auth.router import router as auth_router
from app.modules.users.router import router as users_router
from app.modules.organization.router import router as org_router
from app.modules.system.router import router as system_router
from app.modules.abac_config.router import router as abac_router
from app.modules.crawler_config.router import router as crawler_router
from app.modules.drafting.router import router as drafting_router

# Bidding Modules (Đã tách nhỏ)
from app.modules.bidding.package.router import router as bid_pkg_router
from app.modules.bidding.project.router import router as bid_proj_router
from app.modules.bidding.task.router import router as bid_task_router
from app.modules.bidding.requirement.router import router as bid_req_router

# Integrations
from app.integrations.google.googlelogin import router as google_auth_router
from app.integrations.google.mcp_drive.router import router as drive_router
from app.integrations.microsoft.onedrive_router import router as onedrive_router

# AI / Generation
from app.modules.ai_bidding.router import router as ai_bidding_router
# from routers import generation as generation_router # Giả định file này nằm ở root/routers

# --- 1. QUAN TRỌNG: LOAD BIẾN MÔI TRƯỜNG TRƯỚC TẤT CẢ ---
load_dotenv()

# [DEBUG] Kiểm tra xem Key LangSmith đã nhận chưa
ls_key = os.getenv("LANGCHAIN_API_KEY")
ls_proj = os.getenv("LANGCHAIN_PROJECT")
if ls_key:
    print(f"✅ LangSmith Configured: Project='{ls_proj}' | Key='{ls_key[:5]}...'")
else:
    print("❌ CẢNH BÁO: Chưa tìm thấy LANGCHAIN_API_KEY trong .env. Trace sẽ không hoạt động!")

# --- 2. SAU ĐÓ MỚI IMPORT CÁC THƯ VIỆN KHÁC ---
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
import app.infrastructure.database.all_models 
from app.infrastructure.database.database import engine, get_db, Base
import sentry_sdk
from scalar_fastapi import get_scalar_api_reference
from fastapi.openapi.docs import get_redoc_html


from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from app.integrations.crawlers.crawler_bot import start_scheduler_service

# 3. Tự động tạo các bảng trong Database nếu chưa tồn tại
Base.metadata.create_all(bind=engine)
sentry_sdk.init(
    dsn="https://ab7ffbb2dcf35915b8401d9a4b5ee942@o4510781631102976.ingest.de.sentry.io/4510781632675920",
    # Add data like request headers and IP for users,
    # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
    send_default_pii=True,
)
# 4. Khởi tạo App
app = FastAPI(
    title="PC1 Bidding Management System",
)

# --- MIDDLEWARE ---
@app.middleware("http")
async def strip_trailing_slash_middleware(request: Request, call_next):
    # Nếu path không phải là root "/" và có dấu "/" ở cuối -> bỏ đi
    if request.url.path != "/" and request.url.path.endswith("/"):
        request.scope["path"] = request.url.path.rstrip("/")
    response = await call_next(request)
    return response

app.add_middleware(SessionMiddleware, secret_key="bi_mat_khong_bat_mi")

# --- CORS ---
origins = [
    "http://localhost:3000",
    "http://26.152.34.61:3000",
    "http://10.10.0.158:3000",
    "http://10.11.1.26:3000",
    "https://baptist-nerve-coupled-evaluating.trycloudflare.com"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"], 
)

# --- 5. ĐĂNG KÝ ROUTER ---
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(org_router)
app.include_router(system_router)
app.include_router(abac_router)
app.include_router(crawler_router)
app.include_router(bid_pkg_router)
app.include_router(bid_proj_router)
app.include_router(bid_req_router)
app.include_router(bid_task_router)
app.include_router(drafting_router)
app.include_router(drive_router)
app.include_router(google_auth_router)
app.include_router(onedrive_router)
app.include_router(ai_bidding_router)
# app.include_router(generation_router.router)

# [QUAN TRỌNG] Bật router Agent lên (tôi đã bỏ comment dòng này)
# Đảm bảo bạn đã có file routers/agent_api.py chứa endpoint


# --- EXCEPTION HANDLERS ---
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "status": exc.status_code,
            "message": exc.detail,
            "errors": None 
        },
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors_dict = {}
    for error in exc.errors():
        field = error["loc"][-1] 
        msg = error["msg"]
        if field not in errors_dict:
            errors_dict[field] = []
        errors_dict[field].append(msg)

    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "success": False,
            "status": 400,
            "message": "Dữ liệu đầu vào không hợp lệ",
            "errors": errors_dict 
        },
    )

# API Test kết nối
@app.get("/")
def read_root():
    return {"message": "Hệ thống quản lý đấu thầu PC1 đang chạy!"}

@app.get("/sentry-debug")
async def trigger_error():
    division_by_zero = 1 / 0
    
class CustomTheme:
    def __init__(self, theme_name: str):
        self.value = theme_name
@app.get("/scalar", include_in_schema=False)
async def scalar_html(request: Request):
    return get_scalar_api_reference(
        openapi_url=request.app.openapi_url,
        title="Bidding System Dashboard API",
        # Bạn có thể chọn các theme như 'purple', 'moon', 'solarized', v.v.
        theme=CustomTheme("deepSpace") # type: ignore
    )

if __name__ == "__main__":
    import uvicorn
    # In ra key lần nữa lúc khởi động uvicorn để chắc chắn
    if os.getenv("LANGCHAIN_API_KEY"):
        print("🚀 LangSmith Tracing: ENABLED")
    else:
        print("⚠️ LangSmith Tracing: DISABLED")
        
    uvicorn.run(app, host="0.0.0.0", port=43210, timeout_keep_alive=120)