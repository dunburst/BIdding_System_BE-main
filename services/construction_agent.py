import operator
from typing import Annotated, List, TypedDict, Optional, Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver 
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field
from langchain_core.runnables import RunnableConfig

# Import các service hiện có
from services.retrieval_service import RetrievalService
from services.chroma_service import ChromaService

# --- 1. ĐỊNH NGHĨA STATE & SCHEMA ---

class Section(BaseModel):
    id: int
    title: str = Field(description="Tên chương/mục")
    search_query: str = Field(description="Từ khóa tìm kiếm RAG")
    content: str = Field(default="", description="Nội dung đã viết xong")

class ProposalOutline(BaseModel):
    sections: List[Section] = Field(description="Danh sách dàn ý")

# [NEW] Cấu trúc phiếu đánh giá của Reviewer
class ReviewFeedback(BaseModel):
    is_approved: bool = Field(description="True nếu bài đạt yêu cầu, False nếu cần sửa")
    score: int = Field(description="Điểm chất lượng trên thang 10")
    critique: str = Field(description="Nhận xét chi tiết về lỗi sai (nếu có)")
    suggestions: str = Field(description="Hướng dẫn cụ thể để Writer sửa bài")

class AgentState(TypedDict):
    project_name: str
    requirements_collection: str   
    reference_doc_name: Optional[str]        
    
    outline: List[Section]         
    current_section_idx: int       
    final_document: str            
    
    # [NEW] Biến phục vụ vòng lặp Review
    revision_count: int      # Đếm số lần đã sửa (max 3 lần)
    current_feedback: str    # Lời phê bình hiện tại

# [QUAN TRỌNG] KHỞI TẠO BỘ NHỚ TOÀN CỤC (GLOBAL)
# Để nó không bị reset mỗi khi gọi API mới
global_memory = MemorySaver()

# --- 2. CLASS AGENT CHÍNH ---

