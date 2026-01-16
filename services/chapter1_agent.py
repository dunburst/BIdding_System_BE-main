# # services/chapter1_agent.py
# import logging
# from typing import List, Optional
# from sentence_transformers import CrossEncoder
# from openai import OpenAI
# from services.retrieval_service import RetrievalService

# logger = logging.getLogger(__name__)

# class Chapter1Agent:
#     def __init__(self, retrieval_service: RetrievalService, openai_client: OpenAI):
#         self.retriever = retrieval_service
#         self.client = openai_client
#         self.model_name = "gpt-4o"
        
#         try:
#             # Model Rerank
#             self.reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
#             logger.info("Reranker model loaded successfully.")
#         except Exception as e:
#             logger.error(f"Failed to load Reranker: {e}")
#             self.reranker = None

#     # [UPDATE] Thêm tham số project_name vào hàm này
#     def _smart_retrieve(self, query: str, collection_name: str, project_name: Optional[str], top_k_fetch: int = 50, top_k_final: int = 15) -> str:
#         """
#         Lấy thật nhiều (50) -> Lọc lấy tinh hoa (15).
#         """
#         # 1. Retrieve (Truyền project_name xuống RetrievalService)
#         raw_results = self.retriever.search(
#             query=query, 
#             collection_name=collection_name, 
#             top_k=top_k_fetch,
#             project_name=project_name # <--- QUAN TRỌNG: Lọc theo dự án
#         )
        
#         # Nếu raw_results trả về là list dict, cần lấy content ra
#         docs = [res['content'] for res in raw_results]
        
#         if not docs: return ""

#         # 2. Rerank (Logic giữ nguyên)
#         if self.reranker:
#             pairs = [[query, doc] for doc in docs]
#             scores = self.reranker.predict(pairs)
#             scored_docs = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
#             final_docs = [doc for doc, score in scored_docs[:top_k_final]]
#         else:
#             final_docs = docs[:top_k_final]

#         return "\n\n---\n\n".join(final_docs)

#     def write(self, project_name: str):
#         logger.info(f"Đang soạn thảo Chương 1 (Chi tiết hóa) cho: {project_name}")

#         # --- BƯỚC 1: QUÉT DỮ LIỆU "YÊU CẦU KỸ THUẬT" (Collection: current_requirements) ---
#         # Mẹo: Dùng đúng từ khóa trong header của file PDF để vector search tìm chính xác vị trí.

#         # 1.1. Pháp lý & Quy chuẩn chung (Mục 1.1.1 trong PDF)
#         # Tìm các văn bản luật: 06/2021, 14/2014, QCVN 01, 02...
#         q1 = "1.1.1. Các qui chuẩn, quy định: Nghị định 06/2021, Nghị định 14/2014, QCVN 01:2019, QCVN 02:2022, Quy phạm 11TCN."
#         c1 = self._smart_retrieve(q1, "current_requirements", project_name=project_name, top_k_final=10)

#         # 1.2. Công tác Đất & Bê tông (Mục 1.1.3 & 1.1.4 trong PDF)
#         # QUAN TRỌNG: Liệt kê rõ các vật liệu để AI tìm được đoạn giữa của danh sách
#         q2 = "1.1.3 Các tiêu chuẩn về công tác đất (TCVN 4447, 9361). 1.1.4 Các tiêu chuẩn về công tác bê tông cốt thép và vữa: TCVN 4453, 9345, 9340, 8828, 9343, 9346, 4506 (Nước), 7570 (Cốt liệu), 2682 (Xi măng), 1651 (Thép), Que hàn, Vữa xây."
#         c2 = self._smart_retrieve(q2, "current_requirements", project_name=project_name, top_k_final=20) # Lấy 20 chunk để bao trọn danh sách dài

#         # 1.3. Kết cấu thép & Hoàn thiện (Mục 1.1.5 & 1.1.6 trong PDF)
#         q3 = "1.1.5 Các tiêu chuẩn về công tác kết cấu thép: TCVN 5575, Bu lông (1916, 1889), Vòng đệm, Mạ kẽm (ASTM A123), Hàn. 1.1.6 Công tác hoàn thiện nghiệm thu (TCVN 9377)."
#         c3 = self._smart_retrieve(q3, "current_requirements", project_name=project_name, top_k_final=15)

