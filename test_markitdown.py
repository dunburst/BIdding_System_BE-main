import fitz  # PyMuPDF
from openai import OpenAI
import time

class CommandRServiceV2:
    def __init__(self, base_url, api_key="ollama", model="command-r-max"):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    def extract_with_chunking(self, file_path: str, prompt_request: str, pages_per_chunk=10):
        """
        Chiến thuật: Chia nhỏ để trị.
        Đọc 10 trang một -> Gửi AI -> Lưu kết quả -> Làm tiếp 10 trang sau.
        """
        doc = fitz.open(file_path)
        total_pages = len(doc)
        full_result = ""
        
        print(f"📂 File có {total_pages} trang. Sẽ chia làm {total_pages//pages_per_chunk + 1} lần gửi.")

        for start_page in range(0, total_pages, pages_per_chunk):
            end_page = min(start_page + pages_per_chunk, total_pages)
            
            # 1. Lấy text của cụm trang hiện tại
            chunk_text = ""
            for i in range(start_page, end_page):
                chunk_text += str(doc[i].get_text()) + "\n"
            
            print(f"\n🔄 Đang xử lý trang {start_page+1} đến {end_page} ({len(chunk_text)} ký tự)...")
            
            # 2. Gửi cho AI (Lúc này text ngắn, chạy rất nhanh, không lo timeout)
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "Bạn là thư ký bóc tách vật tư. Chỉ trích xuất dữ liệu, không nói chuyện."},
                        {"role": "user", "content": f"Dữ liệu thầu (Trang {start_page+1}-{end_page}):\n{chunk_text}\n\nYêu cầu: {prompt_request}"}
                    ],
                    temperature=0.1
                )
                result = response.choices[0].message.content
                print("✅ Xong cụm này.")
                full_result += f"\n--- KẾT QUẢ TỪ TRANG {start_page+1} ĐẾN {end_page} ---\n{result}\n"
                
            except Exception as e:
                print(f"❌ Lỗi cụm {start_page}-{end_page}: {e}")
        
        return full_result

# --- SỬ DỤNG ---
if __name__ == "__main__":
    # Dùng Ngrok hay Cloudflare đều được vì giờ file đã nhỏ
    service = CommandRServiceV2(base_url="https://butler-col-flows-www.trycloudflare.com/v1",)
    
    kq = service.extract_with_chunking(
        "Bien phap thi cong T3.pdf", 
        "Liệt kê danh mục vật tư thành dạng bảng (Tên, ĐVT, Khối lượng)."
    )
    
    # Ghi ra file text để xem cho dễ
    with open("ket_qua_boc_tach.txt", "w", encoding="utf-8") as f:
        f.write(kq)
    print("🎉 Đã hoàn thành! Kiểm tra file ket_qua_boc_tach.txt")