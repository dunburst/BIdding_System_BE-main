import os
from dotenv import load_dotenv

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
import models
from database import engine, get_db

# Import các Router
from routers import (
    bidding, auth, crawler, organization, user, abac, system, 
    project, googlelogin, task, bidding_req, agent_api, # <-- Đảm bảo agent_api có trong file routers/__init__.py
    onedrive_router, generation, drafting
)

from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from mcp_drive.router import router as drive_router
from starlette.middleware.sessions import SessionMiddleware
from crawler_bot import start_scheduler_service

# 3. Tự động tạo các bảng trong Database nếu chưa tồn tại
models.Base.metadata.create_all(bind=engine)

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
    "https://bidding-management.vercel.app",
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
app.include_router(auth.router)
app.include_router(bidding.router)
app.include_router(bidding_req.router)
app.include_router(crawler.router)
app.include_router(organization.router)
app.include_router(user.router)
app.include_router(abac.router)
app.include_router(system.router)
app.include_router(project.router)
app.include_router(googlelogin.router)
app.include_router(task.router)
app.include_router(drive_router)
app.include_router(drafting.router)
app.include_router(onedrive_router.router)
app.include_router(generation.router)
app.include_router(agent_api.router)

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

if __name__ == "__main__":
    import uvicorn
    # In ra key lần nữa lúc khởi động uvicorn để chắc chắn
    if os.getenv("LANGCHAIN_API_KEY"):
        print("🚀 LangSmith Tracing: ENABLED")
    else:
        print("⚠️ LangSmith Tracing: DISABLED")
        
    uvicorn.run(app, host="0.0.0.0", port=43210, timeout_keep_alive=120)