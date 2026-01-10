# services/requirement_service.py

import os
from services.ai_pipeline.llama_service import llama_service
from services.chroma_service import chroma_service
# Import hàm cắt chương bạn đã viết ở file khác (hoặc để chung)
from services.ai_pipeline.ingest import chunk_by_chapters 

class RequirementService:
    def process_requirement_file(self, file_path: str, filename: str) -> str:
        """
        1. Đọc file HSMT qua LlamaParse
        2. Cắt nhỏ thành từng chương
        3. Lưu vào Vector DB (Collection: current_requirements)
        """
        print(f"📖 Đang đọc Hồ sơ yêu cầu từ: {filename}...")
        
        # Bước 1: Parse PDF -> Markdown
        full_text = llama_service.parse_pdf_to_markdown(file_path)
        
        if not full_text:
            return ""

        # Bước 2: Dọn dẹp DB cũ (Để đảm bảo Bot không nhớ nhầm dự án trước)
        # Tùy logic business, ở đây tôi chọn xóa cũ nạp mới cho sạch
        # chroma_service.clear_current_requirements()

        # Bước 3: Cắt nhỏ (Chunking)
        chunks = chunk_by_chapters(full_text)
        print(f"✂️ Đã cắt yêu cầu thành {len(chunks)} chương/phần.")

        # Bước 4: Lưu vào ChromaDB (Requirement Collection)
        chroma_service.save_requirements(chunks, source_filename=filename)
        
        return full_text # Vẫn trả về text để xem preview nếu cần

req_service = RequirementService()