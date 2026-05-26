import operator
import os
import re
from typing import Annotated, List, TypedDict, Optional, Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver 
# --- THAY ĐỔI: Import Google ---
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field, SecretStr
from langchain_core.runnables import RunnableConfig
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

# Import các service
from app.integrations.ai.data_processing.retrieval_service import RetrievalService
from app.integrations.ai.data_processing.chroma_service import ChromaService
from app.integrations.ai.data_processing.visual_retrieval_service import VisualRetrievalService

# --- CẤU HÌNH API KEY ---
google_key = os.getenv("GEMINI_API_KEY")
if not google_key:
    raise ValueError("❌ Google API Key not found! Vui lòng set biến môi trường GEMINI_API_KEY.")

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
        
        # --- THAY ĐỔI: Cấu hình Gemini ---
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0,
            google_api_key=google_key,
            max_retries=2,
            # Tắt bộ lọc an toàn để tránh block nội dung xây dựng
            safety_settings={
                "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
                "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
                "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
            }
        )
        
        # Sử dụng Parser để xử lý JSON output (Ổn định hơn native tool calling)
        self.outline_parser = JsonOutputParser(pydantic_object=ProposalOutline)
        self.review_parser = JsonOutputParser(pydantic_object=ReviewFeedback)

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
        """Bước 1: Lập dàn ý dựa trên thứ tự thực tế của tài liệu và Regex chuẩn"""
        print(f"🏗️ [Planner] Đang lập dàn ý: {state['project_name']}...")
        
        detected_headers = []
        full_context_str = ""

        if state.get('reference_doc_name'):
            print(f"   --> Quét cấu trúc từ: {state['reference_doc_name']}")
            try:
                # 1. Tăng top_k để lấy nhiều mảnh ghép hơn
                sample_filter = {"source": state['reference_doc_name']}
                sample_docs = self.retriever.search(
                    query="Chương mục quy định biện pháp thi công", 
                    collection_name="bidding_docs", 
                    top_k=600,  # Lấy rộng để bao phủ đủ các chương
                    filters=sample_filter
                )
                
                # --- LOGIC MỚI: SẮP XẾP THEO CHUNK ID ---
                # Chunk ID của Docling/Langchain thường có dạng "filename_0", "filename_1"
                # Sắp xếp theo cái đuôi số này sẽ ra đúng thứ tự Mục lục gốc của sách/file
                def get_chunk_index(doc):
                    try:
                        # Giả sử ID là "fc6f9..._0". Lấy số cuối cùng.
                        # Nếu ID object không có thuộc tính id, thử lấy từ metadata
                        doc_id = getattr(doc, 'id', "") or doc.get('metadata', {}).get('id', "") or ""
                        if "_" in str(doc_id):
                            return int(str(doc_id).split("_")[-1])
                    except:
                        pass
                    return 0
                
                # Sắp xếp docs theo thứ tự trang/chunk
                sorted_docs = sorted(sample_docs, key=get_chunk_index)

                seen_headers = set()
                
                # Regex bắt buộc: Phải bắt đầu bằng (Chương/Phần) hoặc (Số La Mã + chấm) hoặc (Số thường + chấm)
                # Ví dụ hợp lệ: "Chương 1", "I. Giới thiệu", "1.1. Tổng quan", "4. An toàn"
                valid_pattern = re.compile(r'^(?:chương|phần|mục|[ivx]+\.|\d+(?:\.\d+)*[\.\s])', re.IGNORECASE)

                for doc in sorted_docs:
                    metadata = doc.get('metadata', {})
                    # Ưu tiên lấy Header từ metadata
                    header_val = metadata.get('Header 2') or metadata.get('header_2') or metadata.get('Header 1')
                    
                    if header_val and isinstance(header_val, str):
                        clean = header_val.strip()
                        # Chỉ lấy nếu khớp Regex và chưa trùng
                        if valid_pattern.match(clean) and clean not in seen_headers:
                            seen_headers.add(clean)
                            detected_headers.append(clean) # Append theo thứ tự sorted_docs
                
                if detected_headers:
                    print(f"   --> Đã tìm thấy {len(detected_headers)} header theo đúng thứ tự tài liệu.")
                    
            except Exception as e:
                print(f"⚠️ Lỗi trích xuất Header: {e}")

        # 2. Tạo Prompt ép buộc phân cấp
        if detected_headers:
            structure_input = "DANH SÁCH MỤC LỤC TÌM THẤY (Đã sắp xếp theo thứ tự trang):\n" + "\n".join([f"- {h}" for h in detected_headers])
        else:
            structure_input = f"NỘI DUNG THAM KHẢO:\n{full_context_str}"

        # Prompt được tinh chỉnh để hiểu luật "Mẹ bồng Con"
        prompt = ChatPromptTemplate.from_messages([
            ("system", """Bạn là Kỹ sư trưởng lập kế hoạch hồ sơ thầu.
            Nhiệm vụ: Sắp xếp lại danh sách các đầu mục thành một Dàn ý phân cấp logic.
            
            QUY TẮC PHÂN CẤP QUAN TRỌNG:
            1. Cấp to nhất: "CHƯƠNG" hoặc "PHẦN".
            2. Cấp 2: Số La Mã (I., II., III....). -> Nằm trong Chương.
            3. Cấp 3: Số tự nhiên (1., 2., 3....). -> Nằm trong La Mã.
            4. Cấp 4: Số thập phân (1.1, 1.2...). -> Nằm trong Số tự nhiên.
            
            Ví dụ đúng:
            - CHƯƠNG I: TỔNG QUAN
              - I. CĂN CỨ PHÁP LÝ
                 - 1. Tiêu chuẩn áp dụng
                 - 2. Quy chuẩn
              - II. GIỚI THIỆU DỰ ÁN
                 - 1. Vị trí
                    - 1.1. Địa hình
            
            HÃY TRẢ VỀ JSON:
            {format_instructions}
            """),
            ("human", """Dự án: "{project_name}"
            
            {structure_input}
            
            YÊU CẦU:
            1. Giữ nguyên nội dung text của header tìm thấy, chỉ sắp xếp lại vị trí cho đúng luồng thi công.
            2. Loại bỏ các mục không liên quan (như Lời cảm ơn, Mục lục...).
            3. Tạo 'search_query' thông minh cho từng mục.
            """)
        ]).partial(format_instructions=self.outline_parser.get_format_instructions())

        # 3. Gọi LLM
        try:
            chain = prompt | self.llm | self.outline_parser
            res = chain.invoke({
                "project_name": state['project_name'],
                "structure_input": structure_input
            })
            
            raw_sections = res.get('sections', [])
            sections = [Section(**s) for s in raw_sections]
            
        except Exception as e:
            print(f"⚠️ Lỗi Planner LLM: {e}")
            sections = [] # Handle fallback here if needed

        print(f"✅ Đã lập {len(sections)} mục.")
        return {
            "outline": sections,
            "current_section_idx": 0,
            "final_document": "",
            "revision_count": 0,
            "current_feedback": ""
        }

    def writer_node(self, state: AgentState):
        """Bước 2: Viết nội dung (Gemini Multimodal)"""
        idx = state['current_section_idx']
        if idx >= len(state['outline']): return {"current_section_idx": idx}

        current_section = state['outline'][idx]
        feedback = state.get('current_feedback', "")
        
        if feedback:
            print(f"✍️ [Writer] SỬA LẠI: {current_section.title} (Lần {state['revision_count']})")
        else:
            print(f"✍️ [Writer] Viết mới: {current_section.title}")

        # --- LOGIC TÌM KIẾM ---
        project_filter = {"project_name": state['project_name']}
        req_docs = self.retriever.search(current_section.search_query, "current_requirements", top_k=4, filters=project_filter)
        template_docs = self.retriever.search(current_section.search_query, "bidding_docs", top_k=2)
        
        context_parts = []
        if req_docs:
            context_parts.append("=== YÊU CẦU CỤ THỂ ===")
            context_parts.extend([f"- {r['content']}" for r in req_docs])
        if template_docs:
            context_parts.append("=== BIỆN PHÁP MẪU ===")
            context_parts.extend([f"- {r['content']}" for r in template_docs])
            
        text_context = "\n\n".join(context_parts)

        # 3. Tìm Ảnh (Gemini xem được ảnh!)
        visual_docs = self.visual_retriever.search_visuals(current_section.search_query, top_k=2)

        # Cấu trúc Message cho Gemini
        messages = []
        messages.append(SystemMessage(content=f"""
        Bạn là Kỹ sư Biện pháp thi công chuyên nghiệp.
        Dự án: "{state['project_name']}". Mục: "{current_section.title}".
        
        DỮ LIỆU THAM KHẢO (TEXT):
        {text_context}
        """))

        user_content_blocks: List[Any] = [
            {"type": "text", "text": f"""
            Hãy viết nội dung chi tiết cho mục này.
            
            YÊU CẦU:
            1. Ưu tiên tuân thủ các yêu cầu trong HSMT.
            2. Sử dụng văn phong chuyên nghiệp.
            3. Nếu có hình ảnh được cung cấp, hãy PHÂN TÍCH HÌNH ẢNH để mô tả biện pháp thi công sát thực tế.
            4. Trình bày Markdown đẹp.
            """}
        ]
        
        if feedback:
            user_content_blocks[0]["text"] += f"\n\n!!! REVIEWER YÊU CẦU SỬA: '{feedback}'."

        if visual_docs:
            print(f"   📷 Gửi {len(visual_docs)} ảnh cho Gemini phân tích.")
            for doc in visual_docs:
                # LangChain Google Adapter tự động xử lý format này
                user_content_blocks.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{doc['base64']}"}
                })

        messages.append(HumanMessage(content=user_content_blocks))

        # Invoke Gemini
        msg = self.llm.invoke(messages)
        current_section.content = str(msg.content)
        
        # Update list
        new_outline = list(state['outline'])
        new_outline[idx] = current_section
        
        return {"outline": new_outline}

    def reviewer_node(self, state: AgentState):
        """Bước 3: QA/QC Review"""
        idx = state['current_section_idx']
        if idx >= len(state['outline']): return {}

        current_section = state['outline'][idx]
        print(f"🧐 [Reviewer] Đang chấm: {current_section.title}...")

        prompt = ChatPromptTemplate.from_messages([
            ("system", """Bạn là Chuyên gia thẩm định hồ sơ thầu (QA/QC).
            Tiêu chí chấm:
            1. Tuân thủ yêu cầu kỹ thuật.
            2. Văn phong chuyên nghiệp, không văn nói.
            3. Chi tiết, có số liệu/quy trình cụ thể.

            HÃY TRẢ VỀ JSON:
            {format_instructions}
            """),
            ("human", """BÀI VIẾT CẦN THẨM ĐỊNH:
            ---
            {content}
            ---
            """)
        ]).partial(format_instructions=self.review_parser.get_format_instructions())

        chain = prompt | self.llm | self.review_parser
        feedback_data = chain.invoke({"content": current_section.content})

        # Convert Dict -> Pydantic
        feedback = ReviewFeedback(**feedback_data)

        # Logic chống lặp
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

    # --- 4. HÀM RUN ---
    def run(self, thread_id: str, project_name: str = "", reference_doc: Optional[str] = None, user_feedback_outline: Optional[List[Dict]] = None):
        config: RunnableConfig = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 150
        }
        
        if user_feedback_outline:
            print(f"▶️ [Resume] Thread: {thread_id}...")
            # Cập nhật state khi resume
            updated_sections = [Section(**s) for s in user_feedback_outline]
            self.app.update_state(config, {
                "outline": updated_sections,
                "revision_count": 0,
                "current_feedback": ""
            })
            
            result = self.app.invoke(None, config=config)
            return {"status": "completed", "type": "full_document", "content": result['final_document']}
            
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
            
            # Serialize outline để trả về cho FE
            outline_data = [s.dict() for s in snapshot.values.get("outline", [])]
            return {"status": "paused", "type": "outline_review", "content": outline_data}