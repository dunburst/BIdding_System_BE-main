from app.integrations.ai.provider.gemini_agent import gemini_agent # Import Agent có sẵn của bạn

def process_drafting_with_ai(prompt: str, current_html: str, context: str = "") -> str:
    """
    Hàm xử lý gọi Gemini để hỗ trợ soạn thảo
    """
    
    # Prompt kỹ thuật (System Prompt) ép AI trả về HTML chuẩn
    system_instruction = f"""
    Bạn là trợ lý soạn thảo tài liệu thầu xây dựng chuyên nghiệp.
    
    NGỮ CẢNH DỰ ÁN: {context}
    
    NỘI DUNG VĂN BẢN HIỆN TẠI (HTML):
    {current_html}
    
    YÊU CẦU NGƯỜI DÙNG: "{prompt}"
    
    CHỈ DẪN QUAN TRỌNG:
    1. Hãy sửa đổi hoặc viết tiếp dựa trên 'NỘI DUNG VĂN BẢN HIỆN TẠI'.
    2. Output bắt buộc phải là định dạng **HTML Tags** (ví dụ: <p>, <strong>, <ul>, <table>).
    3. KHÔNG trả về markdown block (như ```html). Chỉ trả về chuỗi HTML thuần.
    4. Giữ nguyên format bảng biểu/style của nội dung cũ nếu không được yêu cầu sửa.
    """
    
    try:
        # Gọi Gemini (Giả định gemini_agent có hàm chat hoặc generate_content)
        # Nếu class của bạn dùng hàm khác, hãy sửa dòng dưới đây cho khớp
        response = gemini_agent.chat(system_instruction) 
        
        # Clean up phòng khi AI vẫn trả về markdown
        clean_html = response.replace("```html", "").replace("```", "").strip()
        return clean_html
        
    except Exception as e:
        print(f"AI Error: {str(e)}")
        return "<p style='color:red'>Lỗi khi gọi AI. Vui lòng thử lại.</p>"