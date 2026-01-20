import os
import traceback
from pathlib import Path
from typing import List, Dict, Any

# [QUAN TRỌNG] Tắt tính năng Symlink của HuggingFace để tránh lỗi WinError 1314
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat
# [FIX] Import thêm bộ cắt theo ký tự để xử lý đoạn văn quá dài
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

class DoclingService:
    def __init__(self):
        print("📄 [Docling] Đang khởi tạo DocumentConverter (Smart Image Mode)...")
        
        # 1. Cấu hình Pipeline để trích xuất ảnh
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True
        pipeline_options.do_table_structure = True
        # BẬT tính năng sinh ảnh cho các phần tử Picture/Figure
        pipeline_options.generate_picture_images = True 
        # Tăng scale để ảnh cắt ra nét hơn (tốt cho LitePali soi chi tiết)
        pipeline_options.images_scale = 1.9

        # 2. Khởi tạo Converter với cấu hình trên
        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )

    def process_pdf_to_markdown(self, pdf_path: str) -> str:
        """
        Chuyển PDF sang Markdown (Giữ nguyên hàm cũ cho Text RAG)
        """
        print(f"📄 [Docling] Đang chuyển đổi PDF sang Markdown: {pdf_path}")
        try:
            result = self.converter.convert(pdf_path)
            markdown_content = result.document.export_to_markdown()
            
            if markdown_content:
                print(f"✅ Docling Text Success! Preview: {markdown_content[:100].replace(chr(10), ' ')}...")
            else:
                print("⚠️ Docling Warning: Nội dung trả về rỗng.")
                
            return markdown_content
        except Exception as e:
            print(f"❌ Lỗi Docling Convert Text: {e}")
            traceback.print_exc()
            return ""

    def chunk_markdown(self, markdown_text: str):
        """
        Cắt nhỏ Markdown. 
        [UPDATE] Thêm cơ chế cắt an toàn (RecursiveCharacterTextSplitter) 
        để tránh lỗi 400 Bad Request của OpenAI (max 8192 tokens).
        """
        if not markdown_text:
            return []
            
        # BƯỚC 1: Cắt theo ngữ nghĩa (Header)
        headers_to_split_on = [
            ("#", "Header 1"), 
            ("##", "Header 2"), 
            ("###", "Header 3")
        ]
        markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
        header_splits = markdown_splitter.split_text(markdown_text)

        # BƯỚC 2: Cắt theo kích thước an toàn (Safety Split)
        # OpenAI text-embedding-3-large giới hạn 8192 tokens (~32,000 ký tự).
        # Ta đặt giới hạn an toàn là 4000 ký tự (~1000 tokens) để đảm bảo không bao giờ lỗi
        # và tăng độ chính xác khi tìm kiếm (RAG hoạt động tốt hơn với chunk nhỏ).
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=4000,      # Giới hạn mỗi chunk khoảng 4000 ký tự
            chunk_overlap=400,    # Gối đầu 400 ký tự để không mất ngữ cảnh
            separators=["\n\n", "\n", " ", ""] # Ưu tiên ngắt ở xuống dòng
        )

        final_chunks = text_splitter.split_documents(header_splits)
        
        print(f"✂️ Chunking: Từ {len(header_splits)} phần (Header) -> Cắt thành {len(final_chunks)} chunks nhỏ (Safe Size).")
        return final_chunks

    # --- HÀM TRÍCH XUẤT ẢNH THÔNG MINH (GIỮ NGUYÊN) ---
    def extract_images_from_pdf(self, pdf_path: str, output_dir: str) -> List[Dict[str, Any]]:
        """
        Dùng Docling để tìm và cắt (crop) các hình ảnh/biểu đồ trong PDF.
        Lưu ảnh vào output_dir và trả về danh sách đường dẫn + metadata.
        """
        print(f"🖼️ [Docling] Đang quét và cắt ảnh từ: {os.path.basename(pdf_path)}")
        extracted_images = []
        
        try:
            # Convert để lấy cấu trúc
            conv_res = self.converter.convert(pdf_path)
            doc = conv_res.document
            
            # Tạo thư mục lưu ảnh
            os.makedirs(output_dir, exist_ok=True)
            
            counter = 0
            # Duyệt qua tất cả các phần tử là Picture (Ảnh) hoặc Figure (Hình vẽ)
            for i, element in enumerate(doc.pictures):
                # Lấy đối tượng ảnh đã được Docling crop sẵn
                image_obj = element.get_image(doc)
                
                if image_obj:
                    counter += 1
                    # Đặt tên file: page_X_img_Y.jpg
                    page_no = element.prov[0].page_no
                    file_name = f"page_{page_no}_img_{counter}.jpg"
                    save_path = os.path.join(output_dir, file_name)
                    
                    # Lưu ảnh xuống đĩa
                    image_obj.save(save_path, "JPEG")
                    
                    # Thêm vào danh sách kết quả
                    extracted_images.append({
                        "path": save_path,
                        "page_number": page_no,
                        "type": "figure" # Đánh dấu đây là hình vẽ/sơ đồ
                    })
            
            print(f"✅ [Docling] Đã tìm thấy và cắt {len(extracted_images)} hình ảnh quan trọng.")
            return extracted_images

        except Exception as e:
            print(f"❌ Lỗi Docling Extract Images: {e}")
            traceback.print_exc()
            return []

# Singleton
docling_service = DoclingService()
def get_docling_service():
    return docling_service