#         # 1.4. Phần Điện (Mục 1.2 trong PDF)
#         q4 = "1.2. Quy chuẩn, tiêu chuẩn về phần điện: QCVN QTĐ-5, QTĐ-7, QTĐ-8, IEC 61089, IEC 60305, Quy phạm trang bị điện."
#         c4 = self._smart_retrieve(q4, "current_requirements", project_name=project_name, top_k_final=10)

#         # --- BƯỚC 2: LẤY CẤU TRÚC MẪU (Collection: bidding_docs) ---
#         style_query = "Mẫu trình bày Chương I Cơ sở lập phương án tổ chức thi công, mục lục các tiêu chuẩn"
#         style_context = self._smart_retrieve(style_query, "bidding_docs", project_name=project_name, top_k_final=3)

#         # --- BƯỚC 3: PROMPT (CHẾ ĐỘ COPY-PASTE) ---
#         prompt = f"""
#         Bạn là Kỹ sư hồ sơ thầu. Nhiệm vụ: Soạn thảo "CHƯƠNG I: CƠ SỞ LẬP PHƯƠNG ÁN TỔ CHỨC THI CÔNG".

#         MỤC TIÊU: Tái tạo lại chính xác danh sách tiêu chuẩn từ HSMT vào trong cấu trúc của Biện pháp thi công.

#         DỮ LIỆU ĐẦU VÀO (SOURCE OF TRUTH):
#         1. [Pháp lý]: {c1}
#         2. [Đất & Bê tông (Bao gồm cả Xi măng, Cát, Đá, Thép)]: {c2}
#         3. [Kết cấu thép & Hoàn thiện]: {c3}
#         4. [Điện]: {c4}

#         CẤU TRÚC TRÌNH BÀY (TEMPLATE):
#         {style_context}

#         YÊU CẦU SOẠN THẢO NGHIÊM NGẶT:
#         1. **Cấu trúc:** Tuân thủ các mục lớn I, II của TEMPLATE.
#         2. **Nội dung:**
#            - **KHÔNG TÓM TẮT.**
#            - Nhiệm vụ của bạn là trích xuất (Extract) toàn bộ các dòng chứa tiêu chuẩn (TCVN, QCVN, IEC, ASTM...) từ DỮ LIỆU ĐẦU VÀO và sắp xếp vào đúng mục.
#            - **Đặc biệt lưu ý mục Bê tông:** Phải liệt kê đủ các tiêu chuẩn về vật liệu đầu vào tìm thấy trong dữ liệu (Xi măng, Cốt liệu, Nước, Thép, Que hàn...). Nếu dữ liệu có TCVN 2682, TCVN 7570... thì bắt buộc phải đưa vào.
#            - Giữ nguyên tên đầy đủ của tiêu chuẩn. Ví dụ: "TCVN 4453-95: Kết cấu bê tông và bê tông cốt thép toàn khối. Quy phạm thi công và nghiệm thu".

#         3. **Sắp xếp:**
#            I. CƠ SỞ THỰC HIỆN: Liệt kê các Luật, Nghị định, Quyết định, QCVN chung.
#            II. CÁC TIÊU CHUẨN KỸ THUẬT ÁP DỤNG:
#                1. Các tiêu chuẩn về công tác đất
#                2. Các tiêu chuẩn về công tác bê tông cốt thép và vữa (Liệt kê cả tiêu chuẩn vật liệu vào đây)
#                3. Các tiêu chuẩn về công tác kết cấu thép
#                4. Các tiêu chuẩn về công tác hoàn thiện nghiệm thu và bàn giao
#                5. Quy chuẩn, tiêu chuẩn về điện

#         4. **Định dạng:** Markdown. Dùng gạch đầu dòng (-) cho từng tiêu chuẩn.

#         BẮT ĐẦU:
#         """

#         response = self.client.chat.completions.create(
#             model=self.model_name,
#             messages=[{"role": "user", "content": prompt}],
#             temperature=0.0 # Nhiệt độ = 0 để model không "sáng tạo", chỉ copy
#         )

#         return response.choices[0].message.content

import logging
from typing import TypedDict, List, Dict, Any
from sentence_transformers import CrossEncoder

# LangGraph & LangChain imports
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from typing import Optional
from services.retrieval_service import RetrievalService

# Khởi tạo Logger
logger = logging.getLogger(__name__)

