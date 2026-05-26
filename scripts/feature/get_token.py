# File: get_token.py
import msal
import os

# 1. Điền Client ID của bạn vào đây
CLIENT_ID = "73923cc9-12e8-44ae-ac7c-0683816b0dbf" 
SCOPES = ["Files.ReadWrite.All", "User.Read", "Offline_access"]

def get_refresh_token():
    # Cấu hình App cho tài khoản cá nhân
    app = msal.PublicClientApplication(
        client_id=CLIENT_ID,
        authority="https://login.microsoftonline.com/common"
    )

    # Bắt đầu quy trình Device Flow
    flow = app.initiate_device_flow(scopes=SCOPES)
    
    if "user_code" not in flow:
        print("❌ Lỗi khởi tạo Flow. Kiểm tra lại Client ID.")
        return

    print("\n" + "="*60)
    print("⚠️  HÀNH ĐỘNG CẦN THIẾT:")
    print(f"1. Mở trình duyệt và vào: {flow['verification_uri']}")
    print(f"2. Nhập mã code này: {flow['user_code']}")
    print("3. Đăng nhập bằng tài khoản Gmail/Outlook của bạn.")
    print("="*60 + "\n")
    print("⏳ Đang chờ bạn đăng nhập...")

    # Script sẽ dừng ở đây chờ bạn đăng nhập trên web
    result = app.acquire_token_by_device_flow(flow)

    if "refresh_token" in result:
        print("\n✅ ĐĂNG NHẬP THÀNH CÔNG!")
        print("-" * 60)
        print("Hãy copy toàn bộ chuỗi dưới đây vào file .env (biến ONEDRIVE_REFRESH_TOKEN):")
        print("-" * 60)
        print(result['refresh_token'])
        print("-" * 60)
    else:
        print(f"❌ Lỗi: {result.get('error_description')}")

if __name__ == "__main__":
    get_refresh_token()