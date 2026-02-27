import os
import re
import chromadb
from chromadb.utils import embedding_functions
from typing import cast
from chromadb.api.types import EmbeddingFunction, Documents

# Cấu hình ChromaDB (Lưu trữ local tại thư mục chroma_db nằm ở root dự án)
# Lưu ý: Dùng đường dẫn tương đối để tránh lỗi path
# CHROMA_DB_PATH = os.path.join(os.getcwd(), "chroma_db")
PROJECT_ROOT = os.getcwd() 

# 2. Trỏ chính xác vào thư mục mong muốn
CHROMA_DB_PATH = os.path.join(
    PROJECT_ROOT, 
    "app", "infrastructure", "vectordb", "chroma_db"
)

# Khởi tạo Client
client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

# Dùng Embedding Model nhẹ, miễn phí
sentence_transformer_ef = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

# Tạo/Lấy Collection
collection = client.get_or_create_collection(
    name="construction_samples_chapters",
    # Thêm comment này vào cuối dòng để tắt lỗi đỏ
    embedding_function=sentence_transformer_ef  # type: ignore
)

def split_markdown_by_chapters(md_text: str) -> list[dict]:
    """
    Cắt Markdown thành các chunk dựa trên Header cấp 1 (#) hoặc từ khóa CHƯƠNG/PHẦN
    """
    chunks = []
    current_lines = []
    current_title = "PHẦN MỞ ĐẦU / GIỚI THIỆU"
    
    # Regex bắt dòng tiêu đề:
    # Bắt: "# CHƯƠNG I", "## PHẦN 2", "**CHƯƠNG III**"...
    chapter_pattern = re.compile(r'^(#+\s+)?(\**)?(CHƯƠNG|PHẦN|MỤC)\s+[0-9IVX]+.*', re.IGNORECASE)

    lines = md_text.split('\n')
    
    for line in lines:
        line_stripped = line.strip()
        
        if chapter_pattern.match(line_stripped):
            # Lưu chunk cũ nếu có nội dung
            if current_lines:
                full_content = "\n".join(current_lines).strip()
                if len(full_content) > 50:
                    chunks.append({
                        "title": current_title,
                        "content": full_content
                    })
            
            # Reset chunk mới
            current_title = line_stripped.replace('#', '').replace('*', '').strip()
            current_lines = [line]
        else:
            current_lines.append(line)
            
    # Lưu chunk cuối cùng
    if current_lines:
        full_content = "\n".join(current_lines).strip()
        if len(full_content) > 50:
            chunks.append({
                "title": current_title,
                "content": full_content
            })
        
    return chunks

def ingest_markdown_content(file_name: str, md_content: str):
    """
    Hàm nhận nội dung Markdown và lưu vào Vector DB
    """
    print(f"✂️ Đang phân tích cấu trúc chương của: {file_name}...")
    
    chunks = split_markdown_by_chapters(md_content)
    
    if not chunks:
        print("⚠️ Không tìm thấy chương nào. File có thể quá ngắn hoặc sai định dạng.")
        return

    print(f"   -> Tìm thấy {len(chunks)} phần/chương.")

    ids = []
    metadatas = []
    documents = []

    for i, item in enumerate(chunks):
        chunk_id = f"{file_name}_chap_{i}"
        
        ids.append(chunk_id)
        documents.append(item['content'])
        metadatas.append({
            "source": file_name, 
            "chapter_title": item['title']
        })
        
        print(f"   + [Lưu Chunk {i}]: {item['title'][:60]}... ({len(item['content'])} ký tự)")

    print(f"💾 Đang lưu vào Vector DB tại: {CHROMA_DB_PATH}...")
    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas
    )
    print("✅ ĐÃ LƯU THÀNH CÔNG! Dữ liệu đã sẵn sàng để AI dùng.")

def retrieve_chapter_sample(query: str) -> str:
    """
    Hàm tìm kiếm (Dùng sau này)
    """
    results = collection.query(
        query_texts=[query],
        n_results=1
    )
    if results['documents'] and results['documents'][0]:
        return results['documents'][0][0]
    return ""