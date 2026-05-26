import os
# Import service LlamaParse "xịn" bạn đã test
from app.integrations.ai.provider.llama_service import llama_service 
from app.integrations.ai.provider.gemini_agent import gemini_agent 
# Import hàm tìm kiếm chương mẫu từ Vector DB
from app.integrations.ai.data_processing.embedding import retrieve_chapter_sample

def convert_hsmt_to_markdown(file_paths: list[str]) -> str:
    """
    Đọc các file HSMT đầu vào và chuyển sang Markdown bằng LlamaParse
    để AI hiểu rõ cấu trúc bảng biểu.
    """
    combined_md = ""
    print(f"📂 Đang xử lý {len(file_paths)} file đầu vào...")
    
    for path in file_paths:
        if os.path.exists(path):
            try:
                print(f"   -> Đang đọc file: {os.path.basename(path)}")
                # Gọi LlamaParse thay vì pymupdf4llm
                md_content = llama_service.parse_pdf_to_markdown(path)
                
                if md_content:
                    filename = os.path.basename(path)
                    # Đánh dấu rõ ràng đầu/đuôi file để AI biết
                    combined_md += f"\n\n{'='*30}\nNỘI DUNG TÀI LIỆU ĐẦU VÀO: {filename}\n{'='*30}\n{md_content}\n"
                else:
                    print(f"⚠️ Cảnh báo: File {path} không trích xuất được nội dung.")
            except Exception as e:
                print(f"❌ Lỗi đọc file {path}: {e}")
        else:
            print(f"❌ Không tìm thấy file: {path}")
            
    return combined_md

def generate_draft_section(section_name: str, task_description: str, input_files: list[str]) -> str:
    """
    Hàm lõi: Kết hợp Mẫu (RAG) + Dữ liệu thật (HSMT) -> AI viết bài
    """
    
    # 1. Chuẩn bị dữ liệu đầu vào (FACTS)
    print("1️⃣ Đang chuẩn bị dữ liệu đầu vào từ HSMT...")
    hsmt_context = convert_hsmt_to_markdown(input_files)
    
    if not hsmt_context:
        return "❌ Lỗi: Không đọc được nội dung từ các file HSMT đầu vào."

    # 2. Lấy mẫu (STYLE & STRUCTURE)
    # Query bằng chính tên chương để lấy đúng chương đó trong file T3
    print(f"2️⃣ Đang tìm chương mẫu tương ứng với: '{section_name}' trong Vector DB...")
    sample_context = retrieve_chapter_sample(query=section_name)
    
    if not sample_context:
        print(f"⚠️ Cảnh báo: Không tìm thấy mẫu cho '{section_name}'. AI sẽ tự viết dựa trên cấu trúc chuẩn.")
        sample_context = "(Không có mẫu cụ thể, hãy viết theo chuẩn xây dựng Việt Nam)"
    else:
        print("✅ Đã tìm thấy chương mẫu phù hợp!")

    # 3. Xây dựng Prompt
    system_instruction = f"""
    Bạn là Kỹ sư trưởng chuyên lập Hồ sơ dự thầu (Biện pháp thi công, Thuyết minh kỹ thuật).
    Nhiệm vụ: Soạn thảo **{section_name}**.
    
    --------------------------------------------------------
    PHẦN 1: MẪU TRÌNH BÀY (TEMPLATE TỪ DỰ ÁN CŨ)
    (Hãy học cấu trúc, các đề mục, bảng biểu và văn phong từ mẫu này. KHÔNG copy dữ liệu cũ như tên dự án cũ, địa điểm cũ...)
    
    {sample_context}
    --------------------------------------------------------
    
    PHẦN 2: DỮ LIỆU ĐẦU VÀO (FACTS TỪ DỰ ÁN MỚI)
    (Đây là thông tin SỰ THẬT. Hãy trích xuất Tên dự án, Địa điểm, Tiêu chuẩn, Thông số kỹ thuật TỪ ĐÂY để điền vào bài làm)
    
    {hsmt_context}
    --------------------------------------------------------
    
    YÊU CẦU CỤ THỂ CỦA NGƯỜI DÙNG:
    "{task_description}"
    
    YÊU CẦU ĐẦU RA:
    1. Trả về định dạng **HTML** (thẻ h2, h3, p, ul, table...).
    2. Giữ nguyên cấu trúc của "MẪU TRÌNH BÀY" nhưng thay thế toàn bộ dữ liệu (Tên dự án, địa điểm, thông số kỹ thuật...) bằng thông tin từ "DỮ LIỆU ĐẦU VÀO".
    3. Nếu "DỮ LIỆU ĐẦU VÀO" thiếu thông tin nào đó có trong mẫu, hãy để placeholder: <span style="background:yellow; font-weight:bold">[Thiếu tin: ...]</span>.
    4. Chỉ trả về nội dung chính, không cần lời dẫn như "Dưới đây là bản thảo...".
    """
    
    # 4. Gọi Gemini
    print("3️⃣ Đang gửi toàn bộ ngữ cảnh cho Gemini xử lý...")
    try:
        response = gemini_agent.chat(system_instruction)
        # Clean up markdown block nếu AI trả về ```html
        clean_html = response.replace("```html", "").replace("```", "").strip()
        return clean_html
    except Exception as e:
        return f"❌ Lỗi khi gọi AI: {str(e)}"