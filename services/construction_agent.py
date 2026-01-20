import operator
from typing import Annotated, List, TypedDict, Optional, Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver 
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

# Import các service
from services.retrieval_service import RetrievalService
from services.chroma_service import ChromaService
from services.visual_retrieval_service import VisualRetrievalService

# --- 1. ĐỊNH NGHĨA STATE & SCHEMA ---

class Section(BaseModel):
    id: int
    title: str = Field(description="Tên chương/mục")
    search_query: str = Field(description="Từ khóa tìm kiếm (Text & Visual)")
    content: str = Field(default="", description="Nội dung đã viết xong")

class ProposalOutline(BaseModel):
    sections: List[Section] = Field(description="Danh sách dàn ý")

class ReviewFeedback(BaseModel):
    is_approved: bool = Field(description="True nếu đạt, False nếu cần sửa")
    score: int = Field(description="Điểm chất lượng /10")
    critique: str = Field(description="Nhận xét lỗi")
    suggestions: str = Field(description="Gợi ý sửa")

class AgentState(TypedDict):
    project_name: str
    requirements_collection: str   
    reference_doc_name: Optional[str]        
    outline: List[Section]         
    current_section_idx: int       
    final_document: str            
    revision_count: int      
    current_feedback: str    

# KHỞI TẠO BỘ NHỚ TOÀN CỤC
global_memory = MemorySaver()

# --- 2. CLASS AGENT CHÍNH ---

