import os
import nest_asyncio
from dotenv import load_dotenv
from llama_parse import LlamaParse

# Patch để chạy async trong môi trường sync (quan trọng cho Jupyter/Script)
nest_asyncio.apply()
load_dotenv()

class LlamaParseService:
    def __init__(self):
        self.api_key = os.getenv("LLAMA_CLOUD_API_KEY")
        if not self.api_key:
            print("⚠️ Cảnh báo: Thiếu LLAMA_CLOUD_API_KEY")

    def parse_pdf_to_markdown(self, file_path: str) -> str:
        """
        Sử dụng LlamaParse để chuyển PDF sang Markdown giữ nguyên cấu trúc bảng biểu.
        """
        if not os.path.exists(file_path):
            return f"Error: File not found at {file_path}"

        print(f"🦙 LlamaParse đang xử lý file: {os.path.basename(file_path)}...")

        try:
            # Cấu hình Parser tối ưu cho Tiếng Việt và Bảng biểu
            parser = LlamaParse(
                api_key=self.api_key,
                result_type="markdown",  # Output chuẩn Markdown
                language="vi",           # Hỗ trợ tiếng Việt tốt hơn
                verbose=True,
                # Các options nâng cao để xử lý bảng phức tạp (Premium mode - tốn credit hơn chút nhưng ngon)
                premium_mode=True,       
                split_by_page=False,     # Gom hết vào 1 file md
            )

            # Gọi API (quá trình này sẽ upload file lên cloud của LlamaIndex để xử lý)
            documents = parser.load_data(file_path)
            
            # Ghép kết quả lại (thường chỉ có 1 doc nếu split_by_page=False)
            full_markdown = "\n\n".join([doc.text for doc in documents])
            
            return full_markdown

        except Exception as e:
            print(f"❌ Lỗi LlamaParse: {e}")
            return ""

# Khởi tạo singleton
llama_service = LlamaParseService()