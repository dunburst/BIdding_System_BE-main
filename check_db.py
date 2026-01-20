import sys
import os
import base64
import time

# Thêm đường dẫn để import services
sys.path.append(os.getcwd())

from services.visual_retrieval_service import get_visual_service

def save_debug_images():
    print("\n" + "="*50)
    print("📸 DEBUG: TÌM VÀ LƯU ẢNH RA FILE")
    print("="*50)

    # 1. Khởi tạo
    visual = get_visual_service()
    
    # 2. Tạo thư mục để chứa ảnh xuất ra
    output_dir = "debug_images_output"
    os.makedirs(output_dir, exist_ok=True)
    print(f"📂 Các ảnh tìm thấy sẽ được lưu vào thư mục: ./{output_dir}/")

    # 3. Thực hiện tìm kiếm
    # Bạn có thể đổi từ khóa khác nếu muốn
    query = "sơ đồ thi công" 
    print(f"\n🔍 Đang tìm kiếm với từ khóa: '{query}'...")
    
    try:
        # Lấy top 3 ảnh giống nhất
        results = visual.search_visuals(query, top_k=10)
        
        if not results:
            print("❌ Không tìm thấy ảnh nào.")
            return

        print(f"✅ Tìm thấy {len(results)} kết quả.\n")

        for i, res in enumerate(results):
            print(f"--- 🖼️ KẾT QUẢ #{i+1} ---")
            
            # A. In Metadata gốc để debug
            meta = res.get('metadata', {})
            print(f"   🔹 Metadata Gốc (Raw): {meta}") 
            # (Để xem nó lưu key tên là 'source' hay 'file_name' hay gì khác)

            score = round(res['score'], 2)
            print(f"   🔹 Độ khớp (Score): {score}")

            # B. Xử lý và Lưu ảnh
            base64_str = res.get('base64', '')
            if base64_str:
                try:
                    # Giải mã Base64 thành bytes
                    img_data = base64.b64decode(base64_str)
                    
                    # Đặt tên file
                    filename = f"result_{i+1}_score_{score}.jpg"
                    filepath = os.path.join(output_dir, filename)
                    
                    # Ghi ra đĩa
                    with open(filepath, "wb") as f:
                        f.write(img_data)
                    
                    print(f"   💾 ĐÃ LƯU ẢNH TẠI: {filepath}")
                    print("   👉 Bạn hãy vào thư mục trên để mở ảnh xem.")
                except Exception as img_err:
                    print(f"   ❌ Lỗi khi lưu ảnh: {img_err}")
            else:
                print("   ⚠️ Không có dữ liệu Base64.")
            
            print("")

    except Exception as e:
        print(f"❌ Lỗi hệ thống: {e}")

if __name__ == "__main__":
    save_debug_images()