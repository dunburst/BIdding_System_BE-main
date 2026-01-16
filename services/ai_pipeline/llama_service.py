import os
import time
import nest_asyncio
from dotenv import load_dotenv
from llama_parse import LlamaParse
# Docling imports
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions, TableFormerMode
from docling.datamodel.base_models import InputFormat
# Patch để chạy async trong môi trường sync (quan trọng cho Jupyter/Script)
nest_asyncio.apply()
load_dotenv()

class LlamaParseService:
    # def __init__(self):
    #     self.api_key = os.getenv("LLAMA_CLOUD_API_KEY","")
    #     if not self.api_key:
    #         print("⚠️ Cảnh báo: Thiếu LLAMA_CLOUD_API_KEY")

    # def parse_pdf_to_markdown(self, file_path: str) -> str:
    #     """
    #     Sử dụng LlamaParse để chuyển PDF sang Markdown giữ nguyên cấu trúc bảng biểu.
    #     """
    #     if not os.path.exists(file_path):
    #         return f"Error: File not found at {file_path}"

    #     print(f"🦙 LlamaParse đang xử lý file: {os.path.basename(file_path)}...")

    #     try:
    #         # Cấu hình Parser tối ưu cho Tiếng Việt và Bảng biểu
    #         parser = LlamaParse(
    #             api_key=self.api_key,
    #             result_type="markdown",  # Output chuẩn Markdown #type: ignore
    #             language="vi",           # Hỗ trợ tiếng Việt tốt hơn
    #             verbose=True,
    #             # Các options nâng cao để xử lý bảng phức tạp (Premium mode - tốn credit hơn chút nhưng ngon)
    #             premium_mode=True,       
    #             split_by_page=False,     # Gom hết vào 1 file md
    #         )

    #         # Gọi API (quá trình này sẽ upload file lên cloud của LlamaIndex để xử lý)
    #         documents = parser.load_data(file_path)
            
    #         # Ghép kết quả lại (thường chỉ có 1 doc nếu split_by_page=False)
    #         full_markdown = "\n\n".join([doc.text for doc in documents])
            
    #         return full_markdown

    #     except Exception as e:
    #         print(f"❌ Lỗi LlamaParse: {e}")
    #         return ""
    def __init__(self):
        """
        Khởi tạo Docling Converter.
        Lưu ý: Lần chạy đầu tiên sẽ tự động tải model về (khá lâu), các lần sau sẽ nhanh.
        """
        print("⚙️ Đang khởi tạo Docling Service (Load Model Local)...")
        
        # 1. Cấu hình Pipeline (Quy trình xử lý)
        pipeline_options = PdfPipelineOptions()
        
        # Bật OCR (tự động chạy nếu PDF là file scan ảnh)
        pipeline_options.do_ocr = True 
        
        # Bật tính năng tái tạo cấu trúc bảng (Table Structure)
        pipeline_options.do_table_structure = True
        
        # Chế độ xử lý bảng: ACCURATE (Chậm hơn chút nhưng chính xác cao cho bảng biểu phức tạp)
        # Nếu muốn nhanh hơn, có thể đổi thành TableFormerMode.FAST
        pipeline_options.table_structure_options = TableStructureOptions(
            mode=TableFormerMode.ACCURATE
        )

        # 2. Khởi tạo Converter với cấu hình trên
        # Chỉ init converter 1 lần để tái sử dụng, tiết kiệm RAM/CPU load model
        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )
        print("✅ Docling Service đã sẵn sàng!")

    def parse_pdf_to_markdown(self, file_path: str) -> str:
        """
        Sử dụng Docling để chuyển PDF sang Markdown giữ nguyên cấu trúc bảng biểu.
        """
        if not os.path.exists(file_path):
            return f"Error: File not found at {file_path}"

        print(f"🐢 Docling đang xử lý file (Local): {os.path.basename(file_path)}...")
        start_time = time.time()

        try:
            # Thực hiện convert
            # Docling chạy đồng bộ (sync), không cần await
            result = self.converter.convert(file_path)
            
            # Xuất ra Markdown
            # image_placeholder="" để không chèn link ảnh vào markdown text (giữ text sạch)
            full_markdown = result.document.export_to_markdown(image_placeholder="")
            
            elapsed_time = time.time() - start_time
            print(f"✅ Xử lý xong trong {elapsed_time:.2f}s")
            
            return full_markdown

        except Exception as e:
            print(f"❌ Lỗi Docling: {e}")
            return ""

# Khởi tạo singleton
llama_service = LlamaParseService()