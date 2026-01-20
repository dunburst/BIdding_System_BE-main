import os
import re
import nest_asyncio
from dotenv import load_dotenv
from llama_parse import LlamaParse, ResultType
from docling.document_converter import DocumentConverter

# Apply nest_asyncio để tránh lỗi event loop khi chạy trong môi trường async của FastAPI
nest_asyncio.apply()

# Load biến môi trường
load_dotenv()

def parse_pdf_to_markdown(file_path: str) -> str:
    """
    Sử dụng LlamaParse để chuyển PDF sang Markdown (giữ cấu trúc bảng)
    """
    api_key = os.getenv("LLAMA_CLOUD_API_KEY")
    if not api_key:
        raise ValueError("❌ Thiếu LLAMA_CLOUD_API_KEY trong file .env")

    print(f"🔄 [Ingest] Đang đọc file qua LlamaCloud: {file_path}...")
    
    parser = LlamaParse(
        api_key=api_key,
        result_type=ResultType.MD,
        language="vi", 
        verbose=True
    )
    
    documents = parser.load_data(file_path)
    # Gộp các trang thành 1 chuỗi văn bản duy nhất
    full_text = "\n\n".join([doc.text for doc in documents])
    
    return full_text

def chunk_by_chapters(markdown_text: str) -> list:
    """
    Chia nhỏ văn bản theo Header Markdown (Cấp 1, 2, 3)
    Sử dụng Regex để bắt được cả: # TIÊU ĐỀ, ## TIÊU ĐỀ, ### TIÊU ĐỀ
    """
    chunks = []
    
    # Regex pattern: 
    # ^#{1,3} : Bắt đầu dòng bằng 1 đến 3 dấu #
    # \s+     : Theo sau là khoảng trắng
    # .+      : Lấy hết nội dung còn lại của dòng (Tiêu đề)
    # (?m)    : Chế độ multiline (xử lý từng dòng)
    pattern = r'(^#{1,3}\s+.+)'
    
    # re.split sẽ trả về danh sách: [Intro, Header1, Content1, Header2, Content2...]
    parts = re.split(pattern, markdown_text, flags=re.MULTILINE)
    
    # Xử lý phần mở đầu (trước header đầu tiên) nếu có
    if parts[0].strip():
        chunks.append({
            "chapter_title": "Giới thiệu chung",
            "category": "general",
            "full_content": parts[0].strip()
        })
    
    # Lặp qua các phần còn lại (Bước nhảy 2 vì Header và Content đi theo cặp)
    for i in range(1, len(parts), 2):
        header = parts[i].strip()             # VD: "## CHƯƠNG I..."
        # Kiểm tra xem có phần content đi kèm không
        content = parts[i+1].strip() if i+1 < len(parts) else ""
        
        # Gộp lại thành chunk hoàn chỉnh để AI đọc
        full_chunk_text = f"{header}\n\n{content}"
        
        # Làm sạch tiêu đề (bỏ dấu # để dễ đọc log)
        clean_title = re.sub(r'#+', '', header).strip()
        
        # --- PHÂN LOẠI (TAGGING) ---
        # Giúp định hướng dữ liệu (Optional: sau này có thể dùng để filter context)
        category = "general"
        lower_title = clean_title.lower()
        
        if any(x in lower_title for x in ["tiêu chuẩn", "đánh giá", "chấm điểm", "chương iii"]):
            category = "evaluation_criteria" 
        elif any(x in lower_title for x in ["yêu cầu kỹ thuật", "phạm vi", "giải pháp", "chương v"]):
            category = "technical_requirements"
        elif any(x in lower_title for x in ["nhân sự", "chủ chốt", "cán bộ"]):
            category = "personnel"
        elif any(x in lower_title for x in ["tài chính", "doanh thu", "năng lực"]):
            category = "financial"
        elif any(x in lower_title for x in ["thiết bị", "máy móc"]):
            category = "equipment"
        elif any(x in lower_title for x in ["mời thầu", "thủ tục", "bảo đảm"]):
            category = "admin"

        chunks.append({
            "chapter_title": clean_title,
            "category": category,
            "full_content": full_chunk_text
        })
        
    print(f"✅ [Ingest] Đã tách được {len(chunks)} phân đoạn theo Header Markdown.")
    return chunks

# def parse_pdf_to_markdown(file_path: str) -> str:
#     """
#     Sử dụng Docling để chuyển PDF sang Markdown (Chạy local, giữ cấu trúc bảng tốt)
#     """
#     if not os.path.exists(file_path):
#         raise FileNotFoundError(f"❌ Không tìm thấy file: {file_path}")

#     print(f"🔄 [Ingest] Đang xử lý file qua Docling (Local): {file_path}...")
    
#     try:
#         # Khởi tạo Converter
#         converter = DocumentConverter()
        
#         # Thực hiện convert
#         result = converter.convert(file_path)
        
#         # Xuất ra định dạng Markdown
#         # Docling tự động xử lý bảng và layout rất tốt
#         full_text = result.document.export_to_markdown()
        
#         print("✅ [Ingest] Đã convert xong PDF sang Markdown.")
#         return full_text
        
#     except Exception as e:
#         print(f"❌ Lỗi khi convert file: {e}")
#         raise e

# def chunk_by_chapters(markdown_text: str) -> list:
#     """
#     Chia nhỏ văn bản theo Header Markdown (Cấp 1, 2, 3)
#     Sử dụng Regex để bắt được cả: # TIÊU ĐỀ, ## TIÊU ĐỀ, ### TIÊU ĐỀ
#     (Giữ nguyên logic cũ vì Docling cũng xuất ra Markdown chuẩn)
#     """
#     chunks = []
    
#     # Regex pattern bắt header
#     pattern = r'(^#{1,3}\s+.+)'
    
#     parts = re.split(pattern, markdown_text, flags=re.MULTILINE)
    
#     # Xử lý phần mở đầu
#     if parts[0].strip():
#         chunks.append({
#             "chapter_title": "Giới thiệu chung",
#             "category": "general",
#             "full_content": parts[0].strip()
#         })
    
#     # Lặp qua các phần còn lại
#     for i in range(1, len(parts), 2):
#         header = parts[i].strip()
#         content = parts[i+1].strip() if i+1 < len(parts) else ""
        
#         full_chunk_text = f"{header}\n\n{content}"
        
#         # Clean title
#         clean_title = re.sub(r'#+', '', header).strip()
        
#         # --- PHÂN LOẠI (TAGGING) ---
#         category = "general"
#         lower_title = clean_title.lower()
        
#         if any(x in lower_title for x in ["tiêu chuẩn", "đánh giá", "chấm điểm", "chương iii"]):
#             category = "evaluation_criteria" 
#         elif any(x in lower_title for x in ["yêu cầu kỹ thuật", "phạm vi", "giải pháp", "chương v"]):
#             category = "technical_requirements"
#         elif any(x in lower_title for x in ["nhân sự", "chủ chốt", "cán bộ"]):
#             category = "personnel"
#         elif any(x in lower_title for x in ["tài chính", "doanh thu", "năng lực"]):
#             category = "financial"
#         elif any(x in lower_title for x in ["thiết bị", "máy móc"]):
#             category = "equipment"
#         elif any(x in lower_title for x in ["mời thầu", "thủ tục", "bảo đảm"]):
#             category = "admin"

#         chunks.append({
#             "chapter_title": clean_title,
#             "category": category,
#             "full_content": full_chunk_text
#         })
        
#     print(f"✅ [Ingest] Đã tách được {len(chunks)} phân đoạn theo Header Markdown.")
#     return chunks