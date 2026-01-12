# services/requirement_service.py

import os

from fastapi import Depends
from services.chroma_service import ChromaService, get_chroma_service
from services.ai_pipeline.llama_service import llama_service 
from services.ai_pipeline.ingest import chunk_by_chapters

class RequirementService:
    def __init__(self, chroma_service: ChromaService):
        self.chroma = chroma_service
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
        self.chroma.save_requirements(chunks, source_filename=filename)
        
        return full_text # Vẫn trả về text để xem preview nếu cần
    
    # --- HÀM MỚI (CHUYỂN VÀO ĐÂY) ---
    def process_large_document_background(self, file_path: str, original_filename: str):
        """
        Hàm này chạy ngầm, dùng self.chroma để lưu và llama_service để parse
        """
        try:
            print(f"🚀 [Background] Service đang xử lý file: {original_filename}...")
            
            # 1. Gọi Llama (vẫn dùng biến global từ file kia)
            markdown_text = llama_service.parse_pdf_to_markdown(file_path)
            
            if not markdown_text:
                print(f"❌ [Background] Lỗi: Không đọc được nội dung file {original_filename}")
                return

            # 2. Cắt nhỏ
            chunks = chunk_by_chapters(markdown_text)
            print(f"✂️ [Background] Đã cắt thành {len(chunks)} chương.")

            # 3. Lưu vào DB (Dùng self.chroma đã được inject)
            self.chroma.save_chunks_to_db(chunks, source_filename=original_filename)
            
            print(f"✅ [Background] Hoàn tất xử lý file {original_filename}!")

        except Exception as e:
            print(f"❌ [Background] Lỗi nghiêm trọng: {str(e)}")
        
        finally:
            # Dọn dẹp file tạm
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"🧹 Đã xóa file tạm: {file_path}")

# --- THÊM Provider cho RequirementService ---
def get_req_service(
    # FastAPI sẽ tự động lấy ChromaService trước, rồi nhét vào đây
    chroma: ChromaService = Depends(get_chroma_service) 
) -> RequirementService:
    return RequirementService(chroma)