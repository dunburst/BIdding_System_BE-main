from typing import Optional
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
            
    # [CHANGE] Thêm tham số collection_name
    def save_hierarchical_chunks(self, chunks, source_filename, collection_name="legal_docs"):
        """
        Lưu chunks vào collection được chỉ định
        """
        # Lấy hoặc tạo Collection theo tên người dùng nhập
        target_collection = self.client.get_or_create_collection(
            name=collection_name, 
            embedding_function=self.embedding_fn # type: ignore
        )

        ids = []
        documents = []
        metadatas = []
        
        for chunk in chunks:
            ids.append(str(uuid.uuid4()))
            documents.append(chunk['page_content'])
            metadatas.append(chunk['metadata']) 
            
        BATCH_SIZE = 50
        total = len(ids)
        
        try:
            for i in range(0, total, BATCH_SIZE):
                end = i + BATCH_SIZE
                target_collection.add(
                    ids=ids[i:end],
                    documents=documents[i:end],
                    metadatas=metadatas[i:end]
                )
            print(f"💾 Đã lưu {total} vectors vào Collection '{collection_name}'.")
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
            
    # [CHANGE] Cập nhật hàm xóa để xóa đúng collection
    def delete_document_vectors(self, source_filename: str, collection_name="legal_docs"):
        try:
            print(f"🗑️ Đang tiến hành xóa vectors của: {source_filename} trong {collection_name}...")
            
            target_collection = self.client.get_collection(name=collection_name)
            target_collection.delete(
                where={"source": source_filename}
            )
            
            print(f"✅ Đã xóa sạch vectors của file {source_filename}.")
            return True
        except ValueError:
            print(f"⚠️ Collection {collection_name} không tồn tại, bỏ qua bước xóa.")
            return True
        except Exception as e:
            print(f"❌ Lỗi khi xóa vector trong Chroma: {e}")
            return False
        
        # 👇 THÊM HÀM NÀY VÀO CUỐI CLASS
    def list_all_collections(self) -> list:
        """
        Lấy danh sách tên tất cả các Collection đang tồn tại trong ChromaDB.
        """
        try:
            # list_collections trả về một list các object Collection
            collections = self.client.list_collections()
            
            # Chúng ta chỉ cần lấy tên (name) của chúng
            collection_names = [c.name for c in collections]
            
            print(f"📂 Tìm thấy {len(collection_names)} collections: {collection_names}")
            return collection_names
        except Exception as e:
            print(f"❌ Lỗi khi lấy danh sách collection: {e}")
            return []
        

# --- HÀM MỚI QUAN TRỌNG CHO AGENT ---
    def query_collection(self, collection_name: str, query_texts: list, n_results: int, where: Optional[dict] = None):
        """Cho phép tìm kiếm linh hoạt trên bất kỳ collection nào"""
        try:
            col = self.client.get_collection(name=collection_name)
            results = col.query(query_texts=query_texts, n_results=n_results, where=where)
            
            formatted_results = []
            if results['documents']:
                for i, doc in enumerate(results['documents'][0]):
                    formatted_results.append({
                        "content": doc,
                        "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                        "id": results['ids'][0][i]
                    })
            return formatted_results
        except Exception as e:
            print(f"⚠️ Lỗi query collection '{collection_name}': {e}")
            return []
# --- THÊM ĐOẠN NÀY ---
@lru_cache()
def get_chroma_service() -> ChromaService:
    """
    Hàm này đảm bảo ChromaService chỉ khởi tạo 1 lần duy nhất (Singleton)
    nhưng chỉ khi nào có request gọi đến nó (Lazy Loading).
    """
    print("🐢 Init ChromaService (Lazy Load)...")
    return ChromaService()