# --- 1. ĐỊNH NGHĨA STATE (TRẠNG THÁI) ---
# Lưu trữ dữ liệu chạy qua các node
class AgentState(TypedDict):
    project_name: str
    
    # Dữ liệu thô (Raw) sau khi Retrieve
    raw_legal: List[str]
    raw_concrete: List[str]
    raw_steel: List[str]
    raw_electric: List[str]
    raw_style: List[str]
    
    # Dữ liệu tinh (Refined) sau khi Rerank (Dạng chuỗi text để đưa vào prompt)
    c1: str
    c2: str
    c3: str
    c4: str
    style_context: str
    
    # Kết quả cuối cùng
    final_content: str

class Chapter1Agent:
    def __init__(self, retrieval_service: RetrievalService):
        self.retriever = retrieval_service
        
        # Cấu hình OpenAI (GPT-4o)
        self.llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0.0
        )

        # Load Reranker Model (Load 1 lần dùng mãi mãi)
        try:
            self.reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
            logger.info("✅ Reranker model loaded successfully.")
        except Exception as e:
            logger.error(f"❌ Failed to load Reranker: {e}")
            self.reranker = None

        # Xây dựng Graph
        self.workflow = self._build_graph()

    # --- HELPER: Hàm tìm kiếm nội bộ ---
    def _fetch_from_chroma(self, query: str, collection: str, top_k: int, project_name: Optional[str]) -> List[str]:
        """Hàm helper gọi xuống RetrievalService/ChromaService"""
        # Tạo bộ lọc theo dự án
        where_filter = {"project_name": project_name} if project_name else None
        
        # Gọi hàm query_collection (giả định bạn đã update ChromaService như yêu cầu trước)
        # Truy cập vào ChromaService bên trong RetrievalService
        results = self.retriever.chroma.query_collection(
            collection_name=collection,
            query_texts=[query],
            n_results=top_k,
            where=where_filter
        )
        # Trích xuất content
        return [item['content'] for item in results]

    # --- NODE 1: RETRIEVE (Tìm kiếm dữ liệu thô) ---
    def retrieve_node(self, state: AgentState):
        project_name = state["project_name"]
        logger.info(f"🔍 [NODE RETRIEVE] Đang tìm dữ liệu cho: {project_name}")

        # Định nghĩa các câu Query (Giữ nguyên logic của bạn)
        q1 = "1.1.1. Các qui chuẩn, quy định: Nghị định 06/2021, Nghị định 14/2014, QCVN 01:2019, QCVN 02:2022, Quy phạm 11TCN."
        q2 = "1.1.3 Các tiêu chuẩn về công tác đất (TCVN 4447, 9361). 1.1.4 Các tiêu chuẩn về công tác bê tông cốt thép và vữa: TCVN 4453, 9345, 9340, 8828, 9343, 9346, 4506 (Nước), 7570 (Cốt liệu), 2682 (Xi măng), 1651 (Thép), Que hàn, Vữa xây."
        q3 = "1.1.5 Các tiêu chuẩn về công tác kết cấu thép: TCVN 5575, Bu lông (1916, 1889), Vòng đệm, Mạ kẽm (ASTM A123), Hàn. 1.1.6 Công tác hoàn thiện nghiệm thu (TCVN 9377)."
        q4 = "1.2. Quy chuẩn, tiêu chuẩn về phần điện: QCVN QTĐ-5, QTĐ-7, QTĐ-8, IEC 61089, IEC 60305, Quy phạm trang bị điện."
        q_style = "Mẫu trình bày Chương I Cơ sở lập phương án tổ chức thi công, mục lục các tiêu chuẩn"

        # Thực hiện tìm kiếm song song (hoặc tuần tự)
        # Lấy top_k=50 như logic cũ để không sót
        return {
            "raw_legal": self._fetch_from_chroma(q1, "current_requirements", 50, project_name),
            "raw_concrete": self._fetch_from_chroma(q2, "current_requirements", 50, project_name),
            "raw_steel": self._fetch_from_chroma(q3, "current_requirements", 50, project_name),
            "raw_electric": self._fetch_from_chroma(q4, "current_requirements", 50, project_name),
            "raw_style": self._fetch_from_chroma(q_style, "bidding_docs", 5, None) # Mẫu không cần lọc theo project
        }

    # --- HELPER: Hàm Rerank nội bộ ---
    def _rerank_logic(self, query: str, docs: List[str], top_k: int) -> str:
        """Hàm thực hiện rerank và join thành string"""
        if not docs: return ""
        if not self.reranker: return "\n\n---\n\n".join(docs[:top_k])

        pairs = [[query, doc] for doc in docs]
        scores = self.reranker.predict(pairs)
        scored_docs = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
        final_docs = [doc for doc, score in scored_docs[:top_k]]
        
        return "\n\n---\n\n".join(final_docs)

    # --- NODE 2: RERANK (Lọc dữ liệu tinh hoa) ---
    def rerank_node(self, state: AgentState):
        logger.info("⚖️ [NODE RERANK] Đang chấm điểm và lọc tài liệu...")
        
        # Query dùng để đối chiếu khi rerank (Copy lại từ Retrieve)
        q1 = "1.1.1. Các qui chuẩn, quy định: Nghị định 06/2021, Nghị định 14/2014..."
        q2 = "1.1.3 Các tiêu chuẩn về công tác đất... Bê tông... Xi măng... Thép..."
        q3 = "1.1.5 Các tiêu chuẩn về công tác kết cấu thép... Hoàn thiện..."
        q4 = "1.2. Quy chuẩn, tiêu chuẩn về phần điện..."
        
        # Lọc từng nhóm (Giữ nguyên top_k_final theo logic cũ)
        return {
            "c1": self._rerank_logic(q1, state["raw_legal"], 10),
            "c2": self._rerank_logic(q2, state["raw_concrete"], 20), # Lấy 20 vì danh sách dài
            "c3": self._rerank_logic(q3, state["raw_steel"], 15),
            "c4": self._rerank_logic(q4, state["raw_electric"], 10),
            "style_context": "\n\n".join(state["raw_style"][:3]) # Style chỉ cần lấy top 3
        }

    # --- NODE 3: GENERATE (Viết bài) ---
    def generate_node(self, state: AgentState):
        logger.info("✍️ [NODE GENERATE] Đang gọi OpenAI viết bài...")
        
        # Prompt (COPY NGUYÊN BẢN TỪ CODE CỦA BẠN)
        prompt = f"""
        Bạn là Kỹ sư hồ sơ thầu. Nhiệm vụ: Soạn thảo "CHƯƠNG I: CƠ SỞ LẬP PHƯƠNG ÁN TỔ CHỨC THI CÔNG".

        MỤC TIÊU: Tái tạo lại chính xác danh sách tiêu chuẩn từ HSMT vào trong cấu trúc của Biện pháp thi công.

        DỮ LIỆU ĐẦU VÀO (SOURCE OF TRUTH):
        1. [Pháp lý]: {state['c1']}
        2. [Đất & Bê tông (Bao gồm cả Xi măng, Cát, Đá, Thép)]: {state['c2']}
        3. [Kết cấu thép & Hoàn thiện]: {state['c3']}
        4. [Điện]: {state['c4']}

        CẤU TRÚC TRÌNH BÀY (TEMPLATE):
        {state['style_context']}

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

        messages = [
            SystemMessage(content="Bạn là trợ lý AI chuyên về thầu xây dựng."),
            HumanMessage(content=prompt)
        ]

        response = self.llm.invoke(messages)
        return {"final_content": response.content}

    # --- XÂY DỰNG GRAPH ---
    def _build_graph(self):
        workflow = StateGraph(AgentState)
        
        # Thêm các Node
        workflow.add_node("retrieve", self.retrieve_node)
        workflow.add_node("rerank", self.rerank_node)
        workflow.add_node("generate", self.generate_node)
        
        # Nối các Node (Tuần tự)
        workflow.set_entry_point("retrieve")
        workflow.add_edge("retrieve", "rerank")
        workflow.add_edge("rerank", "generate")
        workflow.add_edge("generate", END)
        
        return workflow.compile()

    # --- HÀM MAIN ---
    def write(self, project_name: str) -> str:
        """Hàm kích hoạt Graph"""
        # Khởi tạo state ban đầu
        inputs = {
            "project_name": project_name,
            "raw_legal": [], "raw_concrete": [], "raw_steel": [], "raw_electric": [], "raw_style": [],
            "c1": "", "c2": "", "c3": "", "c4": "", "style_context": "",
            "final_content": ""
        }
        
        # Chạy Graph
        result = self.workflow.invoke(inputs) #type: ignore
        return result["final_content"]