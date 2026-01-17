from typing import Any, Dict, Optional, List
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

    # --- [UPDATE 1] LƯU DỮ LIỆU KÈM NHÃN DỰ ÁN ---
    def save_requirements(self, chunks: List[Dict[str, Any]], source_filename: str, project_name: str):
        collection = self.client.get_or_create_collection("current_requirements")
        
        ids = []
        documents = []
        metadatas = []

        for idx, chunk in enumerate(chunks):
            # Tạo ID: kết hợp project + filename + index để tránh trùng
            chunk_id = f"{project_name}_{source_filename}_{idx}"
            
            # Lấy metadata gốc và thêm project_name vào
            meta = chunk.get("metadata", {}).copy()
            meta["source"] = source_filename
            meta["project_name"] = project_name  # <--- KEY CHANGE: Đánh nhãn dự án
            
            ids.append(chunk_id)
            documents.append(chunk.get("page_content", ""))
            metadatas.append(meta)

        if ids:
            # Upsert để nếu trùng ID (cùng file, cùng dự án update lại) thì nó tự ghi đè
            collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
            print(f"💾 Đã lưu {len(ids)} chunks vào dự án '{project_name}' (File: {source_filename})")
        
    def save_chunks_to_db(self, chunks, source_filename):
        """Alias tương thích ngược"""
        self.save_styles(chunks, source_filename)

    def query_styles(self, query_text, n_results=2):
        return self.style_collection.query(query_texts=[query_text], n_results=n_results)

    # --- [UPDATE 2] TÌM KIẾM CÓ LỌC THEO DỰ ÁN ---
    # --- [FIXED] SỬA LỖI TYPE HINT ---
    def query_requirements(self, query_text: str, n_results: int = 5, project_name: Optional[str] = None) -> Any: 
        # Đổi return type thành Any hoặc dict để tránh lỗi "QueryResult is not assignable..."
        
        collection = self.client.get_collection("current_requirements")
        
        # [FIX] Khai báo kiểu tường minh là Dict[str, Any] để bypass lỗi "dict[str, str] is not assignable to Where"
        where_filter: Dict[str, Any] = {} 
        
        if project_name:
            where_filter["project_name"] = project_name

        # Nếu dict rỗng thì gán None
        final_where = where_filter if where_filter else None

        print(f"🔍 Querying Chroma with filter: {final_where}")

        return collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=final_where 
        )
        
    def list_files_in_collection(self, collection_name: str) -> List[str]:
        """
        Lấy danh sách TẤT CẢ các file (unique) đang có trong collection.
        Sửa lỗi: Thêm limit=None để quét sạch DB.
        """
        try:
            print(f"📂 Đang quét collection: {collection_name}...")
            # 1. Lấy collection
            try:
                collection = self.client.get_collection(collection_name)
            except Exception:
                print(f"⚠️ Collection '{collection_name}' chưa tồn tại hoặc tên sai.")
                return []
            
            # 2. Lấy dữ liệu
            # [QUAN TRỌNG] Phải có limit=None, nếu không nó chỉ lấy 10 dòng đầu
            results = collection.get(
                include=["metadatas"],
                limit=None 
            )
            
            files = set()
            metadatas = results.get("metadatas")
            
            # Debug: In ra số lượng vector tìm thấy
            count = len(metadatas) if metadatas else 0
            print(f"📊 Tìm thấy {count} vectors trong collection.")

            if metadatas: 
                for meta in metadatas:
                    if meta:
                        # Kiểm tra cả 2 trường hợp key phổ biến để chắc chắn không bị sót
                        if "source" in meta:
                            files.add(str(meta["source"]))
                        elif "source_file" in meta:
                            files.add(str(meta["source_file"]))
                        elif "filename" in meta:
                            files.add(str(meta["filename"]))
            
            final_list = list(files)
            print(f"✅ Kết quả: Tìm thấy {len(final_list)} file unique: {final_list}")
            return final_list

        except Exception as e:
            print(f"❌ Lỗi khi list file: {str(e)}")
            return []
        

    # --- [FIX LỖI NONE TYPE] ---
    def list_source_files(self, collection_name: str = "current_requirements", project_name: Optional[str] = None) -> List[str]:
        try:
            collection = self.client.get_collection(collection_name)
            
            where_filter = {}
            if project_name:
                where_filter["project_name"] = project_name
            final_where = where_filter if where_filter else None

            # Lấy metadata
            results = collection.get(
                include=["metadatas"],
                where=final_where
            )
            
            files = set()
            
            # [QUAN TRỌNG] Kiểm tra xem key 'metadatas' có tồn tại và có dữ liệu không
            metadatas = results.get("metadatas")
            
            if metadatas: # Chỉ chạy vòng lặp nếu metadatas không phải None
                for meta in metadatas:
                    if meta and "source" in meta:
                        files.add(str(meta["source"]))
            
            return list(files)

        except Exception as e:
            print(f"⚠️ Lỗi lấy danh sách file: {str(e)}")
            return []
    
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
    def delete_document_vectors(self, source_filename: str, collection_name: str):
        """
        Xóa vector an toàn. Luôn trả về True trừ khi lỗi kết nối nghiêm trọng.
        """
        try:
            print(f"🗑️ Đang tiến hành quét xóa vectors của: {source_filename} trong {collection_name}...")
            
            try:
                target_collection = self.client.get_collection(name=collection_name)
            except ValueError:
                # Lỗi này xảy ra khi collection chưa được tạo -> Coi như đã xóa sạch.
                print(f"⚠️ Collection '{collection_name}' chưa tồn tại -> Bỏ qua.")
                return True

            # [CẢI TIẾN] Xóa triệt để các biến thể key metadata
            # ChromaDB .delete() không báo lỗi nếu where clause không tìm thấy item nào.
            # Nên cứ gọi thoải mái.
            
            target_collection.delete(where={"source": source_filename})
            target_collection.delete(where={"source_file": source_filename})
            target_collection.delete(where={"filename": source_filename})
            
            print(f"✅ Đã gửi lệnh xóa vectors (nếu có) cho file {source_filename}.")
            return True

        except Exception as e:
            # Chỉ in log lỗi hệ thống, không làm crash luồng chính
            print(f"❌ Lỗi ngoại lệ khi gọi ChromaDB (kết nối/timeout...): {e}")
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
