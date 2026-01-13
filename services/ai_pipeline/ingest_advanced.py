import re
from typing import List, Dict, Any
# Bạn cần cài thư viện này: pip install langchain-text-splitters
from langchain_text_splitters import RecursiveCharacterTextSplitter

# --- 1. HÀM TRÍCH XUẤT METADATA (NÂNG CẤP: FILE NAME + CONTENT) ---
def extract_legal_metadata(filename: str, content_preview: str = "") -> Dict[str, Any]:
    """
    Phân tích tên file VÀ nội dung đầu trang để lấy thông tin pháp lý.
    Priority: Filename > Content
    """
    filename_lower = filename.lower()
    content_lower = content_preview.lower()[:2000] # Chỉ quét 2000 ký tự đầu

    # --- A. Xác định cấp độ (Luật > Nghị định > Thông tư) ---
    level = "unknown"
    priority = 0 
    
    # 1. Check Filename trước
    if "luật" in filename_lower or "luat" in filename_lower:
        level = "law"
        priority = 3
    elif "nghị định" in filename_lower or "nghi_dinh" in filename_lower:
        level = "decree"
        priority = 2
    elif "thông tư" in filename_lower or "thong_tu" in filename_lower:
        level = "circular"
        priority = 1
    
    # 2. Nếu Filename fail, check Content
    if level == "unknown":
        if "luật" in content_lower:
            level = "law"
            priority = 3
        elif "nghị định" in content_lower:
            level = "decree"
            priority = 2
        elif "thông tư" in content_lower:
            level = "circular"
            priority = 1

    # --- B. Tìm năm ban hành (4 số: 1990-2029) ---
    year = 0
    
    # 1. Check Filename
    year_match = re.search(r'(199\d|20[0-3]\d)', filename)
    if year_match:
        year = int(year_match.group(0))
    else:
        # 2. Check Content (Tìm số năm gần chữ "năm")
        # Regex tìm chuỗi kiểu: "năm 2023", "nam 2023", "/2023/"
        content_year_match = re.search(r'(?:năm|nam|/)\s*(199\d|20[0-3]\d)', content_lower)
        if content_year_match:
            year = int(content_year_match.group(1))

    return {
        "legal_level": level,
        "legal_priority": priority, # [FIX] Sửa lỗi chính tả priorityy cũ
        "promulgation_year": year,
        "source_file": filename
    }

def clean_text(text: str) -> str:
    # Xóa các dòng chỉ có số (số trang)
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        # Nếu dòng ngắn < 5 ký tự và là số -> Bỏ qua
        if len(line.strip()) < 5 and line.strip().isdigit():
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)
# --- 2. HÀM XỬ LÝ CHÍNH (GIỮ NGUYÊN LOGIC CŨ, CHỈ THÊM THAM SỐ) ---
def process_hierarchical_chunks(markdown_text: str, filename: str) -> List[Dict[str, Any]]:
    
    # Bước 1: Tách Parent
    parent_pattern = r'(^#{1,3}\s+.+)'
    parts = re.split(parent_pattern, markdown_text, flags=re.MULTILINE)
    
    # [NÂNG CẤP] Truyền thêm nội dung text vào để scan
    file_metadata = extract_legal_metadata(filename, content_preview=markdown_text)
    
    print(f"🏷️ Metadata (Updated) {filename}: {file_metadata}")
    
    parent_chunks = []
    
    # Xử lý phần Intro
    if parts[0].strip():
        parent_chunks.append({
            "title": "Giới thiệu / Mở đầu",
            "content": parts[0].strip(),
            "category": "general",
            **file_metadata
        })

    # Loop qua các phần còn lại
    for i in range(1, len(parts), 2):
        header = parts[i].strip()
        content = parts[i+1].strip() if i+1 < len(parts) else ""
        full_parent_content = f"{header}\n\n{content}"
        
        # Logic phân loại (Tagging)
        clean_title = re.sub(r'#+', '', header).strip()
        lower_title = clean_title.lower()
        
        category = "general"
        if any(x in lower_title for x in ["tiêu chuẩn", "đánh giá", "chấm điểm"]):
            category = "evaluation"
        elif any(x in lower_title for x in ["nhân sự", "chủ chốt", "cán bộ"]):
            category = "personnel"
        elif any(x in lower_title for x in ["tài chính", "doanh thu", "năng lực"]):
            category = "financial"
        elif any(x in lower_title for x in ["kỹ thuật", "giải pháp", "phạm vi"]):
            category = "technical"

        parent_chunks.append({
            "title": clean_title,
            "content": full_parent_content,
            "category": category,
            **file_metadata 
        })

    print(f"📦 [Ingest] Tìm thấy {len(parent_chunks)} chương lớn.")

    # Bước 2: Tách Child
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000, # Tăng nhẹ size
        chunk_overlap=200,
        separators=["\n\n", "\n", ". ", " ", ""]
    )

    final_chunks = []

    for parent in parent_chunks:
        def create_chunk_dict(content_text):
            return {
                "page_content": content_text,
                "metadata": {
                    "chapter_title": parent['title'],
                    "category": parent['category'],
                    "parent_content": parent['content'],
                    "source": parent.get('source_file'),
                    "year": parent.get('promulgation_year'),
                    "level": parent.get('legal_level'),
                    "priority": parent.get('legal_priority')
                }
            }

        if len(parent['content']) < 1200:
            final_chunks.append(create_chunk_dict(parent['content']))
        else:
            child_texts = child_splitter.split_text(parent['content'])
            for child_text in child_texts:
                final_chunks.append(create_chunk_dict(child_text))
            
    print(f"✅ [Ingest] Đã tạo ra {len(final_chunks)} vector search nodes.")
    return final_chunks