# import sys
# import os
# import base64
# import time

# # Thêm đường dẫn để import services
# sys.path.append(os.getcwd())

# from services.visual_retrieval_service import get_visual_service

# def save_debug_images():
#     print("\n" + "="*50)
#     print("📸 DEBUG: TÌM VÀ LƯU ẢNH RA FILE")
#     print("="*50)

#     # 1. Khởi tạo
#     visual = get_visual_service()
    
#     # 2. Tạo thư mục để chứa ảnh xuất ra
#     output_dir = "debug_images_output"
#     os.makedirs(output_dir, exist_ok=True)
#     print(f"📂 Các ảnh tìm thấy sẽ được lưu vào thư mục: ./{output_dir}/")

#     # 3. Thực hiện tìm kiếm
#     # Bạn có thể đổi từ khóa khác nếu muốn
#     query = "sơ đồ thi công" 
#     print(f"\n🔍 Đang tìm kiếm với từ khóa: '{query}'...")
    
#     try:
#         # Lấy top 3 ảnh giống nhất
#         results = visual.search_visuals(query, top_k=1000)
        
#         if not results:
#             print("❌ Không tìm thấy ảnh nào.")
#             return

#         print(f"✅ Tìm thấy {len(results)} kết quả.\n")

#         for i, res in enumerate(results):
#             print(f"--- 🖼️ KẾT QUẢ #{i+1} ---")
            
#             # A. In Metadata gốc để debug
#             meta = res.get('metadata', {})
#             print(f"   🔹 Metadata Gốc (Raw): {meta}") 
#             # (Để xem nó lưu key tên là 'source' hay 'file_name' hay gì khác)

#             score = round(res['score'], 2)
#             print(f"   🔹 Độ khớp (Score): {score}")

#             # B. Xử lý và Lưu ảnh
#             base64_str = res.get('base64', '')
#             if base64_str:
#                 try:
#                     # Giải mã Base64 thành bytes
#                     img_data = base64.b64decode(base64_str)
                    
#                     # Đặt tên file
#                     filename = f"result_{i+1}_score_{score}.jpg"
#                     filepath = os.path.join(output_dir, filename)
                    
#                     # Ghi ra đĩa
#                     with open(filepath, "wb") as f:
#                         f.write(img_data)
                    
#                     print(f"   💾 ĐÃ LƯU ẢNH TẠI: {filepath}")
#                     print("   👉 Bạn hãy vào thư mục trên để mở ảnh xem.")
#                 except Exception as img_err:
#                     print(f"   ❌ Lỗi khi lưu ảnh: {img_err}")
#             else:
#                 print("   ⚠️ Không có dữ liệu Base64.")
            
#             print("")

#     except Exception as e:
#         print(f"❌ Lỗi hệ thống: {e}")

# if __name__ == "__main__":
#     print("🚀 BẮT ĐẦU XUẤT DỮ LIỆU RA EXCEL/CSV...\n")
    
#     print("\n🎉 Hoàn tất. Hãy mở các file .csv vừa tạo bằng Excel để xem.")
#     save_debug_images()
import chromadb
import os
import csv
import sys

# [FIX] Thay sys.maxsize bằng số cụ thể (Max 32-bit integer) để tránh lỗi trên Windows
# 2147483647 là số lượng ký tự tối đa cho 1 ô Excel/CSV (khoảng 2GB text)
csv.field_size_limit(2147483647)

DB_PATH = "./chroma_db"

if not os.path.exists(DB_PATH):
    print(f"❌ Lỗi: Thư mục '{DB_PATH}' không tồn tại.")
    exit()

client = chromadb.PersistentClient(path=DB_PATH)

def export_collection_to_csv(collection_name):
    print(f"⏳ Đang tải dữ liệu từ: {collection_name}...")
    
    try:
        collection = client.get_collection(name=collection_name)
        count = collection.count()
        
        if count == 0:
            print(f"⚠️ Collection {collection_name} trống. Bỏ qua.")
            return

        # Lấy TOÀN BỘ dữ liệu
        # Lưu ý: include=['documents', 'metadatas'] để lấy nội dung
        data = collection.get(include=['documents', 'metadatas'])
        
        ids = data.get('ids', [])
        metadatas = data.get('metadatas', [])
        documents = data.get('documents', [])
        
        # Tên file xuất ra
        filename = f"export_{collection_name}.csv"
        
        print(f"💾 Đang ghi {len(ids)} dòng vào file '{filename}'...")

        # encoding='utf-8-sig' để Excel hiển thị đúng tiếng Việt
        with open(filename, mode='w', newline='', encoding='utf-8-sig') as file:
            writer = csv.writer(file)
            # Ghi tiêu đề cột
            writer.writerow(['ID', 'Source File', 'Chapter Title', 'Category', 'Content Length', 'Full Content'])
            
            for i in range(len(ids)):
                doc_id = ids[i]
                meta = metadatas[i] if metadatas else {}
                content = documents[i] if documents else ""
                
                if meta is None: meta = {}
                if content is None: content = ""
                
                writer.writerow([
                    doc_id,
                    meta.get('source', 'N/A'),
                    meta.get('chapter', 'N/A'),
                    meta.get('category', 'general'),
                    len(content),
                    content # Ghi toàn bộ nội dung
                ])
                
        print(f"✅ XONG! Đã xuất file: {filename}")
        print("-" * 40)

    except Exception as e:
        print(f"❌ Lỗi khi xuất {collection_name}: {e}")

if __name__ == "__main__":
    print("🚀 BẮT ĐẦU XUẤT DỮ LIỆU RA EXCEL/CSV...\n")
    
    # Xuất cả 2 kho
    export_collection_to_csv("current_requirements")
    export_collection_to_csv("bidding_docs")
    export_collection_to_csv("legal_docs")
    
    print("\n🎉 Hoàn tất. Hãy mở các file .csv vừa tạo bằng Excel để xem.")