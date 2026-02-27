import sys
import os

# Thêm thư mục hiện tại vào sys.path để Python tìm thấy module 'services'
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from app.integrations.ai.provider.llama_service import llama_service
except ImportError as e:
    print(f"❌ Lỗi Import: {e}")
    print("👉 Hãy chắc chắn bạn đã tạo file 'services/ai_pipeline/llama_service.py' và cài thư viện llama-parse.")
    sys.exit(1)

# Chọn 1 file HSMT khó nhằn nhất của bạn để test
FILE_PATH = "Bien phap thi cong T3.pdf" 
OUTPUT_PATH = "test_llama_output.md"

def test_conversion():
    if not os.path.exists(FILE_PATH):
        print(f"❌ Chưa tìm thấy file test tại: {FILE_PATH}")
        print("💡 Gợi ý: Kiểm tra lại đường dẫn file hoặc copy file PDF ra cùng thư mục với script này.")
        return

    print("🚀 Bắt đầu gửi file sang LlamaParse (Cloud)...")
    print("⏳ Vui lòng đợi 1-2 phút tùy độ dài file...")
    
    md_content = llama_service.parse_pdf_to_markdown(FILE_PATH)
    
    if md_content:
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"✅ Thành công! Đã lưu kết quả tại: {OUTPUT_PATH}")
        print("👉 Hãy mở file .md lên để xem bảng biểu có được giữ nguyên không.")
    else:
        print("❌ Thất bại. LlamaParse trả về nội dung rỗng.")

if __name__ == "__main__":
    test_conversion()