import operator
import os
import json
from typing import Annotated, List, TypedDict, Optional, Dict, Any, Union
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver 
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage, AIMessage
from pydantic import BaseModel, Field, SecretStr
from langchain_core.runnables import RunnableConfig
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.exceptions import OutputParserException

# --- IMPORT SERVICES ---
# Đảm bảo bạn đã có các file này
from app.integrations.ai.data_processing.retrieval_service import RetrievalService
from app.integrations.ai.data_processing.visual_retrieval_service import VisualRetrievalService

# ==========================================
# 1. SCHEMA
# ==========================================

class Section(BaseModel):
    id: int
    title: str = Field(description="Tên chương/mục")
    search_query: str = Field(description="Từ khóa tìm kiếm")
    content: str = Field(default="", description="Nội dung chi tiết")

class ProposalOutline(BaseModel):
    sections: List[Section] = Field(description="Danh sách các mục")

class ReviewFeedback(BaseModel):
    is_approved: bool = Field(description="True nếu đạt")
    score: int = Field(description="Điểm /10")
    critique: str = Field(description="Nhận xét lỗi")
    suggestions: str = Field(description="Gợi ý sửa")

class RequirementsAnalysis(BaseModel):
    is_sufficient: bool = Field(description="True nếu đủ thông tin")
    missing_info_question: Optional[str] = Field(description="Câu hỏi nếu thiếu")
    extracted_details: Optional[str] = Field(description="Tóm tắt thông tin")

# ==========================================
# 2. STATE
# ==========================================

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add] 
    requirements_gathered: bool
    project_name: str
    project_details: str
    reference_doc_name: Optional[str]        
    outline: List[Section]         
    current_section_idx: int       
    final_document: str            
    revision_count: int      
    current_feedback: str          

# ==========================================
# 3. CLASS AGENT (FIXED TYPES)
# ==========================================

global_memory = MemorySaver()

