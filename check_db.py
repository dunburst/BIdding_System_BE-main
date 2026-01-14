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
    # export_collection_to_csv("current_requirements")
    # export_collection_to_csv("bidding_docs")
    export_collection_to_csv("legal_docs")
    
    print("\n🎉 Hoàn tất. Hãy mở các file .csv vừa tạo bằng Excel để xem.")