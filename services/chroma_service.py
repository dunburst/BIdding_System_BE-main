import chromadb
from chromadb.utils import embedding_functions
import os
from dotenv import load_dotenv
import uuid
import shutil
from functools import lru_cache # <--- Import cái này

load_dotenv()

class ChromaService:
    def __init__(self):
        # Đường dẫn lưu DB
        self.db_path = "./chroma_db"
        self.client = chromadb.PersistentClient(path=self.db_path)
        
        # # [CHANGE] Sử dụng SentenceTransformer (Local - Free)
        # # Yêu cầu cài đặt: pip install sentence-transformers
        # print("📥 Đang tải/load model Embedding (all-MiniLM-L6-v2)...")
        # self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        #     model_name="all-MiniLM-L6-v2"
        # )
        # --- CẤU HÌNH OPENAI EMBEDDING (text-embedding-3-large) ---
        api_key = os.getenv("OPENAI_API_KEY")
        # [FIX] Lấy thêm endpoint/domain từ biến môi trường
        # Nếu bạn không set biến này, nó sẽ fallback về None (dùng mặc định của OpenAI)
        api_base = os.getenv("OPENAI_API_BASE")  # Ví dụ: "https://your-custom-domain.com/v1"
        if not api_key:
            print("⚠️ Cảnh báo: Thiếu OPENAI_API_KEY. Vector Search sẽ lỗi.")

        self.embedding_fn = embedding_functions.OpenAIEmbeddingFunction(
            api_key=api_key,
            model_name="text-embedding-3-large"
            , api_base=api_base
        )

        # 3. Tạo Collection: VĂN PHONG MẪU
        self.style_collection = self.client.get_or_create_collection(
            name="bidding_docs",
            embedding_function=self.embedding_fn # type: ignore
        )

        # 4. Tạo Collection: YÊU CẦU ĐẦU VÀO
        self.req_collection = self.client.get_or_create_collection(
            name="current_requirements",
            embedding_function=self.embedding_fn # type: ignore
        )
        # Tạo Collection
        self.legal_collection = self.client.get_or_create_collection(
            name="legal_docs", 
            embedding_function=self.embedding_fn # type: ignore
        )

    # --- HÀM HỖ TRỢ CHUNG ---
    def _save_to_collection(self, collection, chunks, source_filename):
        """
        Lưu chunks vào collection với cơ chế cắt nhỏ (Safe Split)
        phù hợp với giới hạn của all-MiniLM-L6-v2.
        """
        if not chunks: return

        ids, documents, metadatas = [], [], []
        
        # [QUAN TRỌNG] Model all-MiniLM-L6-v2 chỉ nhận max ~256 tokens.
        # Ta để giới hạn an toàn là 1000 ký tự tiếng Việt. 
        # Nếu để cao hơn, phần đuôi văn bản sẽ bị model lờ đi (ignore).
        SAFE_CHAR_LIMIT = 1000 

        for chunk in chunks:
            raw_content = chunk.get('full_content') or chunk.get('content') or ""
            title = chunk.get('chapter_title') or "No Title"
            category = chunk.get('category', 'general')

            content_len = len(raw_content)
            
            if content_len > SAFE_CHAR_LIMIT:
                # Nếu dài quá, cắt nhỏ tiếp
                # print(f"⚠️ Chunk '{title}' dài {content_len} ký tự -> Cắt nhỏ để vừa với MiniLM.")
                
                for i in range(0, content_len, SAFE_CHAR_LIMIT):
                    sub_text = raw_content[i : i + SAFE_CHAR_LIMIT]
                    part_num = (i // SAFE_CHAR_LIMIT) + 1
                    sub_title = f"{title} (Part {part_num})"
                    
                    ids.append(str(uuid.uuid4()))
                    documents.append(sub_text)
                    metadatas.append({
                        "source": source_filename,
                        "chapter": sub_title,
                        "category": category
                    })
            else:
                ids.append(str(uuid.uuid4()))
                documents.append(raw_content)
                metadatas.append({
                    "source": source_filename,
                    "chapter": title,
                    "category": category
                })

        # Batch insert
        BATCH_SIZE = 20
        total_docs = len(ids)
        
        try:
            for i in range(0, total_docs, BATCH_SIZE):
                end = i + BATCH_SIZE
                collection.add(
                    ids=ids[i:end],
                    documents=documents[i:end],
                    metadatas=metadatas[i:end]
                )
            print(f"✅ Đã lưu {total_docs} vectors vào Collection: {collection.name}")
        except Exception as e:
            print(f"❌ Lỗi khi lưu vào ChromaDB: {e}")
            
    def save_hierarchical_chunks(self, chunks, source_filename):
        """
        Lưu chunks đã xử lý theo mô hình Parent-Child
        """
        ids = []
        documents = [] # Child content
        metadatas = []
        
        for chunk in chunks:
            ids.append(str(uuid.uuid4()))
            documents.append(chunk['page_content'])
            metadatas.append(chunk['metadata']) # Chứa parent_content
            
        # Batch insert (Tăng tốc độ)
        BATCH_SIZE = 50
        total = len(ids)
        
        try:
            for i in range(0, total, BATCH_SIZE):
                end = i + BATCH_SIZE
                self.legal_collection.add(
                    ids=ids[i:end],
                    documents=documents[i:end],
                    metadatas=metadatas[i:end]
                )
            print(f"💾 Đã lưu {total} vectors vào DB.")
        except Exception as e:
            print(f"❌ Lỗi lưu Chroma: {e}")

    # --- CÁC HÀM GỌI TỪ BÊN NGOÀI ---

    def save_styles(self, chunks, source_filename):
        self._save_to_collection(self.style_collection, chunks, source_filename)

    def save_requirements(self, chunks, source_filename):
        self._save_to_collection(self.req_collection, chunks, source_filename)
        
    def save_chunks_to_db(self, chunks, source_filename):
        """Alias tương thích ngược"""
        self.save_styles(chunks, source_filename)

    def query_styles(self, query_text, n_results=2):
        return self.style_collection.query(query_texts=[query_text], n_results=n_results)

    def query_requirements(self, query_text, n_results=5):
        return self.req_collection.query(query_texts=[query_text], n_results=n_results)
    
    def clear_current_requirements(self):
        try:
            self.client.delete_collection("current_requirements")
            self.req_collection = self.client.get_or_create_collection(
                name="current_requirements",
                embedding_function=self.embedding_fn # type: ignore
            )
            print("🧹 Đã dọn sạch bộ nhớ yêu cầu cũ.")
        except Exception as e:
            print(f"⚠️ Lỗi khi clear collection: {e}")

# --- THÊM ĐOẠN NÀY ---
@lru_cache()
def get_chroma_service() -> ChromaService:
    """
    Hàm này đảm bảo ChromaService chỉ khởi tạo 1 lần duy nhất (Singleton)
    nhưng chỉ khi nào có request gọi đến nó (Lazy Loading).
    """
    print("🐢 Init ChromaService (Lazy Load)...")
    return ChromaService()
# import chromadb
# from chromadb.utils import embedding_functions
# import os
# from dotenv import load_dotenv
# import uuid

# load_dotenv()

# class ChromaService:
#     def __init__(self):
#         # 1. Kết nối DB (Lưu trữ vĩnh viễn trên ổ cứng)
#         self.client = chromadb.PersistentClient(path="./chroma_db")
        
#         # 2. Cấu hình OpenAI Embedding (Quay lại model cũ)
#         api_key = os.getenv("OPENAI_API_KEY", "")
#         if not api_key:
#             print("⚠️ Cảnh báo: Thiếu OPENAI_API_KEY trong file .env")

#         self.openai_ef = embedding_functions.OpenAIEmbeddingFunction(
#             api_key=api_key,
#             model_name="text-embedding-3-small" # 1536 dimensions
#         )

#         # 3. Tạo Collection: VĂN PHONG MẪU
#         self.style_collection = self.client.get_or_create_collection(
#             name="bidding_docs",
#             embedding_function=self.openai_ef # type: ignore
#         )

#         # 4. Tạo Collection: YÊU CẦU ĐẦU VÀO
#         self.req_collection = self.client.get_or_create_collection(
#             name="current_requirements",
#             embedding_function=self.openai_ef # type: ignore
#         )

#     # --- HÀM HỖ TRỢ CHUNG (Có logic chống lỗi quá tải Token) ---
#     def _save_to_collection(self, collection, chunks, source_filename):
#         """
#         Lưu chunks vào collection.
#         Tự động cắt nhỏ nếu chunk dài hơn giới hạn của OpenAI (8192 tokens).
#         """
#         if not chunks: return

#         ids, documents, metadatas = [], [], []
        
#         # NGƯỠNG AN TOÀN: 15.000 ký tự (~4000-5000 tokens). 
#         # OpenAI text-embedding-3-small max 8192 tokens. 
#         # Để 15k là rất an toàn, đảm bảo không bao giờ bị lỗi 400.
#         SAFE_CHAR_LIMIT = 15000 

#         for chunk in chunks:
#             # Lấy dữ liệu, xử lý các key khác nhau tùy nguồn gọi
#             raw_content = chunk.get('full_content') or chunk.get('content') or ""
#             title = chunk.get('chapter_title') or chunk.get('title') or "No Title"
#             category = chunk.get('category', 'general')

#             content_len = len(raw_content)

#             # --- LOGIC CẮT NHỎ (Sub-chunking) ---
#             if content_len > SAFE_CHAR_LIMIT:
#                 print(f"⚠️ Chương '{title}' dài {content_len} ký tự -> Đang cắt nhỏ...")
                
#                 # Cắt từng khúc 15.000 ký tự
#                 for i in range(0, content_len, SAFE_CHAR_LIMIT):
#                     sub_text = raw_content[i : i + SAFE_CHAR_LIMIT]
                    
#                     # Đánh số phần (Part 1, Part 2...)
#                     part_num = (i // SAFE_CHAR_LIMIT) + 1
#                     sub_title = f"{title} (Part {part_num})"
                    
#                     ids.append(str(uuid.uuid4()))
#                     documents.append(sub_text)
#                     metadatas.append({
#                         "source": source_filename,
#                         "chapter": sub_title,
#                         "category": category
#                     })
#             else:
#                 # Nếu ngắn thì lưu bình thường
#                 ids.append(str(uuid.uuid4()))
#                 documents.append(raw_content)
#                 metadatas.append({
#                     "source": source_filename,
#                     "chapter": title,
#                     "category": category
#                 })

#         # Batch insert (Gửi từng gói 20 cái)
#         BATCH_SIZE = 20
#         total_docs = len(ids)
        
#         try:
#             for i in range(0, total_docs, BATCH_SIZE):
#                 end = i + BATCH_SIZE
#                 collection.add(
#                     ids=ids[i:end],
#                     documents=documents[i:end],
#                     metadatas=metadatas[i:end]
#                 )
#             print(f"✅ Đã lưu {total_docs} vectors vào Collection: {collection.name}")
            
#         except Exception as e:
#             print(f"❌ Lỗi Critical khi lưu ChromaDB: {e}")

#     # --- CÁC HÀM GỌI TỪ BÊN NGOÀI ---

#     def save_styles(self, chunks, source_filename):
#         self._save_to_collection(self.style_collection, chunks, source_filename)

#     def save_requirements(self, chunks, source_filename):
#         self._save_to_collection(self.req_collection, chunks, source_filename)
        
#     def save_chunks_to_db(self, chunks, source_filename):
#         """Alias cho code cũ"""
#         self.save_styles(chunks, source_filename)

#     def query_styles(self, query_text, n_results=2):
#         return self.style_collection.query(query_texts=[query_text], n_results=n_results)

#     def query_requirements(self, query_text, n_results=5):
#         return self.req_collection.query(query_texts=[query_text], n_results=n_results)
    
#     def clear_current_requirements(self):
#         try:
#             self.client.delete_collection("current_requirements")
#             self.req_collection = self.client.get_or_create_collection(
#                 name="current_requirements",
#                 embedding_function=self.openai_ef # type: ignore
#             )
#             print("🧹 Đã dọn sạch bộ nhớ yêu cầu cũ.")
#         except Exception as e:
#             print(f"⚠️ Lỗi khi clear collection: {e}")

# chroma_service = ChromaService()