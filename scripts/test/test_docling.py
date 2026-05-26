import os
import time
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions

# --- CẤU HÌNH ---
PDF_PATH = "Bien phap thi cong T3.pdf" 

class OptimizedDoclingService:
    def __init__(self):
        print("🚀 Khởi tạo Docling (Chế độ tối ưu)...")
        
        # --- CẤU HÌNH PIPELINE ---
        # 1. Tạo options
        pipeline_options = PdfPipelineOptions()
        
        # 2. QUAN TRỌNG: Tắt OCR nếu file là digital text (giúp chạy cực nhanh)
        # Nếu file của bạn là SCANNED (ảnh chụp), hãy đổi thành True
        pipeline_options.do_ocr = False  
        
        # 3. Vẫn giữ tính năng nhận diện bảng biểu
        pipeline_options.do_table_structure = True

        # 4. Khởi tạo Converter với options đã chỉnh
        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )
        print("✅ Đã cấu hình: Tắt OCR (Fast Mode), Bật Table Recognition.")

    def parse_full_pdf(self, file_path: str):
        if not os.path.exists(file_path):
            print(f"❌ Không tìm thấy file {file_path}")
            return

        print(f"📄 Đang xử lý: {os.path.basename(file_path)}")
        start_time = time.time()

        try:
            # Convert
            result = self.converter.convert(file_path)
            
            # Export
            full_markdown = result.document.export_to_markdown()
            
            elapsed = time.time() - start_time
            
            # Thống kê
            num_pages = len(result.document.pages)
            print("-" * 60)
            print(f"✅ XONG! (Mất {elapsed:.2f}s cho {num_pages} trang)")
            
            # Lưu file
            output_filename = f"FAST_RESULT_{os.path.basename(file_path)}.md"
            with open(output_filename, "w", encoding="utf-8") as f:
                f.write(full_markdown)
                
            print(f"💾 Kết quả: {output_filename}")
            print("-" * 60)

        except Exception as e:
            print(f"❌ Lỗi: {e}")

if __name__ == "__main__":
    if not os.path.exists(PDF_PATH):
        PDF_PATH = input("Nhập đường dẫn file PDF: ").strip().strip('"')
    
    service = OptimizedDoclingService()
    service.parse_full_pdf(PDF_PATH)