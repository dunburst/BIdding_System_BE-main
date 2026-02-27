# services/drafting_bot.py

from fastapi import Depends
from app.integrations.ai.data_processing.chroma_service import ChromaService, get_chroma_service
from openai import OpenAI
import os

class DraftingBot:
    # 1. Truyền chroma_service vào __init__
    def __init__(self, chroma_service: ChromaService):
        self.chroma = chroma_service
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    def draft_with_rag(self, topic: str):
        """
        Viết bài KHÔNG CẦN truyền full text requirement vào hàm này nữa.
        Bot sẽ tự tìm trong Database.
        """
        
        # --- BƯỚC 1: Tìm kiếm YÊU CẦU ĐẦU VÀO (Input Data) ---
        print(f"🔎 Đang tìm thông tin trong HSMT liên quan đến: {topic}...")
        req_results = self.chroma.query_requirements(query_text=topic, n_results=5)
        
        req_context = ""
        if req_results and req_results['documents'] and req_results['documents'][0]:
            req_context = "\n---\n".join(req_results['documents'][0])
            print(f"✅ Tìm thấy {len(req_results['documents'][0])} đoạn yêu cầu liên quan.")
        else:
            req_context = "Không tìm thấy thông tin cụ thể trong tài liệu. Hãy viết dựa trên kiến thức chuyên môn chung."

        # --- BƯỚC 2: Tìm kiếm MẪU VĂN PHONG (Style) ---
        print(f"🎨 Đang tìm mẫu văn phong tham khảo...")
        style_results = self.chroma.query_styles(query_text=topic, n_results=2)
        
        style_context = ""
        if style_results and style_results['documents'] and style_results['documents'][0]:
            style_context = "\n---\n".join(style_results['documents'][0])
        else:
            style_context = "Viết theo văn phong Kỹ thuật xây dựng chuyên nghiệp, gãy gọn."

        # --- BƯỚC 3: Xây dựng Prompt ---
        system_prompt = """
        Bạn là Chuyên gia Đấu thầu chuyên nghiệp. 
        Nhiệm vụ: Viết nội dung Hồ sơ dự thầu (HSDT) dựa trên dữ liệu cung cấp.
        
        QUY TẮC:
        1. SỰ THẬT: Chỉ sử dụng thông số kỹ thuật từ phần 'THÔNG TIN YÊU CẦU'.
        2. HÌNH THỨC: Học cách diễn đạt từ phần 'TÀI LIỆU MẪU'.
        3. Định dạng Markdown đẹp.
        """

        user_prompt = f"""
        CHỦ ĐỀ CẦN VIẾT: "{topic}"

        === 1. DỮ LIỆU ĐẦU VÀO TỪ HSMT (Bắt buộc tuân thủ) ===
        {req_context}
        ======================================================

        === 2. VĂN PHONG THAM KHẢO (Cách viết) ===
        {style_context}
        ======================================================

        Hãy viết bài chi tiết cho chủ đề trên:
        """

        # --- BƯỚC 4: Gọi AI ---
        response = self.client.chat.completions.create(
            model="gpt-4o-mini", 
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.4
        )

        return response.choices[0].message.content

# --- THÊM Provider ---
def get_drafting_bot(
    chroma: ChromaService = Depends(get_chroma_service)
) -> DraftingBot:
    return DraftingBot(chroma)