class ConstructionDraftingAgent:
    def __init__(self, retrieval_service: RetrievalService, visual_service: VisualRetrievalService):
        self.retriever = retrieval_service
        self.visual_retriever = visual_service
        
        print("🤖 Initializing DeepSeek Agent...")
        
        deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "sk-b2086419ba0a4219b7d322ae0c45db26")
        
        self.llm = ChatOpenAI(
            model="deepseek-chat",
            api_key=SecretStr(deepseek_api_key) if deepseek_api_key else None,
            base_url="https://api.deepseek.com",
            temperature=0.1,
            model_kwargs={
                "max_tokens": 4096 
            } 
        )
        
        self.analyst_parser = PydanticOutputParser(pydantic_object=RequirementsAnalysis)
        self.planner_parser = PydanticOutputParser(pydantic_object=ProposalOutline)
        self.reviewer_parser = PydanticOutputParser(pydantic_object=ReviewFeedback)

        self.memory = global_memory 
        self.app = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(AgentState)
        
        workflow.add_node("requirements_analyst", self.requirements_node)
        workflow.add_node("planner", self.planner_node)
        workflow.add_node("writer", self.writer_node)
        workflow.add_node("reviewer", self.reviewer_node) 

        workflow.set_entry_point("requirements_analyst")

        workflow.add_conditional_edges("requirements_analyst", self.route_requirements, {"ask_user": END, "proceed": "planner"})
        workflow.add_edge("planner", "writer")
        workflow.add_edge("writer", "reviewer")
        workflow.add_conditional_edges("reviewer", self.route_review, {"revise": "writer", "next": "writer", "completed": END})

        return workflow.compile(checkpointer=self.memory)

    # ==========================================
    # 4. HELPERS (QUAN TRỌNG: FIX LỖI TYPE)
    # ==========================================
    
    def _get_text_content(self, content: Union[str, List[Union[str, Dict]]]) -> str:
        """Hàm an toàn để lấy text từ content (xử lý cả multimodal list)"""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text = ""
            for item in content:
                if isinstance(item, str):
                    text += item
                elif isinstance(item, dict):
                    text += item.get("text", "")
            return text
        return str(content)

    def _safe_parse(self, raw_content: Union[str, List], parser: PydanticOutputParser):
        """Hàm parse JSON an toàn"""
        text_content = self._get_text_content(raw_content).strip()
        
        # Clean Markdown
        if "```json" in text_content:
            text_content = text_content.split("```json")[1].split("```")[0].strip()
        elif "```" in text_content:
            text_content = text_content.split("```")[1].strip()
            
        try:
            return parser.parse(text_content)
        except:
            try:
                data = json.loads(text_content)
                return parser.pydantic_object(**data)
            except:
                return None

    # ==========================================
    # 5. NODES (FIXED LOGIC)
    # ==========================================

    def requirements_node(self, state: AgentState):
        print("🕵️ [Analyst] Checking requirements...")
        if state.get("requirements_gathered") and not state.get("current_feedback"): return {} 

        messages = state['messages']
        last_msg_content = self._get_text_content(messages[-1].content) if messages else ""
        
        format_instructions = self.analyst_parser.get_format_instructions()
        prompt = f"""
        Nhiệm vụ: Phân tích xem User đã cung cấp 'Tên dự án' chưa.
        
        User Input: "{last_msg_content}"
        
        {format_instructions}
        """
        
        try:
            res = self.llm.invoke([SystemMessage(content=prompt)] + messages)
            analysis = self._safe_parse(res.content, self.analyst_parser)
        except:
            analysis = None

        # --- FALLBACK LOGIC (ĐÃ FIX LỖI .lower()) ---
        if not analysis:
            # Bây giờ last_msg_content chắc chắn là string nên .lower() an toàn
            if len(last_msg_content) > 5 and "dự án" in last_msg_content.lower():
                print(f"⚠️ Auto-accepting project name from text: {last_msg_content[:20]}...")
                return {
                    "requirements_gathered": True,
                    "project_name": last_msg_content,
                    "project_details": last_msg_content,
                    "current_feedback": ""
                }
            else:
                return {
                    "requirements_gathered": False, 
                    "messages": [AIMessage(content="Tôi chưa rõ tên dự án. Vui lòng ghi 'Dự án: [Tên]'")]
                }

        if analysis.is_sufficient:
            print(f"✅ [Analyst] OK: {analysis.extracted_details}")
            return {
                "requirements_gathered": True,
                "project_name": analysis.extracted_details or "Project",
                "project_details": analysis.extracted_details or "",
                "current_feedback": "" 
            }
        else:
            return {"requirements_gathered": False, "messages": [AIMessage(content=str(analysis.missing_info_question))]}

    def planner_node(self, state: AgentState):
        print(f"🏗️ [Planner] Planning...")
        prompt = f"Lập Dàn ý cho: {state['project_details']}.\n{self.planner_parser.get_format_instructions()}"
        res = self.llm.invoke(prompt)
        plan = self._safe_parse(res.content, self.planner_parser)
        
        if not plan:
            default_sections = [Section(id=1, title="Tổng quan", search_query=state['project_name'])]
            return {"outline": default_sections, "current_section_idx": 0}

        return {"outline": plan.sections, "current_section_idx": 0, "final_document": "", "revision_count": 0}

    def writer_node(self, state: AgentState):
        idx = state['current_section_idx']
        outline = state.get('outline', [])
        if not outline or idx >= len(outline): return {}

        current_section = outline[idx]
        feedback = state.get('current_feedback', "")
        print(f"✍️ [Writer] Writing: {current_section.title}")

        req_docs = self.retriever.search(current_section.search_query, "current_requirements", top_k=3)
        context_str = "\n".join([d['content'] for d in req_docs]) if req_docs else ""
        
        sys_msg = SystemMessage(content=f"Bạn là Kỹ sư xây dựng. Viết mục: '{current_section.title}'.")
        text_content = f"DỰ ÁN: {state['project_details']}\nCTX: {context_str}\n"
        if feedback: text_content += f"SỬA THEO FEEDBACK: {feedback}"

        user_content: List[Any] = [{"type": "text", "text": text_content}]
        try:
            visual_docs = self.visual_retriever.search_visuals(current_section.search_query, top_k=1)
            for doc in visual_docs:
                user_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{doc['base64']}"}})
        except: pass

        msg = self.llm.invoke([sys_msg, HumanMessage(content=user_content)])
        
        current_section.content = self._get_text_content(msg.content) # Dùng helper an toàn
        new_outline = list(outline)
        new_outline[idx] = current_section
        
        return {"outline": new_outline}

    def reviewer_node(self, state: AgentState):
        idx = state['current_section_idx']
        outline = state.get('outline', [])
        if not outline or idx >= len(outline): return {}
        
        current_section = outline[idx]
        print(f"🧐 [Reviewer] Checking: {current_section.title}")
        
        prompt = f"Review bài viết:\n{current_section.content}\n{self.reviewer_parser.get_format_instructions()}"
        res = self.llm.invoke(prompt)
        feedback = self._safe_parse(res.content, self.reviewer_parser)
        
        if not feedback: 
            feedback = ReviewFeedback(is_approved=True, score=10, critique="", suggestions="") # Auto pass if parse fail

        rev_count = state.get('revision_count') or 0
        if not feedback.is_approved and rev_count >= 2:
            feedback.is_approved = True # Max retries

        if feedback.is_approved:
            doc_chunk = f"\n\n## {current_section.title}\n\n{current_section.content}"
            return {"current_section_idx": idx + 1, "revision_count": 0, "current_feedback": "", "final_document": state.get('final_document', "") + doc_chunk}
        else:
            return {"revision_count": rev_count + 1, "current_feedback": f"{feedback.critique}"}

    # ==========================================
    # 6. RUN (FIXED RESPONSE LOGIC)
    # ==========================================

    def route_requirements(self, state: AgentState):
        return "proceed" if state.get("requirements_gathered") else "ask_user"

    def route_review(self, state: AgentState):
        if state.get("current_feedback"): return "revise"
        idx = state.get('current_section_idx', 0)
        outline = state.get('outline', [])
        return "completed" if idx >= len(outline) else "next"

    def run(self, user_input: str, thread_id: str):
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}
        current_state = self.app.get_state(config)
        
        if not current_state.values:
            print(f"🚀 [New Session] {thread_id}")
            initial_state: AgentState = {
                "messages": [HumanMessage(content=user_input)],
                "requirements_gathered": False,
                "project_name": "", "project_details": "",
                "outline": [], "current_section_idx": 0,
                "final_document": "", "revision_count": 0, "current_feedback": "", "reference_doc_name": None
            }
            final_state = self.app.invoke(initial_state, config=config)
        else:
            vals = current_state.values
            is_done = vals.get("final_document") and vals.get("current_section_idx", 0) >= len(vals.get("outline", []))
            
            if is_done:
                print("🔄 [Feedback Loop]")
                self.app.update_state(config, {"messages": [HumanMessage(content=user_input)], "current_feedback": f"USER: {user_input}", "current_section_idx": 0, "final_document": ""})
                final_state = self.app.invoke(None, config=config) # type: ignore
            else:
                print("▶️ [Continuing]")
                self.app.update_state(config, {"messages": [HumanMessage(content=user_input)]})
                final_state = self.app.invoke(None, config=config) # type: ignore

        # --- RESPONSE HANDLING ---
        if not final_state.get("requirements_gathered"):
            msgs = final_state.get("messages", [])
            # Lấy tin nhắn AI cuối cùng, bỏ qua User Message
            last_ai_msg = "..."
            for m in reversed(msgs):
                if isinstance(m, AIMessage):
                    last_ai_msg = self._get_text_content(m.content)
                    break
            return {"status": "interaction_needed", "message": last_ai_msg, "data": None}
            
        elif final_state.get("final_document") and not final_state.get("current_feedback"):
            return {"status": "completed", "message": "Hoàn thành.", "data": final_state["final_document"]}
        else:
            return {"status": "processing", "message": "Đang xử lý...", "data": None}