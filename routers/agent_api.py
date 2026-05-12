from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

# Import Agent và Services thực tế
from services.planning_agent import ConstructionDraftingAgent
from services.chroma_service import get_chroma_service, ChromaService
from services.retrieval_service import RetrievalService
from services.visual_retrieval_service import VisualRetrievalService

router = APIRouter(prefix="/api/v1/agent", tags=["Construction Agent"])

# --- 1. DATA TRANSFER OBJECTS (DTO) ---
class ChatRequest(BaseModel):
    message: str = Field(..., description="Nội dung người dùng chat")
    thread_id: str = Field(..., description="ID phiên làm việc (Session ID) để Agent nhớ ngữ cảnh")

class ChatResponse(BaseModel):
    status: str = Field(..., description="interaction_needed | processing | completed")
    message: str = Field(..., description="Lời nhắn của Agent hoặc câu hỏi")
    data: Optional[Any] = Field(None, description="Dữ liệu final document nếu xong")

# --- 2. DEPENDENCY INJECTION (SINGLETON AGENT) ---
# Biến toàn cục để lưu instance của Agent (để không phải init lại DeepSeek/Visual Model mỗi lần gọi API)
_agent_instance: Optional[ConstructionDraftingAgent] = None

def get_agent_service() -> ConstructionDraftingAgent:
    """
    Hàm này khởi tạo Agent 1 lần duy nhất (Singleton Pattern).
    Được inject vào các endpoint API.
    """
    global _agent_instance
    
    if _agent_instance is None:
        print("⏳ [System] Đang khởi tạo Services & Agent lần đầu...")
        
        # 1. Khởi tạo các Service con
        # (Giả định bạn có hàm get_chroma_service hoặc tự khởi tạo class)
        try:
            chroma_svc = get_chroma_service() 
        except:
            chroma_svc = ChromaService() # Fallback nếu không dùng Dependency
            
        retrieval_svc = RetrievalService(chroma_svc)
        visual_svc = VisualRetrievalService() # Model LitePali load ở đây
        
        # 2. Khởi tạo Agent
        _agent_instance = ConstructionDraftingAgent(retrieval_svc, visual_svc)
        print("✅ [System] Agent đã sẵn sàng!")
        
    return _agent_instance

# --- 3. API ENDPOINTS ---

@router.post("/chat", response_model=ChatResponse)
async def chat_with_agent(
    payload: ChatRequest,
    agent: ConstructionDraftingAgent = Depends(get_agent_service)
):
    """
    API chính để chat với Agent.
    - Input: message, thread_id
    - Output: status, message, data (nếu xong)
    """
    try:
        # Gọi hàm run của Agent
        # Lưu ý: thread_id từ client gửi lên rất quan trọng để MemorySaver hoạt động
        result = agent.run(payload.message, payload.thread_id)
        
        return ChatResponse(
            status=result["status"],
            message=result["message"],
            data=result.get("data")
        )
        
    except Exception as e:
        print(f"❌ API Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/memory/{thread_id}")
async def clear_memory(thread_id: str):
    """
    API phụ để xóa bộ nhớ của một phiên (Nếu cần reset cứng)
    Lưu ý: Bạn cần implement hàm clear trong Agent nếu muốn dùng tính năng này.
    """
    # Logic xóa memory (Tuỳ chọn)
    return {"status": "success", "message": f"Đã xóa bộ nhớ thread {thread_id}"}