class ConstructionDraftingAgent:
    def __init__(self, retrieval_service: RetrievalService, visual_service: VisualRetrievalService):
        self.retriever = retrieval_service
        self.visual_retriever = visual_service
        self.llm = ChatOpenAI(model="gpt-4o", temperature=0)
        
        self.planner_llm = self.llm.with_structured_output(ProposalOutline)
        self.reviewer_llm = self.llm.with_structured_output(ReviewFeedback)

        self.memory = global_memory 
        self.app = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(AgentState)

        workflow.add_node("planner", self.planner_node)
        workflow.add_node("writer", self.writer_node)
        workflow.add_node("reviewer", self.reviewer_node) 

        workflow.set_entry_point("planner")
        workflow.add_edge("planner", "writer")
        workflow.add_edge("writer", "reviewer") 

        workflow.add_conditional_edges(
            "reviewer",
            self.router_logic,
            {
                "revise": "writer",
                "next": "writer", 
                "end": END           
            }
        )

        return workflow.compile(
            checkpointer=self.memory,
            interrupt_after=["planner"] 
        )

    # --- 3. LOGIC CÁC NODE ---

    def planner_node(self, state: AgentState):
        """Bước 1: Lập dàn ý"""
        print(f"🏗️ [Planner] Đang lập dàn ý: {state['project_name']}...")
        
        sample_filter = {"source": state['reference_doc_name']} if state['reference_doc_name'] else None
        context_str = ""
        if state['reference_doc_name']:
            try:
                # Tìm mục lục từ kho mẫu (bidding_docs)
                sample_docs = self.retriever.search("Mục lục danh sách chương", "bidding_docs", 5, filters=sample_filter)
                context_str = "\n".join([doc['content'] for doc in sample_docs])
            except: pass

        prompt = f"""
        Lập Dàn ý Biện pháp thi công cho dự án: "{state['project_name']}".
        THAM KHẢO CẤU TRÚC MẪU:
        {context_str}
        
        NHIỆM VỤ:
        1. Tạo danh sách các mục chính.
        2. Sinh 'search_query' dùng để tìm cả Text (TCVN) và Ảnh (Bản vẽ).
        """
        try:
            res = self.planner_llm.invoke(prompt)
            sections = res.sections 
        except:
            sections = [Section(id=1, title="Giới thiệu", search_query="Tổng quan dự án")]

        return {
            "outline": sections,
            "current_section_idx": 0,
            "final_document": "",
            "revision_count": 0,
            "current_feedback": ""
        }

    def writer_node(self, state: AgentState):
        """Bước 2: Viết nội dung (Multimodal: Text + Vision)"""
        idx = state['current_section_idx']
        if idx >= len(state['outline']): return {"current_section_idx": idx}

        current_section = state['outline'][idx]
        feedback = state.get('current_feedback', "")
        
        if feedback:
            print(f"✍️ [Writer] Đang SỬA LẠI mục: {current_section.title} (Lần {state['revision_count']})")
        else:
            print(f"✍️ [Writer] Viết mới mục: {current_section.title}")

        # --- LOGIC TÌM KIẾM KÉP (QUAN TRỌNG) ---
        
        # 1. Tìm trong HSMT (Bắt buộc phải lọc theo đúng Project Name)
        project_filter = {"project_name": state['project_name']}
        
        req_docs = self.retriever.search(
            query=current_section.search_query,
            collection_name="current_requirements", # Tìm trong yêu cầu
            top_k=4,
            filters=project_filter # <--- LỌC CHÍNH XÁC DỰ ÁN
        )
        
        # 2. Tìm trong Mẫu (Bidding Docs) - Không cần lọc project, để lấy kiến thức chung
        template_docs = self.retriever.search(
            query=current_section.search_query,
            collection_name="bidding_docs", # Tìm trong kho mẫu
            top_k=2
        )
        
        # Gộp context lại
        context_parts = []
        if req_docs:
            context_parts.append("=== YÊU CẦU TỪ HỒ SƠ MỜI THẦU (QUAN TRỌNG NHẤT) ===")
            context_parts.extend([f"- {r['content']}" for r in req_docs])
            
        if template_docs:
            context_parts.append("=== THAM KHẢO BIỆN PHÁP MẪU ===")
            context_parts.extend([f"- {r['content']}" for r in template_docs])
            
        text_context = "\n\n".join(context_parts)

        # 3. Tìm Hình ảnh (LitePali)
        # (LitePali hiện tại tìm chung trong index, LLM sẽ tự lọc ngữ cảnh qua hình ảnh)
        visual_docs = self.visual_retriever.search_visuals(current_section.search_query, top_k=2)

        # Cấu trúc Message
        messages = []
        messages.append(SystemMessage(content=f"""
        Bạn là Kỹ sư Biện pháp thi công chuyên nghiệp.
        Dự án: "{state['project_name']}". Mục: "{current_section.title}".
        
        DỮ LIỆU THAM KHẢO:
        {text_context}
        """))

        user_content = [
            {"type": "text", "text": f"""
            Hãy viết nội dung chi tiết cho mục này.
            
            YÊU CẦU:
            1. Ưu tiên tuân thủ các yêu cầu trong HSMT (nếu có).
            2. Sử dụng văn phong từ tài liệu mẫu để viết cho chuyên nghiệp.
            3. Nếu có bản vẽ/hình ảnh đính kèm, hãy mô tả phương án thi công dựa trên đó.
            4. Trình bày Markdown chuyên nghiệp.
            """}
        ]
        
        if feedback:
            user_content[0]["text"] += f"\n\n!!! CẢNH BÁO TỪ REVIEWER: Bài trước bị chê vì: '{feedback}'. HÃY SỬA LẠI."

        if visual_docs:
            print(f"   📷 Tìm thấy {len(visual_docs)} ảnh minh họa.")
            for doc in visual_docs:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{doc['base64']}"}
                })

        messages.append(HumanMessage(content=user_content))

        # Invoke LLM
        msg = self.llm.invoke(messages)
        current_section.content = msg.content
        
        new_outline = list(state['outline'])
        new_outline[idx] = current_section
        
        return {"outline": new_outline}

    def reviewer_node(self, state: AgentState):
        """Bước 3: QA/QC Review"""
        idx = state['current_section_idx']
        if idx >= len(state['outline']): return {}

        current_section = state['outline'][idx]
        print(f"🧐 [Reviewer] Đang chấm: {current_section.title}...")

        criteria = """
        1. **Tuân thủ:** Có bám sát yêu cầu kỹ thuật (nếu có trong context) không?
        2. **Chuyên nghiệp:** Văn phong có giống hồ sơ thầu xây dựng không?
        3. **Chi tiết:** Có đưa ra số liệu/quy trình cụ thể không? (Tránh viết chung chung).
        """
        prompt = f"{criteria}\n\nNỘI DUNG:\n{current_section.content}"

        feedback: ReviewFeedback = self.reviewer_llm.invoke(prompt)

        if not feedback.is_approved and state['revision_count'] >= 2:
            print(f"⚠️ [Reviewer] Duyệt tạm (Hết lượt sửa).")
            feedback.is_approved = True

        if feedback.is_approved:
            print(f"✅ [Reviewer] DUYỆT! ({feedback.score}đ)")
            new_doc = state['final_document'] + f"\n\n# {current_section.title}\n\n{current_section.content}"
            return {
                "current_section_idx": idx + 1,
                "revision_count": 0,
                "current_feedback": "",
                "final_document": new_doc
            }
        else:
            print(f"❌ [Reviewer] TỪ CHỐI! ({feedback.score}đ) - {feedback.critique}")
            return {
                "revision_count": state['revision_count'] + 1,
                "current_feedback": f"{feedback.critique}. Gợi ý: {feedback.suggestions}"
            }

    def router_logic(self, state: AgentState):
        if state.get('current_feedback'): return "revise"
        if state['current_section_idx'] >= len(state['outline']): return "end"
        return "next"

    def run(self, thread_id: str, project_name: str = "", reference_doc: Optional[str] = None, user_feedback_outline: List[Dict] = None):
        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 150 
        }
        
        if user_feedback_outline:
            print(f"▶️ [Resume] Thread: {thread_id}...")
            current_state = self.app.get_state(config)
            if not current_state.values:
                print("⚠️ Khôi phục session...")
                self.app.update_state(config, {
                    "project_name": project_name,
                    "requirements_collection": "current_requirements",
                    "reference_doc_name": reference_doc,
                    "current_section_idx": 0,
                    "final_document": ""
                })

            updated_sections = [Section(**s) for s in user_feedback_outline]
            self.app.update_state(config, {
                "outline": updated_sections,
                "revision_count": 0,
                "current_feedback": ""
            })
            
            result = self.app.invoke(None, config=config)
            return {"status": "completed", "type": "full_document", "content": result['final_document']}
            
        else:
            print(f"🚀 [Start] Thread: {thread_id}...")
            initial_state = {
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
            return {"status": "paused", "type": "outline_review", "content": [s.model_dump() for s in snapshot.values.get("outline", [])]}