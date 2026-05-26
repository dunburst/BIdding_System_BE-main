# Hướng dẫn chạy project lần đầu

## Yêu cầu cài đặt

| Công cụ | Phiên bản | Link |
|---|---|---|
| Python | 3.10+ | https://www.python.org/downloads/ |
| Docker Desktop | mới nhất | https://www.docker.com/products/docker-desktop/ |
| ODBC Driver 17 for SQL Server | 17 | https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server |

> **Không cần cài Edge WebDriver nữa** — Crawler đã chuyển sang dùng Playwright, tự quản lý browser.

---

## Bước 1 — Cấu hình file `.env`

Chỉnh sửa các giá trị phù hợp với máy anh:

```env
# SQL Server
DB_SERVER=localhost          # hoặc IP server SQL
DB_NAME=Bidding              # tên database
DB_USER=nvduong
DB_PASSWORD=duong123456
DB_DRIVER=ODBC Driver 17 for SQL Server

# MinIO (Docker)
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=admin_user
MINIO_SECRET_KEY=MinioStrongPassword2024!
MINIO_SECURE=false
MINIO_PUBLIC_URL=http://<IP_MÁY_ANH>:9000   # IP mà frontend truy cập được, VD: http://10.31.1.85:9000
```

---

## Bước 2 — Khởi động MinIO bằng Docker

```powershell
# Chạy từ thư mục gốc project
docker-compose up -d
```

Kiểm tra container đã chạy chưa:

```powershell
docker-compose ps
```

Kết quả mong đợi:

```
NAME    STATUS          PORTS
minio   Up (healthy)    0.0.0.0:9000->9000/tcp, 0.0.0.0:9001->9001/tcp
```

Truy cập MinIO Web Console để kiểm tra:
- URL: `http://localhost:9001`
- User: `admin_user`
- Password: `MinioStrongPassword2024!`

---

## Bước 3 — Tạo môi trường Python và cài thư viện

```powershell
# Tạo virtual environment
python -m venv venv

# Kích hoạt venv
.\venv\Scripts\Activate.ps1

# Cài thư viện từ requirements
pip install -r requirements.txt

# Cài Playwright (thư viện crawler mới)
pip install playwright

# Tải browser Chromium về (chỉ cần chạy 1 lần)
playwright install chromium
```

---

## Bước 4 — Chạy Backend

```powershell
# Đảm bảo venv đang được kích hoạt
.\venv\Scripts\Activate.ps1

# Chạy server
uvicorn main:app --host 0.0.0.0 --port 43210 --reload
```

API docs sau khi chạy:
- Swagger: `http://localhost:43210/docs`
- Scalar: `http://localhost:43210/scalar`

---

## Bước 5 — Chạy crawler thủ công cho 1 link (tuỳ chọn)

Sửa `target_url` trong [crawler_bot.py](app/integrations/crawlers/crawler_bot.py) ở cuối file, sau đó:

```powershell
python -m app.integrations.crawlers.crawler_bot
```

---

## Quản lý Docker MinIO

```powershell
# Dừng
docker-compose down

# Dừng và xóa toàn bộ data
docker-compose down -v

# Xem log
docker-compose logs minio

# Khởi động lại
docker-compose restart minio
```

---

## Cấu trúc lưu trữ file

```
MinIO (Docker volume: minio_data)
└── bucket: files/
      └── {ma_tbmt}/
            └── {ten_file}.docx
```

URL file được lưu vào bảng `bidding_package_files.file_path` dạng:
```
http://<MINIO_PUBLIC_URL>/files/{ma_tbmt}/{ten_file}
```

---

## Troubleshooting

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| `Import "playwright.sync_api" could not be resolved` | Playwright chưa được cài | Chạy `pip install playwright` rồi `playwright install chromium` |
| `NameResolutionError` khi kết nối MinIO | MINIO_ENDPOINT sai hoặc Docker chưa chạy | Chạy `docker-compose up -d` |
| `SSLError: wrong version number` | MINIO_SECURE=true nhưng MinIO chạy HTTP | Đặt `MINIO_SECURE=false` trong `.env` |
| `BiddingProject failed to locate` | Import thiếu model | Đã sửa trong `crawler_bot.py` — import đủ rồi |
| Lỗi kết nối SQL Server | Sai chuỗi kết nối hoặc ODBC chưa cài | Kiểm tra `.env` và cài ODBC Driver 17 |
| `Không bắt được dữ liệu API` | Trang load chưa xong hoặc web thay đổi cấu trúc | Tăng `wait_for_timeout` trong `process_package` |
