from app.integrations.ai.data_processing.chroma_service import ChromaService, get_chroma_service
from sentence_transformers import CrossEncoder
import re
from typing import List, Dict, Any, Optional
from functools import lru_cache
from fastapi import Depends

# [FIX 1] KHAI BÁO BIẾN TOÀN CỤC
global_reranker = None
_retrieval_service_instance = None

class RetrievalService:
    def __init__(self, chroma_service: ChromaService):
        self.chroma = chroma_service
        
        # [FIX 2] CHECK XEM ĐÃ CÓ MODEL CHƯA
        global global_reranker
        if global_reranker is None:
            print("⚖️ Đang tải model Re-ranking (Chạy lần đầu tiên)...")
            # Dùng model nhẹ cho CPU
            print("🚀 Đang dùng model nhẹ ms-marco-MiniLM-L-6-v2 cho nhanh...")
            global_reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2', max_length=512)
        else:
            print("⚡ Sử dụng lại model Re-ranking đã có trong RAM.")
            
        self.reranker = global_reranker

    # --- HÀM CŨ 1 (GIỮ NGUYÊN) ---
    def search_with_rerank(self, query: str, top_k=5):
        """
        [DRAFTING] Hàm này dùng để tìm kiếm trong YÊU CẦU ĐẦU VÀO (req_collection)
        """
        try:
            raw_results = self.chroma.req_collection.query(
                query_texts=[query],
                n_results=20 
            )
        except Exception as e:
            print(f"⚠️ Lỗi query req_collection: {e}")
            return []
        
        if not raw_results['documents'] or not raw_results['documents'][0]:
            return []

        documents = raw_results['documents'][0]
        metadatas = raw_results['metadatas'][0] # type: ignore
        
        pairs = [[query, doc] for doc in documents]
        scores = self.reranker.predict(pairs)
        
        scored_results = []
        for i, score in enumerate(scores):
            scored_results.append({
                "score": score,
                "child_content": documents[i],
                "parent_content": metadatas[i].get("parent_content", ""),
                "chapter_title": metadatas[i].get("chapter_title", "")
            })
            
        scored_results.sort(key=lambda x: x['score'], reverse=True)
        
        final_context = []
        seen_parents = set()
        for item in scored_results:
            p_content = item['parent_content']
            p_hash = hash(p_content)
            if p_hash not in seen_parents:
                final_context.append(item)
                seen_parents.add(p_hash)
            if len(final_context) >= top_k:
                break
                
        print(f"🎯 [Drafting] Re-ranking xong. Chọn được {len(final_context)} ngữ cảnh.")
        return final_context
    
    # --- HÀM CŨ 2 (GIỮ NGUYÊN) ---
    def search_legal_docs(self, query: str, filters: Optional[Dict[str, Any]] = None, top_k=5):
        """
        [CHATBOT] Hàm này dùng để tìm kiếm trong KHO KIẾN THỨC LUẬT (legal_collection)
        """
        where_condition = filters if filters else None 
        try:
            raw_results = self.chroma.legal_collection.query(
                query_texts=[query],
                n_results=50,
                where=where_condition 
            )
        except Exception as e:
            print(f"⚠️ Lỗi truy vấn ChromaDB: {e}")
            try:
                raw_results = self.chroma.legal_collection.query(
                    query_texts=[query],
                    n_results=50
                )
            except Exception:
                return []
        
        if not raw_results['documents'] or not raw_results['documents'][0]:
            return []

        docs = raw_results['documents'][0]
        metadatas: List[Dict[str, Any]] = raw_results['metadatas'][0] # type: ignore
        
        rerank_pairs = [[query, doc_content] for doc_content in docs]
        scores = self.reranker.predict(rerank_pairs)
        
        final_results = []
        for i, score in enumerate(scores):
            meta = metadatas[i]
            raw_priority = meta.get('priority', 0)
            try:
                legal_priority = float(raw_priority)
            except (ValueError, TypeError):
                legal_priority = 0.0

            adjusted_score = score + (legal_priority * 0.05)
            parent_content = meta.get("parent_content") or docs[i]

            final_results.append({
                "score": adjusted_score,
                "content": docs[i],
                "parent_content": parent_content, 
                "source": meta.get("source", "Tài liệu hệ thống"),
                "year": meta.get("year", "N/A"),
                "level": meta.get("level", "unknown")
            })

        final_results.sort(key=lambda x: x['score'], reverse=True)

        unique_results = []
        seen_parent_hashes = set()
        for item in final_results:
            p_content = str(item['parent_content'])
            p_hash = hash(p_content)
            if p_hash not in seen_parent_hashes:
                unique_results.append(item)
                seen_parent_hashes.add(p_hash)
            if len(unique_results) >= top_k:
                break
        
        print(f"🔍 [Legal Search] Tìm thấy {len(unique_results)} văn bản phù hợp.")
        return unique_results

    # --- [ĐÃ SỬA] HÀM NÀY ĐÃ THÊM THAM SỐ filters ĐỂ SỬA LỖI ---
    def search(self, query: str, collection_name: str = "current_requirements", top_k: int = 10, filters: Optional[Dict] = None):
        """
        [NEW] Hàm tìm kiếm tổng quát, hỗ trợ chọn Collection và Filter.
        Phục vụ cho Agent.
        """
        # Nếu user không truyền tên, mặc định tìm trong requirements
        target_collection = collection_name if collection_name else "current_requirements"
        
        print(f"🔍 Agent Searching '{query}' in [{target_collection}] (Filters: {filters})...")
        
        # Gọi hàm query_collection của ChromaService
        # Lưu ý: ChromaService phải có hàm query_collection (đã cập nhật ở bước trước)
        results = self.chroma.query_collection(
            collection_name=target_collection,
            query_texts=[query],
            n_results=top_k,
            where=filters # <--- QUAN TRỌNG: Truyền filters vào đây
        )
        return results

def get_retrieval_service(
    chroma_service: ChromaService = Depends(get_chroma_service)
) -> RetrievalService:
    global _retrieval_service_instance
    if _retrieval_service_instance is None:
        _retrieval_service_instance = RetrievalService(chroma_service)
    return _retrieval_service_instance