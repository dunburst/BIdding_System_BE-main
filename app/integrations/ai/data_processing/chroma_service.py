from typing import Any, Dict, Optional, List
import chromadb
from chromadb.utils import embedding_functions
import os
from dotenv import load_dotenv
import uuid
import shutil
from functools import lru_cache

load_dotenv()

class ChromaService:
    def __init__(self):
        # Đường dẫn lưu DB
        # 1. Lấy thư mục gốc dự án (BIDDINGSYSTEM)
        project_root = os.getcwd()

        # 2. Thiết lập đường dẫn sâu vào bên trong
        self.db_path = os.path.join(
            project_root, 
            "app", "infrastructure", "vectordb", "chroma_db"
        )
        
        # [QUAN TRỌNG] Tạo thư mục (tự động tạo cả các thư mục cha nếu thiếu)
        os.makedirs(self.db_path, exist_ok=True)
        # self.db_path = "./chroma_db"
        
        # # [QUAN TRỌNG] Tạo thư mục nếu chưa có để tránh lỗi
        # os.makedirs(self.db_path, exist_ok=True)
        
        self.client = chromadb.PersistentClient(path=self.db_path)
        
        # --- CẤU HÌNH OPENAI EMBEDDING ---
        api_key = os.getenv("OPENAI_API_KEY")
        api_base = os.getenv("OPENAI_API_BASE")  
        
        if not api_key:
            print("⚠️ Cảnh báo: Thiếu OPENAI_API_KEY. Vector Search sẽ lỗi.")

        self.embedding_fn = embedding_functions.OpenAIEmbeddingFunction(
            api_key=api_key,
            model_name="text-embedding-3-large",
            api_base=api_base
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
        
        # 5. Tạo Collection: PHÁP LUẬT
        self.legal_collection = self.client.get_or_create_collection(
            name="legal_docs", 
            embedding_function=self.embedding_fn # type: ignore
        )

    # --- HÀM HỖ TRỢ CHUNG (CŨ) ---
    def _save_to_collection(self, collection, chunks, source_filename):
        """
        Lưu chunks vào collection với cơ chế cắt nhỏ (Safe Split)
        """
        if not chunks: return

        ids, documents, metadatas = [], [], []
        SAFE_CHAR_LIMIT = 1000 

        for chunk in chunks:
            raw_content = chunk.get('full_content') or chunk.get('content') or ""
            title = chunk.get('chapter_title') or "No Title"
            category = chunk.get('category', 'general')

            content_len = len(raw_content)
            
            if content_len > SAFE_CHAR_LIMIT:
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
            
    # --- [HÀM CŨ] ---
    def save_hierarchical_chunks(self, chunks, source_filename, collection_name="legal_docs"):
        """
        Lưu chunks vào collection được chỉ định
        """
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

    def save_styles(self, chunks, source_filename):
        self._save_to_collection(self.style_collection, chunks, source_filename)

    def save_requirements(self, chunks: List[Dict[str, Any]], source_filename: str, project_name: str):
        collection = self.client.get_or_create_collection("current_requirements")
        
        ids = []
        documents = []
        metadatas = []

        for idx, chunk in enumerate(chunks):
            chunk_id = f"{project_name}_{source_filename}_{idx}"
            
            meta = chunk.get("metadata", {}).copy()
            meta["source"] = source_filename
            meta["project_name"] = project_name 
            
            ids.append(chunk_id)
            documents.append(chunk.get("page_content", ""))
            metadatas.append(meta)

        if ids:
            collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
            print(f"💾 Đã lưu {len(ids)} chunks vào dự án '{project_name}' (File: {source_filename})")
        
    def save_chunks_to_db(self, chunks, source_filename):
        """Alias tương thích ngược"""
        self.save_styles(chunks, source_filename)

    def query_styles(self, query_text, n_results=2):
        return self.style_collection.query(query_texts=[query_text], n_results=n_results)

    def query_requirements(self, query_text: str, n_results: int = 5, project_name: Optional[str] = None) -> Any: 
        collection = self.client.get_collection("current_requirements")
        
        where_filter: Dict[str, Any] = {} 
        if project_name:
            where_filter["project_name"] = project_name

        final_where = where_filter if where_filter else None
        print(f"🔍 Querying Chroma with filter: {final_where}")

        return collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=final_where 
        )
        
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

    def list_source_files(self, collection_name: str = "current_requirements", project_name: Optional[str] = None) -> List[str]:
        try:
            collection = self.client.get_collection(collection_name)
            
            where_filter = {}
            if project_name:
                where_filter["project_name"] = project_name
            final_where = where_filter if where_filter else None

            results = collection.get(
                include=["metadatas"],
                where=final_where
            )
            
            files = set()
            metadatas = results.get("metadatas")
            
            if metadatas: 
                for meta in metadatas:
                    if meta and "source" in meta:
                        files.add(str(meta["source"]))
            
            return list(files)

        except Exception as e:
            print(f"⚠️ Lỗi lấy danh sách file: {str(e)}")
            return []

    # ==========================================================================
    # [NEW] CÁC HÀM MỚI BỔ SUNG CHO AGENT VÀ QUẢN TRỊ HỆ THỐNG
    # ==========================================================================

    def get_or_create_collection(self, name: str):
        """Lấy collection theo tên, nếu chưa có thì tạo mới"""
        return self.client.get_or_create_collection(
            name=name,
            embedding_function=self.embedding_fn # type: ignore
        )

    def add_documents(self, collection_name: str, documents: List[str], metadatas: List[Dict], ids: List[str]):
        """Hàm thêm dữ liệu tổng quát cho bất kỳ collection nào"""
        try:
            collection = self.get_or_create_collection(collection_name)
            collection.add(
                documents=documents,
                metadatas=metadatas,#type: ignore
                ids=ids
            )
            print(f"💾 [Chroma] Đã lưu {len(documents)} bản ghi vào '{collection_name}'.")
        except Exception as e:
            print(f"❌ [Chroma Error] Lỗi lưu dữ liệu: {e}")
            raise e

    def query_collection(self, collection_name: str, query_texts: list, n_results: int, where: Optional[dict] = None):
        """Hàm tìm kiếm linh hoạt cho Agent, hỗ trợ filter metadata"""
        try:
            # Lấy collection (không tạo mới để tránh rác nếu tên sai)
            col = self.client.get_collection(name=collection_name)
            
            results = col.query(
                query_texts=query_texts, 
                n_results=n_results, 
                where=where
            )
            
            formatted_results = []
            if results['documents']:
                for i, doc in enumerate(results['documents'][0]):
                    meta = results['metadatas'][0][i] if results['metadatas'] else {}
                    doc_id = results['ids'][0][i] if results['ids'] else ""
                    dist = results['distances'][0][i] if results['distances'] else 0
                    
                    formatted_results.append({
                        "content": doc,
                        "metadata": meta,
                        "id": doc_id,
                        "score": dist
                    })
            return formatted_results
        except Exception as e:
            print(f"⚠️ Lỗi query collection '{collection_name}': {e}")
            return []

    def delete_document_vectors(self, source_filename: str, collection_name: str = "legal_docs"):
        """
        Xóa vector của một file cụ thể trong collection chỉ định.
        """
        try:
            print(f"🗑️ Đang tiến hành quét xóa vectors của: {source_filename} trong {collection_name}...")
            print(f"🗑️ Đang tiến hành quét xóa vectors của: {source_filename} trong {collection_name}...")
            
            try:
                target_collection = self.client.get_collection(name=collection_name)
            except ValueError:
                print(f"⚠️ Collection '{collection_name}' chưa tồn tại -> Bỏ qua.")
                return True

            # [CẢI TIẾN] Xóa triệt để các biến thể key metadata
            # ChromaDB .delete() không báo lỗi nếu where clause không tìm thấy item nào.
            # Nên cứ gọi thoải mái.
            
            target_collection.delete(where={"source": source_filename})
            target_collection.delete(where={"source_file": source_filename})
            target_collection.delete(where={"filename": source_filename})
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
            print(f"✅ Đã gửi lệnh xóa vectors (nếu có) cho file {source_filename}.")
            return True


        except Exception as e:
            # Chỉ in log lỗi hệ thống, không làm crash luồng chính
            print(f"❌ Lỗi ngoại lệ khi gọi ChromaDB (kết nối/timeout...): {e}")
            # Chỉ in log lỗi hệ thống, không làm crash luồng chính
            print(f"❌ Lỗi ngoại lệ khi gọi ChromaDB (kết nối/timeout...): {e}")
            return False

    def list_all_collections(self) -> list:
        """
        Lấy danh sách tên tất cả các Collection đang tồn tại trong ChromaDB.
        """
        try:
            collections = self.client.list_collections()
            collection_names = [c.name for c in collections]
            print(f"📂 Tìm thấy {len(collection_names)} collections: {collection_names}")
            return collection_names
        except Exception as e:
            print(f"❌ Lỗi khi lấy danh sách collection: {e}")
            return []

    def list_files_in_collection(self, collection_name: str) -> List[str]:
        """
        Lấy danh sách TẤT CẢ các file (unique) đang có trong collection.
        """
        try:
            print(f"📂 Đang quét collection: {collection_name}...")
            try:
                collection = self.client.get_collection(collection_name)
            except Exception:
                print(f"⚠️ Collection '{collection_name}' chưa tồn tại hoặc tên sai.")
                return []
            
            # Lấy tất cả dữ liệu (limit=None) nhưng chỉ lấy cột metadata để tiết kiệm RAM
            results = collection.get(
                include=["metadatas"],
                limit=None 
            )
            
            files = set()
            metadatas = results.get("metadatas")
            
            if metadatas: 
                for meta in metadatas:
                    if meta:
                        if "source" in meta:
                            files.add(str(meta["source"]))
                        elif "source_file" in meta:
                            files.add(str(meta["source_file"]))
                        elif "filename" in meta:
                            files.add(str(meta["filename"]))
            
            final_list = list(files)
            print(f"✅ Kết quả: Tìm thấy {len(final_list)} file unique.")
            return final_list

        except Exception as e:
            print(f"❌ Lỗi khi list file: {str(e)}")
            return []
        
    def get_file_structure(self, filename: str, collection_name: str = "bidding_docs") -> str:
        """
        Lấy danh sách các chương (Chapter Titles) từ metadata của file cụ thể
        """
        try:
            collection = self.client.get_collection(collection_name)
            
            # Lấy tất cả chunks của file này (chỉ lấy metadata)
            results = collection.get(
                where={"source": filename},
                include=["metadatas"]
            )
            
            if not results['metadatas']:
                return ""

            # Trích xuất và sắp xếp lại các unique chapters
            chapters = set()
            # Vì Chroma lưu lộn xộn, ta cố gắng giữ thứ tự nếu có thể (nhưng set thì không order)
            # Một mẹo là dùng dict để giữ insertion order nếu python 3.7+
            chapters_dict = {} 
            
            for meta in results['metadatas']:
                if meta and 'chapter' in meta:
                    chapters_dict[meta['chapter']] = None
            
            structure_str = "\n".join([f"- {title}" for title in chapters_dict.keys()])
            return structure_str

        except Exception as e:
            print(f"❌ Lỗi lấy cấu trúc file: {e}")
            return ""

# Singleton Lazy Load
@lru_cache()
def get_chroma_service() -> ChromaService:
    print("🐢 Init ChromaService (Lazy Load)...")
    return ChromaService()