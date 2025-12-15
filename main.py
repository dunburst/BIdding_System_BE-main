from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session
import models
from database import engine, get_db
from routers import auth, bidding, crawl
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# 1. Tự động tạo các bảng trong Database nếu chưa tồn tại
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="PC1 Bidding Management System")

app.include_router(auth.router)
app.include_router(bidding.router)
app.include_router(crawl.router)

# API Test kết nối
@app.get("/")
def read_root():
    return {"message": "Hệ thống quản lý đấu thầu PC1 đang chạy!"}

origins = [
    "*", # Cho phép tất cả các nguồn (dùng cho dev/test)
    # Hoặc bạn có thể chỉ định cụ thể:
    # "http://localhost:3000",
    # "http://192.168.1.10:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Cho phép tất cả các method (POST, GET, PUT, DELETE...)
    allow_headers=["*"],  # Cho phép tất cả các header (Authorization, Content-Type...)
)
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "status": exc.status_code,
            "message": exc.detail,
            "errors": None # Không có lỗi chi tiết từng field
        },
    )

# --- 2. XỬ LÝ LỖI VALIDATION (Lỗi do Pydantic/FastAPI tự bắt) ---
# Ví dụ: Gửi email sai định dạng, thiếu password...
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors_dict = {}
    
    # Gom nhóm lỗi theo từng field
    for error in exc.errors():
        # Lấy tên field (vd: "email", "password")
        # loc thường là ('body', 'email') -> lấy phần tử cuối
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
            "errors": errors_dict # Trả về object lỗi chi tiết
        },
    )
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)