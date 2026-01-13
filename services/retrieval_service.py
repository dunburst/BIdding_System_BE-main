# services/retrieval_service.py
from services.chroma_service import ChromaService, get_chroma_service
from sentence_transformers import CrossEncoder
import re
from typing import List, Dict, Any, Optional
from functools import lru_cache
from fastapi import Depends
# [FIX 1] KHAI BÁO BIẾN TOÀN CỤC (GLOBAL)
# Biến này sẽ giữ model trong RAM mãi mãi, không bị reset khi gọi hàm
global_reranker = None
# Biến lưu instance của Service
_retrieval_service_instance = None
class RetrievalService:
    def __init__(self, chroma_service: ChromaService):
        self.chroma = chroma_service
        # Model Re-ranking chuyên dụng cho đa ngôn ngữ (bao gồm tiếng Việt)
        # BAAI/bge-reranker-v2-m3 là top tier hiện nay
        print("⚖️ Đang tải model Re-ranking (bge-reranker-v2-m3)...")
        self.reranker = CrossEncoder('BAAI/bge-reranker-v2-m3', max_length=512)
        # [FIX 2] CHECK XEM ĐÃ CÓ MODEL CHƯA, NẾU CHƯA MỚI LOAD
        # global global_reranker
        # if global_reranker is None:
        #     print("⚖️ Đang tải model Re-ranking (Chạy lần đầu tiên)...")
        #     # [LỜI KHUYÊN] Model 'bge-reranker-v2-m3' rất nặng (500MB+). 
        #     # Nếu chạy CPU, bạn nên đổi sang 'cross-encoder/ms-marco-MiniLM-L-6-v2' (nhẹ hơn 10 lần)
            
        #     # Option 1: Model hiện tại (Tốt nhưng Chậm trên CPU)
        #     # global_reranker = CrossEncoder('BAAI/bge-reranker-v2-m3', max_length=512)
            
        #     # Option 2: Model nhẹ (Khuyên dùng cho CPU)
        #     print("🚀 Đang dùng model nhẹ ms-marco-MiniLM-L-6-v2 cho nhanh...")
        #     global_reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2', max_length=512)
            
        # else:
        #     print("⚡ Sử dụng lại model Re-ranking đã có trong RAM.")
            
        # self.reranker = global_reranker

    def search_with_rerank(self, query: str, top_k=5):
        """
        [DRAFTING] Hàm này dùng để tìm kiếm trong YÊU CẦU ĐẦU VÀO (req_collection)
        Phục vụ tính năng Viết thầu dựa trên HSMT.
        """
        # Bước 1: Vector Search
        # [CHÚ Ý] Dùng req_collection cho drafting
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

        # Chuẩn bị dữ liệu cho Re-ranker
        documents = raw_results['documents'][0]
        metadatas = raw_results['metadatas'][0] # type: ignore
        
        pairs = [[query, doc] for doc in documents]
        
        # Bước 2: Re-ranking
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
        
        # Bước 3: De-duplication
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
    
    def search_legal_docs(self, query: str, filters: Optional[Dict[str, Any]] = None, top_k=5):
        """
        [CHATBOT] Hàm này dùng để tìm kiếm trong KHO KIẾN THỨC LUẬT (legal_collection)
        Phục vụ tính năng Hỏi đáp luật.
        """
        
        # [FIX 1] Xử lý filters: Nếu rỗng hoặc None thì để None để Chroma tìm tất cả
        where_condition = filters if filters else None 
        
        try:
            # [FIX 2] QUAN TRỌNG: Đổi sang legal_collection như bạn yêu cầu
            raw_results = self.chroma.legal_collection.query(
                query_texts=[query],
                n_results=50, # Lấy rộng để Re-rank
                where=where_condition 
            )
        except Exception as e:
            print(f"⚠️ Lỗi truy vấn ChromaDB (có thể do filter hoặc collection rỗng): {e}. Đang thử tìm không cần filter...")
            # Fallback: Tìm không cần filter
            try:
                raw_results = self.chroma.legal_collection.query(
                    query_texts=[query],
                    n_results=50
                )
            except Exception as nested_e:
                print(f"❌ Lỗi Critical khi query legal_collection: {nested_e}")
                return []
        
        if not raw_results['documents'] or not raw_results['documents'][0]:
            print("⚠️ Không tìm thấy documents nào trong legal_collection phù hợp.")
            return []

        docs = raw_results['documents'][0]
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
            
            # [FIX 3] Ép kiểu an toàn cho priority
            raw_priority = meta.get('priority', 0)
            try:
                legal_priority = float(raw_priority) # type: ignore
            except (ValueError, TypeError):
                legal_priority = 0.0

            # Cộng điểm ưu tiên (Luật > Nghị định)
            adjusted_score = score + (legal_priority * 0.05)
            
            # [FIX 4] Fallback nội dung: Nếu không có parent_content thì dùng content gốc
            parent_content = meta.get("parent_content")
            if not parent_content:
                parent_content = docs[i]

            final_results.append({
                "score": adjusted_score,
                "content": docs[i],
                "parent_content": parent_content, 
                "source": meta.get("source", "Tài liệu hệ thống"),
                "year": meta.get("year", "N/A"),
                "level": meta.get("level", "unknown")
            })

        # Sort & De-duplication
        final_results.sort(key=lambda x: x['score'], reverse=True)

        unique_results = []
        for item in final_results:
            p_content = str(item['parent_content'])
            p_hash = hash(p_content)
            
            if p_hash not in seen_parent_hashes:
                unique_results.append(item)
                seen_parent_hashes.add(p_hash)
            
            if len(unique_results) >= top_k:
                break
        
        print(f"🔍 [Legal Search] Tìm thấy {len(unique_results)} văn bản phù hợp từ legal_collection.")
        return unique_results
    
# --- PROVIDER ---
# @lru_cache()
# def get_retrieval_service(
#     chroma_service: ChromaService = Depends(get_chroma_service)
# ) -> RetrievalService:
#     return RetrievalService(chroma_service)

def get_retrieval_service(
    chroma_service: ChromaService = Depends(get_chroma_service)
) -> RetrievalService:
    global _retrieval_service_instance
    # Nếu chưa có thì tạo mới
    if _retrieval_service_instance is None:
        _retrieval_service_instance = RetrievalService(chroma_service)
    return _retrieval_service_instance