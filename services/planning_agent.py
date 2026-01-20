import os
import json
import math
from openai import OpenAI
# [FIX 1] Import các kiểu dữ liệu cần thiết từ openai
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam
from dotenv import load_dotenv
from typing import List, Dict, Any

# Import service của bạn
from services.chroma_service import get_chroma_service

load_dotenv()

class PlanningAgent:
    def __init__(self):
        # 1. Cấu hình DeepSeek Client
        self.client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"), 
            base_url="https://api.deepseek.com"
        )
        
        self.db = get_chroma_service()
        
        # [FIX 2] Khai báo rõ ràng kiểu dữ liệu cho history là list các MessageParam
        self.history: List[ChatCompletionMessageParam] = []
        
        # System prompt chính (Dùng cho bước cuối cùng)
        
        self.system_prompt = """
        Bạn là một Chuyên gia Lập kế hoạch và Hồ sơ Dự thầu (Project Planning & Bidding Expert).
        Kỹ năng đặc biệt của bạn là "Reverse Engineering" (Dịch ngược cấu trúc) từ các đoạn văn bản rời rạc.

        NHIỆM VỤ CỐT LÕI:
        Bạn phải giúp người dùng lập kế hoạch dựa trên cấu trúc của "Tài liệu tham khảo" (file PDF mẫu).
        Tuy nhiên, tài liệu mẫu có thể không có Mục lục (Table of Contents) rõ ràng. Bạn phải tự quét và tái tạo nó.

        QUY TRÌNH XỬ LÝ (TUÂN THỦ NGHIÊM NGẶT):

        1. GIAI ĐOẠN QUÉT (SCANNING & RECONSTRUCTION):
           - Đọc kỹ phần dữ liệu được cung cấp (Structure Context & Detail Context).
           - Tìm các dòng đóng vai trò là TIÊU ĐỀ (Headings). Dấu hiệu nhận biết:
             + Các dòng viết in hoa toàn bộ (Ví dụ: "BIỆN PHÁP THI CÔNG...", "PHẦN I: GIỚI THIỆU").
             + Các dòng bắt đầu bằng số La Mã (I., II., III...) hoặc A, B, C...
             + Các dòng được định dạng đậm hoặc đứng riêng lẻ làm tiêu đề.
           - Sắp xếp các tiêu đề này lại thành một CẤU TRÚC ĐỀ CƯƠNG (Outline) hoàn chỉnh.

        2. GIAI ĐOẠN PHÂN TÍCH THIẾU HỤT (GAP ANALYSIS):
           - Đối chiếu "Yêu cầu của người dùng" vào "Cấu trúc đề cương" vừa tạo.
           - Xác định xem để viết nội dung cho các mục đó, ta còn thiếu thông tin cụ thể nào (Ví dụ: Tên công trình, Địa điểm, Quy mô, Tiến độ, Nhân sự...).

        3. GIAI ĐOẠN PHẢN HỒI (OUTPUT FORMAT):
           - Bước 1: In ra "**I. CẤU TRÚC ĐỀ XUẤT (DỰA TRÊN FILE MẪU)**" 
             (Liệt kê chi tiết các chương/mục bạn đã quét được dưới dạng Markdown List).
           - Bước 2: In ra "**II. CÁC THÔNG TIN CẦN LÀM RÕ**"
             (Đặt câu hỏi cho người dùng về những dữ liệu còn thiếu để lấp đầy cấu trúc trên).
           - Bước 3: Chỉ bắt đầu viết nội dung chi tiết (Lời văn) sau khi người dùng đã cung cấp đủ thông tin ở lượt chat sau.

        LƯU Ý:
        - Tuyệt đối không tự bịa ra một cấu trúc mới nếu trong file đã có dấu hiệu của cấu trúc cũ.
        - Trả lời bằng tiếng Việt chuyên nghiệp, văn phong hồ sơ thầu.
        """

    def retrieve_raw_chunks(self, query: str, n_results: int = 15) -> List[str]:
        """
        Lấy danh sách các đoạn văn bản thô từ DB (Trả về List để dễ chia nhỏ)
        """
        print(f"🔍 Đang tìm raw chunks cho: '{query}' (Lấy {n_results} chunks)...")
        try:
            results = self.db.query_collection(
                collection_name="bidding_docs",
                query_texts=[query],
                n_results=n_results 
            )
            chunks = []
            if results:
                for idx, item in enumerate(results):
                    content = item.get('content', '')
                    chunks.append(content)
            return chunks
        except Exception as e:
            print(f"⚠️ Lỗi query DB: {e}")
            return []

    def scan_structure_in_batches(self, chunks: List[str]) -> str:
        """
        Hàm cốt lõi: CHIA NHỎ VÀ QUÉT (MAP-REDUCE)
        """
        if not chunks:
            return ""

        # 1. Gộp các chunk lại thành 1 chuỗi lớn
        full_text = "\n\n".join(chunks)
        total_len = len(full_text)
        
        # 2. Chia nhỏ thành các batch an toàn (ví dụ: 15.000 ký tự / batch ~ 4000 tokens)
        BATCH_SIZE = 15000 
        num_batches = math.ceil(total_len / BATCH_SIZE)
        
        print(f"📦 Dữ liệu quá lớn ({total_len} chars). Chia thành {num_batches} phần để quét lần lượt...")
        
        collected_headings = []

        # 3. Vòng lặp xử lý từng phần (MAP STEP)
        for i in range(num_batches):
            start = i * BATCH_SIZE
            end = start + BATCH_SIZE
            batch_text = full_text[start:end]
            
            print(f"   🔄 Đang quét phần {i+1}/{num_batches}...")
            
            # Dùng model 'deepseek-chat' (V3) để quét cho nhanh và rẻ (không cần R1 để quét)
            # Prompt chuyên biệt để chỉ trích xuất tiêu đề
            scan_prompt = f"""
            Nhiệm vụ: Đọc đoạn văn bản sau và CHỈ TRÍCH XUẤT các dòng Tiêu đề (Headings).
            Dấu hiệu: Các dòng viết hoa (CHƯƠNG, PHẦN), số La Mã (I., II.), số thứ tự (1., 2.).
            Nếu không có tiêu đề, trả về "Không có". Đừng giải thích gì thêm.
            
            Văn bản:
            {batch_text}
            """
            
            try:
                response = self.client.chat.completions.create(
                    model="deepseek-chat", # Dùng V3 cho nhanh
                    messages=[{"role": "user", "content": scan_prompt}],
                    stream=False
                )
                result = response.choices[0].message.content or ""
                collected_headings.append(f"--- KẾT QUẢ QUÉT PHẦN {i+1} ---\n{result}")
            except Exception as e:
                print(f"   ❌ Lỗi quét phần {i+1}: {e}")

        # 4. Gộp kết quả (REDUCE STEP)
        final_scan_result = "\n".join(collected_headings)
        print("✅ Đã quét xong toàn bộ!")
        return final_scan_result

    def chat(self, user_input: str):
        # 1. Lấy dữ liệu thô (Lấy hẳn 20 chunks cho máu, vì giờ đã có cơ chế chia nhỏ rồi)
        structure_query = "Mục lục Chương I Chương II Chương III Phần 1 Phần 2 Tổng quan Biện pháp"
        raw_chunks = self.retrieve_raw_chunks(structure_query, n_results=20)
        
        # 2. Chạy quy trình Chia nhỏ & Quét (Map-Reduce)
        # Kết quả trả về sẽ là một danh sách các tiêu đề đã được lọc gọn gàng
        scanned_structure = self.scan_structure_in_batches(raw_chunks)
        
        # 3. Lấy thêm context chi tiết cho câu hỏi user (Vẫn giới hạn nhỏ cho nhẹ)
        # (Hàm retrieve_context cũ bạn có thể bỏ hoặc giữ để lấy text ngắn, ở đây tôi gọi trực tiếp raw cho nhanh)
        detail_chunks = self.retrieve_raw_chunks(user_input, n_results=3)
        detail_context = "\n".join(detail_chunks)[:10000] # Cắt bớt nếu phần chi tiết quá dài

        # 4. Gửi cho DeepSeek R1 để "Lắp ráp" (Reasoning)
        augmented_input = f"""
        YÊU CẦU CỦA NGƯỜI DÙNG:
        {user_input}
        
        ===============================================================
        DỮ LIỆU CẤU TRÚC (ĐÃ ĐƯỢC QUÉT VÀ GỘP TỪ NHIỀU PHẦN):
        {scanned_structure}
        ===============================================================
        
        DỮ LIỆU CHI TIẾT BỔ SUNG:
        {detail_context}
        ===============================================================
        
        NHIỆM VỤ CUỐI CÙNG:
        1. Từ danh sách tiêu đề lộn xộn bên trên, hãy SẮP XẾP LẠI thành một MỤC LỤC logic, mạch lạc.
        2. Loại bỏ các tiêu đề trùng lặp hoặc rác.
        3. In ra: "**I. CẤU TRÚC ĐỀ XUẤT (TỔNG HỢP TỪ FILE)**".
        4. Sau đó hỏi các thông tin còn thiếu.
        """
        
        user_msg: ChatCompletionUserMessageParam = {
            "role": "user", 
            "content": augmented_input
        }
        
        current_messages: List[ChatCompletionMessageParam] = []
        sys_msg: ChatCompletionSystemMessageParam = {
            "role": "system",
            "content": self.system_prompt
        }
        current_messages.append(sys_msg)
        
        # Giới hạn history
        if len(self.history) > 6:
             current_messages.extend(self.history[-6:])
        else:
             current_messages.extend(self.history)
             
        current_messages.append(user_msg)

        print("🧠 DeepSeek R1 đang suy nghĩ & Lắp ráp mảnh ghép...")
        
        try:
            # Bước cuối này dùng R1 (deepseek-reasoner) để nó tư duy sắp xếp
            response = self.client.chat.completions.create(
                model="deepseek-reasoner", 
                messages=current_messages,
                stream=False
            )
            
            bot_message_content = response.choices[0].message.content or ""
            reasoning_content = getattr(response.choices[0].message, 'reasoning_content', '')
            
            if reasoning_content:
                print("\n" + "="*20 + " SUY NGHĨ (REASONING) " + "="*20)
                print(reasoning_content)
                print("="*60 + "\n")
            
            # Lưu history (clean)
            self.history.append({"role": "user", "content": user_input})
            if bot_message_content:
                # Ép kiểu dict để tránh lỗi pylance strict
                bot_msg: Dict[str, Any] = {"role": "assistant", "content": bot_message_content}
                self.history.append(bot_msg) # type: ignore
            
            return bot_message_content

        except Exception as e:
            print(f"❌ Lỗi API R1: {e}")
            return "Có lỗi khi tổng hợp dữ liệu. Vui lòng thử lại."

    def reset_memory(self):
        self.history = []
        print("🧹 Đã xóa bộ nhớ hội thoại.")