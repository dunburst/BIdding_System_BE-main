import os
import sys

# Thêm đường dẫn để import được module services
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.integrations.ai.data_processing.embedding import ingest_markdown_content

# Tên file MD bạn vừa tạo ra từ bước trước
INPUT_MD_FILE = "test_llama_output.md"

def main():
    # 1. Kiểm tra file tồn tại
    if not os.path.exists(INPUT_MD_FILE):
        print(f"❌ Lỗi: Không tìm thấy file '{INPUT_MD_FILE}'")
        print("👉 Hãy chạy 'python test_llama.py' trước để tạo file này.")
        return

    # 2. Đọc nội dung
    print(f"📂 Đang đọc file: {INPUT_MD_FILE}...")
    try:
        with open(INPUT_MD_FILE, "r", encoding="utf-8") as f:
            md_text = f.read()
    except Exception as e:
        print(f"❌ Lỗi đọc file: {e}")
        return

    # 3. Gọi Service để cắt và lưu
    # Giả lập tên file gốc là 'Bien_phap_thi_cong_T3' để lưu vào metadata
    ingest_markdown_content("Bien_phap_thi_cong_T3", md_text)

if __name__ == "__main__":
    main()