class ConstructionDraftingAgent:
    def __init__(self, retrieval_service: RetrievalService):
        self.retriever = retrieval_service
        self.llm = ChatOpenAI(model="gpt-4o", temperature=0)
        
        # Output Parsers
        self.planner_llm = self.llm.with_structured_output(ProposalOutline)
        self.reviewer_llm = self.llm.with_structured_output(ReviewFeedback)

        # Sử dụng bộ nhớ toàn cục
        self.memory = global_memory 
        self.app = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(AgentState)

        # Các Node
        workflow.add_node("planner", self.planner_node)
        workflow.add_node("writer", self.writer_node)
        workflow.add_node("reviewer", self.reviewer_node) # Node Reviewer mới

        # Luồng đi
        workflow.set_entry_point("planner")
        workflow.add_edge("planner", "writer")
        workflow.add_edge("writer", "reviewer") # Viết xong nộp cho Reviewer

        # Điều hướng dựa trên kết quả Review
        workflow.add_conditional_edges(
            "reviewer",
            self.router_logic,
            {
                "revise": "writer",  # Chưa đạt -> Quay lại sửa
                "next": "writer",    # Đạt -> Viết mục tiếp theo
                "end": END           # Hết bài
            }
        )

        return workflow.compile(
            checkpointer=self.memory,
            interrupt_after=["planner"] 
        )

    # --- 3. LOGIC CÁC NODE ---

    def planner_node(self, state: AgentState):
        """Bước 1: Lập dàn ý"""
        print(f"🏗️ [Planner] Đang lập dàn ý cho dự án: {state['project_name']}...")

        # Tìm file mẫu để học cấu trúc
        sample_filter = {"source": state['reference_doc_name']} if state['reference_doc_name'] else None
        context_str = ""
        if state['reference_doc_name']:
            print(f"   - Đang đọc cấu trúc từ file mẫu: {state['reference_doc_name']}")
            try:
                sample_docs = self.retriever.search(
                    query="Mục lục, danh sách các chương",
                    collection_name="bidding_docs",
                    top_k=5,
                    filters=sample_filter
                )
                context_str = "\n".join([doc['content'] for doc in sample_docs])
            except Exception as e:
                print(f"⚠️ Lỗi đọc file mẫu: {e}")

        prompt = f"""
        Bạn là Kiến trúc sư Hồ sơ thầu của PC1. Hãy lập Dàn ý (Outline) cho dự án: "{state['project_name']}".
        
        THAM KHẢO CẤU TRÚC (Nếu có):
        {context_str}
        
        NHIỆM VỤ:
        1. Tạo danh sách các Chương/Mục lớn.
        2. Sinh search_query cụ thể để tìm yêu cầu kỹ thuật tương ứng (VD: "Quy trình thi công móng", "Tiêu chuẩn nghiệm thu cột thép").
        """

        try:
            res = self.planner_llm.invoke(prompt)
            # sections = res['sections'] 
            # Kiểm tra kiểu dữ liệu để chắc chắn
            if isinstance(res, dict):
                sections = res['sections'] # Trường hợp hiếm nếu LLM trả về dict
            else:
                sections = res.sections    # <--- SỬA THÀNH CÁI NÀY (Dùng dấu chấm)
        except Exception as e:
            print(f"⚠️ Lỗi Planner: {e}. Dùng dàn ý default.")
            sections = [
                Section(id=1, title="Giới thiệu chung", search_query="Tổng quan dự án"),
                Section(id=2, title="Biện pháp thi công", search_query="Yêu cầu kỹ thuật")
            ]

        print(f"✅ Đã lập {len(sections)} mục.")
        return {
            "outline": sections,
            "current_section_idx": 0,
            "final_document": "",
            "revision_count": 0,
            "current_feedback": ""
        }

    def writer_node(self, state: AgentState):
        """Bước 2: Viết nội dung (Biết sửa theo Feedback)"""
        idx = state['current_section_idx']
        if idx >= len(state['outline']):
            return {"current_section_idx": idx}

        current_section = state['outline'][idx]
        feedback = state.get('current_feedback', "")
        
        if feedback:
            print(f"✍️ [Writer] Đang SỬA LẠI mục: {current_section.title} (Lần {state['revision_count']})")
            print(f"   ⚠️ Feedback: {feedback}")
        else:
            print(f"✍️ [Writer] Viết mới mục: {current_section.title}")

        # RAG Search
        tech_specs = self.retriever.search(
            query=current_section.search_query,
            collection_name=state['requirements_collection'],
            top_k=7
        )
        tech_context = "\n---\n".join([f"HSMT: {res['content']}" for res in tech_specs])

        # Prompt
        prompt = f"""
        Dự án: "{state['project_name']}"
        Mục: "{current_section.title}"
        
        DỮ LIỆU ĐẦU VÀO (HSMT):
        {tech_context}
        
        YÊU CẦU: 
        - Viết nội dung chi tiết, chuyên nghiệp, định dạng Markdown.
        - Trích dẫn số liệu cụ thể.
        """
        
        # Nhồi Feedback vào Prompt để sửa lỗi
        if feedback:
            prompt += f"""
            !!! CẢNH BÁO TỪ REVIEWER:
            Bài trước bị từ chối vì: "{feedback}".
            HÃY SỬA LẠI ĐỂ KHẮC PHỤC LỖI TRÊN.
            """

        msg = self.llm.invoke(prompt)
        raw_content = msg.content
        if isinstance(raw_content, list):
            # Nếu trả về list (thường gặp ở GPT-4o), nối lại thành chuỗi
            final_content = "\n".join([str(item) for item in raw_content])
        else:
            final_content = str(raw_content)

        # Lưu vào Pydantic object
        current_section.content = final_content
        new_outline = state['outline']
        new_outline[idx] = current_section
        
        return {"outline": new_outline}

    def reviewer_node(self, state: AgentState):
        """Bước 3: QA/QC Review (Chấm điểm khắt khe theo chuẩn PC1)"""
        idx = state['current_section_idx']
        if idx >= len(state['outline']): return {}

        current_section = state['outline'][idx]
        print(f"🧐 [Reviewer] Đang thẩm định mục: {current_section.title}...")

        # --- BỘ TIÊU CHÍ (Dựa trên file mẫu 7. BPTCTC_G7_FN.pdf) ---
        criteria = """
        Bạn là Chuyên gia Kiểm soát Chất lượng (QA/QC) của Tổng thầu. 
        Hãy đóng vai người cực kỳ khó tính, soi xét từng chi tiết.
        
        TIÊU CHÍ BẮT BUỘC (CRITICAL):
        
        1. **Cơ sở pháp lý & Tiêu chuẩn:**
           - Có trích dẫn TCVN, QCVN, Nghị định (06/2021/NĐ-CP...) không?
           - Ví dụ: Bê tông (TCVN 4453), Đất (TCVN 4447), An toàn (NĐ 14/2014).
           - KHÔNG CÓ -> TỪ CHỐI (REVISE).

        2. **Thông số kỹ thuật định lượng:**
           - Có con số cụ thể không? (VD: Cẩu 25 tấn, mác 200, sai số ±10mm).
           - Nếu chỉ viết văn xuôi chung chung -> TỪ CHỐI (REVISE).

        3. **Quy trình nghiệm thu:**
           - Phải có bước "Nghiệm thu nội bộ" trước khi "Nghiệm thu với Chủ đầu tư".
           
        4. **Hình thức:** - Markdown chuẩn (Bold tiêu đề, List gạch đầu dòng).
        """

        prompt = f"""
        {criteria}

        BÀI VIẾT CẦN THẨM ĐỊNH:
        ---
        {current_section.content}
        ---

        Output JSON: {{ "is_approved": boolean, "score": int, "critique": "...", "suggestions": "..." }}
        """

        raw_res = self.reviewer_llm.invoke(prompt)

        # 2. Kiểm tra và ép kiểu về Object ReviewFeedback
        if isinstance(raw_res, dict):
            # Nếu là dict -> convert sang Object
            feedback = ReviewFeedback(**raw_res)
        else:
            # Nếu đã là Object -> dùng luôn
            feedback = raw_res

        # Logic chống lặp: Nếu đã sửa 2 lần mà vẫn chưa đạt -> Cho qua (Duyệt tạm)
        if not feedback.is_approved and state['revision_count'] >= 2:
            print(f"⚠️ [Reviewer] Bài chưa hoàn hảo ({feedback.score}/10) nhưng đã sửa 2 lần. DUYỆT TẠM.")
            feedback.is_approved = True
            feedback.critique += " (Đã duyệt ngoại lệ)"

        if feedback.is_approved:
            print(f"✅ [Reviewer] DUYỆT! (Điểm: {feedback.score}/10)")
            new_doc = state['final_document'] + f"\n\n# {current_section.title}\n\n{current_section.content}"
            return {
                "current_section_idx": idx + 1, # Tăng index sang mục sau
                "revision_count": 0,            # Reset đếm sửa
                "current_feedback": "",         # Xóa feedback
                "final_document": new_doc
            }
        else:
            print(f"❌ [Reviewer] TỪ CHỐI! (Điểm: {feedback.score}/10)")
            print(f"   Lý do: {feedback.critique}")
            return {
                "revision_count": state['revision_count'] + 1, # Tăng số lần sửa
                "current_feedback": f"Lỗi: {feedback.critique}. YÊU CẦU: {feedback.suggestions}"
            }

    def router_logic(self, state: AgentState):
        """Điều hướng luồng đi"""
        # Nếu có feedback -> Quay lại Writer sửa (Revise)
        if state.get('current_feedback'):
            return "revise"
        
        # Nếu đã duyệt -> Kiểm tra xem hết bài chưa
        if state['current_section_idx'] >= len(state['outline']):
            return "end"
        
        # Chưa hết -> Viết mục tiếp theo
        return "next"

    # --- 4. HÀM RUN (HỖ TRỢ RESUME AN TOÀN) ---
    def run(self, thread_id: str, project_name: str = "", reference_doc: Optional[str] = None, user_feedback_outline: Optional[List[Dict]] = None):
        # Sửa 2: Khai báo rõ kiểu RunnableConfig
        config: RunnableConfig = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 150
        }
        
        # CASE 2: RESUME (User gửi Dàn ý đã duyệt)
        if user_feedback_outline:
            print(f"▶️ [Resume] Nhận dàn ý (Thread: {thread_id})...")
            
            # Kiểm tra state cũ
            current_state = self.app.get_state(config)
            
            # Khôi phục nếu mất trí nhớ (Server restart)
            if not current_state.values:
                print("⚠️ Khôi phục session cũ...")
                if not project_name:
                    return {"status": "error", "message": "Mất kết nối session. Vui lòng chạy lại từ đầu."}
                
                self.app.update_state(config, {
                    "project_name": project_name,
                    "requirements_collection": "current_requirements",
                    "reference_doc_name": reference_doc,
                    "current_section_idx": 0,
                    "final_document": ""
                })

            # Cập nhật dàn ý & Reset Review
            updated_sections = [Section(**s) for s in user_feedback_outline]
            self.app.update_state(config, {
                "outline": updated_sections,
                "revision_count": 0,
                "current_feedback": ""
            })
            
            # Chạy tiếp
            result = self.app.invoke(None, config=config)
            
            return {
                "status": "completed",
                "type": "full_document",
                "content": result['final_document']
            }
            
        # CASE 1: START NEW
        else:
            print(f"🚀 [Start] Bắt đầu mới (Thread: {thread_id})...")
            initial_state : AgentState= {
                "project_name": project_name,
                "requirements_collection": "current_requirements",
                "reference_doc_name": reference_doc,
                "outline": [],
                "current_section_idx": 0,
                "final_document": "",
                "revision_count": 0, 
                "current_feedback": ""
            }
            
            self.app.invoke(initial_state, config=config)
            
            snapshot = self.app.get_state(config)
            current_outline = snapshot.values.get("outline", [])
            
            return {    
                "status": "paused",
                "type": "outline_review",
                "content": [s.model_dump() for s in current_outline]
            }