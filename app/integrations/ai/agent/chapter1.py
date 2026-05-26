# services/chapter1_agent.py
import logging
from typing import List, Optional, Dict
from sentence_transformers import CrossEncoder
from openai import OpenAI
from app.integrations.ai.data_processing.retrieval_service import RetrievalService

logger = logging.getLogger(__name__)

class Chapter1Agent:
    def __init__(self, retrieval_service: RetrievalService, openai_client: OpenAI):
        self.retriever = retrieval_service
        self.client = openai_client
        self.model_name = "gpt-4o"
        
        try:
            # Model Rerank
            self.reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
            logger.info("Reranker model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load Reranker: {e}")
            self.reranker = None

    # [CẬP NHẬT] Thêm tham số filters
    def _smart_retrieve(self, query: str, collection_name: str, top_k_fetch: int = 50, top_k_final: int = 15, filters: Optional[Dict] = None) -> str:
        """
        Lấy thật nhiều (50) -> Lọc lấy tinh hoa (15).
        Hỗ trợ filters để lọc theo tên file cụ thể.
        """
        # 1. Retrieve
        raw_results = self.retriever.search(
            query=query, 
            collection_name=collection_name, 
            top_k=top_k_fetch,
            filters=filters # <--- Truyền filter vào đây
        )
        docs = [res['content'] for res in raw_results]
        if not docs: return ""

        # 2. Rerank
        if self.reranker:
            pairs = [[query, doc] for doc in docs]
            scores = self.reranker.predict(pairs)
            scored_docs = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
            # Lấy nhiều chunk hơn bình thường vì danh sách tiêu chuẩn rất dài
            final_docs = [doc for doc, score in scored_docs[:top_k_final]]
        else:
            final_docs = docs[:top_k_final]

        return "\n\n---\n\n".join(final_docs)

    # [CẬP NHẬT] Nhận tham số reference_doc
    def write(self, project_name: str, reference_doc: Optional[str] = None):
        logger.info(f"Đang soạn thảo Chương 1 cho: {project_name}. File mẫu: {reference_doc if reference_doc else 'Tự động'}")

        # --- BƯỚC 1: QUÉT DỮ LIỆU "YÊU CẦU KỸ THUẬT" (Collection: current_requirements) ---
        # Phần này KHÔNG dùng filter, vì ta cần tìm sự thật từ tất cả các file yêu cầu đã upload
        
        # 1.1. Pháp lý & Quy chuẩn chung
        q1 = "1.1.1. Các qui chuẩn, quy định: Nghị định 06/2021, Nghị định 14/2014, QCVN 01:2019, QCVN 02:2022, Quy phạm 11TCN."
        c1 = self._smart_retrieve(q1, "current_requirements", top_k_final=10)

        # 1.2. Công tác Đất & Bê tông
        q2 = "1.1.3 Các tiêu chuẩn về công tác đất (TCVN 4447, 9361). 1.1.4 Các tiêu chuẩn về công tác bê tông cốt thép và vữa: TCVN 4453, 9345, 9340, 8828, 9343, 9346, 4506 (Nước), 7570 (Cốt liệu), 2682 (Xi măng), 1651 (Thép), Que hàn, Vữa xây."
        c2 = self._smart_retrieve(q2, "current_requirements", top_k_final=20) 

        # 1.3. Kết cấu thép & Hoàn thiện
        q3 = "1.1.5 Các tiêu chuẩn về công tác kết cấu thép: TCVN 5575, Bu lông (1916, 1889), Vòng đệm, Mạ kẽm (ASTM A123), Hàn. 1.1.6 Công tác hoàn thiện nghiệm thu (TCVN 9377)."
        c3 = self._smart_retrieve(q3, "current_requirements", top_k_final=15)

        # 1.4. Phần Điện
        q4 = "1.2. Quy chuẩn, tiêu chuẩn về phần điện: QCVN QTĐ-5, QTĐ-7, QTĐ-8, IEC 61089, IEC 60305, Quy phạm trang bị điện."
        c4 = self._smart_retrieve(q4, "current_requirements", top_k_final=10)

        # --- BƯỚC 2: LẤY CẤU TRÚC MẪU (Collection: bidding_docs) ---
        
        # [QUAN TRỌNG] Tạo bộ lọc nếu người dùng chọn file
        style_filters = {"source": reference_doc} if reference_doc else None
        
        style_query = "Mẫu trình bày Chương I Cơ sở lập phương án tổ chức thi công, mục lục các tiêu chuẩn"
        
        # Truyền style_filters vào đây để chỉ lấy mẫu từ file được chọn
        style_context = self._smart_retrieve(
            query=style_query, 
            collection_name="bidding_docs", 
            top_k_final=3,
            filters=style_filters 
        )

        # --- BƯỚC 3: PROMPT (CHẾ ĐỘ COPY-PASTE) ---
        prompt = f"""
        Bạn là Kỹ sư hồ sơ thầu. Nhiệm vụ: Soạn thảo "CHƯƠNG I: CƠ SỞ LẬP PHƯƠNG ÁN TỔ CHỨC THI CÔNG".

        MỤC TIÊU: Tái tạo lại chính xác danh sách tiêu chuẩn từ HSMT vào trong cấu trúc của Biện pháp thi công.

        DỮ LIỆU ĐẦU VÀO (SOURCE OF TRUTH):
        1. [Pháp lý]: {c1}
        2. [Đất & Bê tông (Bao gồm cả Xi măng, Cát, Đá, Thép)]: {c2}
        3. [Kết cấu thép & Hoàn thiện]: {c3}
        4. [Điện]: {c4}

        CẤU TRÚC TRÌNH BÀY (TEMPLATE - Hãy học theo cách trình bày của đoạn này):
        {style_context}

        YÊU CẦU SOẠN THẢO NGHIÊM NGẶT:
        1. **Cấu trúc:** Tuân thủ các mục lớn I, II của TEMPLATE.
        2. **Nội dung:**
           - **KHÔNG TÓM TẮT.**
           - Nhiệm vụ của bạn là trích xuất (Extract) toàn bộ các dòng chứa tiêu chuẩn (TCVN, QCVN, IEC, ASTM...) từ DỮ LIỆU ĐẦU VÀO và sắp xếp vào đúng mục.
           - **Đặc biệt lưu ý mục Bê tông:** Phải liệt kê đủ các tiêu chuẩn về vật liệu đầu vào tìm thấy trong dữ liệu (Xi măng, Cốt liệu, Nước, Thép, Que hàn...). Nếu dữ liệu có TCVN 2682, TCVN 7570... thì bắt buộc phải đưa vào.
           - Giữ nguyên tên đầy đủ của tiêu chuẩn. Ví dụ: "TCVN 4453-95: Kết cấu bê tông và bê tông cốt thép toàn khối. Quy phạm thi công và nghiệm thu".

        3. **Sắp xếp:**
           I. CƠ SỞ THỰC HIỆN: Liệt kê các Luật, Nghị định, Quyết định, QCVN chung.
           II. CÁC TIÊU CHUẨN KỸ THUẬT ÁP DỤNG:
               1. Các tiêu chuẩn về công tác đất
               2. Các tiêu chuẩn về công tác bê tông cốt thép và vữa (Liệt kê cả tiêu chuẩn vật liệu vào đây)
               3. Các tiêu chuẩn về công tác kết cấu thép
               4. Các tiêu chuẩn về công tác hoàn thiện nghiệm thu và bàn giao
               5. Quy chuẩn, tiêu chuẩn về điện

        4. **Định dạng:** Markdown. Dùng gạch đầu dòng (-) cho từng tiêu chuẩn.

        BẮT ĐẦU:
        """

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0 # Nhiệt độ = 0 để model không "sáng tạo", chỉ copy
        )

        return response.choices[0].message.content
