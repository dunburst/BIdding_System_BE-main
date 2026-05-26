# services/requirement_service.py

import os

from fastapi import Depends
from app.integrations.ai.data_processing.chroma_service import ChromaService, get_chroma_service
from app.integrations.ai.provider.llama_service import llama_service 
from app.integrations.ai.pipeline.ingest import chunk_by_chapters

class RequirementService:
    def __init__(self, chroma_service: ChromaService):
        self.chroma = chroma_service
    # Thêm tham số project_name vào hàm này
    def process_requirement_file(self, file_path: str, filename: str, project_name: str) -> str:
        
        print(f"📖 Đang đọc Hồ sơ yêu cầu cho dự án [{project_name}] từ: {filename}...")
        
        # 1. Parse PDF -> Markdown
        full_text = llama_service.parse_pdf_to_markdown(file_path)
        
        if not full_text:
            return ""
        

        # 2. Cắt nhỏ (Chunking)
        chunks = chunk_by_chapters(full_text)
        print(f"✂️ Đã cắt yêu cầu thành {len(chunks)} chương/phần.")

        # 3. Lưu vào ChromaDB kèm Project Name
        # Gọi hàm save mới đã sửa ở trên
        self.chroma.save_requirements(chunks, source_filename=filename, project_name=project_name)
        
        return full_text
    
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