# services/retrieval_service.py
from services.chroma_service import ChromaService, get_chroma_service
from sentence_transformers import CrossEncoder
import re
from typing import List, Dict, Any, Optional
from functools import lru_cache
from fastapi import Depends
class RetrievalService:
    def __init__(self, chroma_service: ChromaService):
        self.chroma = chroma_service
        # Model Re-ranking chuyên dụng cho đa ngôn ngữ (bao gồm tiếng Việt)
        # BAAI/bge-reranker-v2-m3 là top tier hiện nay
        print("⚖️ Đang tải model Re-ranking (bge-reranker-v2-m3)...")
        self.reranker = CrossEncoder('BAAI/bge-reranker-v2-m3', max_length=512)

    def search_with_rerank(self, query: str, top_k=5):
        """
        1. Lấy Top 20 từ Vector DB (Tìm diện rộng).
        2. Dùng Cross-Encoder chấm điểm lại (Tìm chính xác).
        3. Trả về Top K Parent Content tốt nhất.
        """
        
        # Bước 1: Vector Search (Lấy dư ra, ví dụ 20 kết quả)
        raw_results = self.chroma.req_collection.query(
            query_texts=[query],
            n_results=20 
        )
        
        if not raw_results['documents'] or not raw_results['documents'][0]:
            return []

        # Chuẩn bị dữ liệu cho Re-ranker: List of [Query, Document]
        documents = raw_results['documents'][0]
        metadatas = raw_results['metadatas'][0] # type: ignore
        
        pairs = [[query, doc] for doc in documents]
        
        # Bước 2: Re-ranking (Chấm điểm sự liên quan)
        # Model này sẽ đọc cả query và document cùng lúc để hiểu ngữ cảnh sâu hơn
        scores = self.reranker.predict(pairs)
        
        # Kết hợp điểm số với metadata
        scored_results = []
        for i, score in enumerate(scores):
            scored_results.append({
                "score": score,
                "child_content": documents[i],
                "parent_content": metadatas[i].get("parent_content", ""),
                "chapter_title": metadatas[i].get("chapter_title", "")
            })
            
        # Sắp xếp giảm dần theo điểm
        scored_results.sort(key=lambda x: x['score'], reverse=True)
        
        # Bước 3: Lọc trùng lặp Parent (De-duplication)
        # Vì nhiều child chunks có thể thuộc cùng 1 Parent -> Ta chỉ lấy Parent 1 lần
        final_context = []
        seen_parents = set()
        
        for item in scored_results:
            p_content = item['parent_content']
            # Hash nội dung để kiểm tra trùng lặp nhanh
            p_hash = hash(p_content)
            
            if p_hash not in seen_parents:
                final_context.append(item)
                seen_parents.add(p_hash)
            
            if len(final_context) >= top_k:
                break
                
        print(f"🎯 Re-ranking xong. Chọn được {len(final_context)} ngữ cảnh tốt nhất.")
        return final_context
    
    def search_legal_docs(self, query: str, filters: Optional[Dict[str, Any]] = None, top_k=5):
        
        # [FIX LỖI 1] Xử lý filters None -> dict rỗng {}
        # ChromaDB yêu cầu 'where' phải là dict hoặc None (nhưng thư viện type check chặt quá)
        where_condition = filters if filters is not None else {}
        
        # Query Chroma
        raw_results = self.chroma.req_collection.query(
            query_texts=[query],
            n_results=50,
            where=where_condition 
        )
        
        if not raw_results['documents'] or not raw_results['documents'][0]:
            return []

        docs = raw_results['documents'][0]
        # Ép kiểu metadata về list dict để tránh lỗi type checker
        metadatas: List[Dict[str, Any]] = raw_results['metadatas'][0] # type: ignore
        
        # Chuẩn bị input cho Re-ranker
        rerank_pairs = []
        for doc_content in docs:
            rerank_pairs.append([query, doc_content])

        # Re-ranking
        scores = self.reranker.predict(rerank_pairs)
        
        final_results = []
        seen_parent_hashes = set()

        for i, score in enumerate(scores):
            meta = metadatas[i]
            
            # [FIX LỖI 2] Ép kiểu an toàn trước khi nhân
            # meta.get lấy ra Union[str, int, float...], cần ép về float
            raw_priority = meta.get('priority', 0)
            try:
                legal_priority = float(raw_priority) # type: ignore
            except (ValueError, TypeError):
                legal_priority = 0.0

            # Cộng điểm ưu tiên (Luật > Nghị định)
            adjusted_score = score + (legal_priority * 0.05)
            
            final_results.append({
                "score": adjusted_score,
                "content": docs[i],
                "parent_content": meta.get("parent_content", ""), # Default string rỗng
                "source": meta.get("source", ""),
                "year": meta.get("year", 0),
                "level": meta.get("level", "unknown")
            })

        # Sort & De-duplication
        final_results.sort(key=lambda x: x['score'], reverse=True)

        unique_results = []
        for item in final_results:
            # Hash parent content để lọc trùng
            p_content = str(item['parent_content'])
            p_hash = hash(p_content)
            
            if p_hash not in seen_parent_hashes:
                unique_results.append(item)
                seen_parent_hashes.add(p_hash)
            
            if len(unique_results) >= top_k:
                break
                
        return unique_results
    
# --- [QUAN TRỌNG] HÀM PROVIDER ĐỂ FASTAPI GỌI ---
@lru_cache()
def get_retrieval_service(
    # Tự động inject ChromaService vào RetrievalService
    chroma_service: ChromaService = Depends(get_chroma_service)
) -> RetrievalService:
    return RetrievalService(chroma_service)