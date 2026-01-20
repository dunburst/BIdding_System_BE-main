from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from typing import Dict, Optional
from fastapi.responses import FileResponse
from docx.document import Document# <--- Import thư viện Word
from docx import Document as DocxDocument
from docx.shared import Pt  # Để chỉnh cỡ chữ nếu cần
import os
import datetime

# Import class PlanningAgent từ file của bạn
# Giả sử file chứa class PlanningAgent tên là planning_agent.py và nằm cùng cấp hoặc trong services
from services.planning_agent import PlanningAgent 

router = APIRouter(prefix="/agent", tags=["Planning Agent"])

# --- 1. MEMORY STORE (QUẢN LÝ PHIÊN) ---
# Lưu trữ các instance của Agent theo session_id
# Cấu trúc: { "session_123": PlanningAgent_Instance, "user_abc": PlanningAgent_Instance }
agent_sessions: Dict[str, PlanningAgent] = {}

def get_agent_by_session(session_id: str) -> PlanningAgent:
    """
    Hàm helper để lấy hoặc tạo mới Agent cho một session cụ thể.
    """
    if session_id not in agent_sessions:
        print(f"✨ Khởi tạo Agent mới cho session: {session_id}")
        agent_sessions[session_id] = PlanningAgent()
    return agent_sessions[session_id]

# --- 2. DATA MODELS (Pydantic) ---
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default" # Mặc định nếu không gửi session_id

class ChatResponse(BaseModel):
    response: str
    session_id: str

# --- 3. API ENDPOINTS ---

@router.post("/chat", response_model=ChatResponse)
async def chat_with_agent(request: ChatRequest):
    """
    Gửi tin nhắn tới Agent và nhận phản hồi lập kế hoạch.
    """
    try:
        # Lấy agent tương ứng với phiên làm việc
        agent = get_agent_by_session(request.session_id)
        
        # Gọi hàm chat (Lưu ý: PlanningAgent đang chạy Sync, FastAPI sẽ xử lý trong threadpool)
        reply = agent.chat(request.message)
        
        return ChatResponse(
            response=reply,
            session_id=request.session_id
        )
    except Exception as e:
        print(f"❌ Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reset")
async def reset_memory(session_id: str = Body(..., embed=True)):
    """
    Xóa bộ nhớ hội thoại của một session cụ thể.
    Body gửi lên: { "session_id": "..." }
    """
    if session_id in agent_sessions:
        agent = agent_sessions[session_id]
        agent.reset_memory()
        return {"status": "success", "message": f"Memory for session '{session_id}' cleared."}
    else:
        return {"status": "warning", "message": "Session not found, nothing to clear."}

@router.delete("/clear-session")
async def clear_session(session_id: str):
    """
    Xóa hoàn toàn Agent instance để giải phóng RAM (Hard Reset)
    """
    if session_id in agent_sessions:
        del agent_sessions[session_id]
        return {"status": "success", "message": f"Session '{session_id}' destroyed."}
    return {"status": "error", "message": "Session not found."}

# --- PHẦN THÊM MỚI: XUẤT FILE ---
def convert_markdown_to_docx_content(doc: Document, text: str):
    """
    Hàm hỗ trợ chuyển đổi Markdown đơn giản sang cấu trúc Word
    """
    for line in text.split('\n'):
        line = line.strip()
        
        if not line:
            continue # Bỏ qua dòng trống
            
        # Xử lý Tiêu đề (Headers)
        if line.startswith('# '):
            doc.add_heading(line[2:], level=1)
        elif line.startswith('## '):
            doc.add_heading(line[3:], level=2)
        elif line.startswith('### '):
            doc.add_heading(line[4:], level=3)
        
        # Xử lý Danh sách (List items)
        elif line.startswith('- ') or line.startswith('* '):
            doc.add_paragraph(line[2:], style='List Bullet')
        elif line[0].isdigit() and line[1:3] == '. ': # Ví dụ: "1. "
            doc.add_paragraph(line[3:], style='List Number')
            
        # Đoạn văn bản thường
        else:
            # Xử lý in đậm cơ bản (**text**) - optional
            # Để đơn giản ở đây ta add paragraph thường, 
            # nếu muốn xịn hơn cần dùng regex tách chuỗi.
            p = doc.add_paragraph(line)
@router.get("/download-docx/{session_id}")
async def download_plan_word(session_id: str):
    """
    Tải bản kế hoạch dưới dạng file Word (.docx)
    """
    # 1. Kiểm tra session
    if session_id not in agent_sessions:
        raise HTTPException(status_code=404, detail="Session not found. Chat first!")
    
    agent = agent_sessions[session_id]
    
    if not agent.history:
        raise HTTPException(status_code=400, detail="History is empty.")

    # 2. Lấy nội dung bản kế hoạch cuối cùng
    last_plan = ""
    for msg in reversed(agent.history):
        if msg["role"] == "assistant":
            # Kiểm tra xem content có phải chuỗi không (đôi khi là None)
            content = msg.get("content")
            if content and isinstance(content, str):
                last_plan = content
                break
    
    if not last_plan:
        raise HTTPException(status_code=400, detail="No plan found.")

    # 3. Khởi tạo file Word
    doc = DocxDocument()
    
    # Thêm Tiêu đề chính cho tài liệu
    doc.add_heading('KẾ HOẠCH DỰ ÁN', 0)
    
    # Thêm thông tin meta
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    doc.add_paragraph(f"Mã phiên: {session_id}")
    doc.add_paragraph(f"Ngày tạo: {timestamp}")
    doc.add_paragraph("-" * 30) # Đường kẻ phân cách

    # 4. Chuyển đổi nội dung Chat sang Word
    convert_markdown_to_docx_content(doc, last_plan)

    # 5. Lưu file
    export_dir = "exports"
    os.makedirs(export_dir, exist_ok=True)
    
    # Đặt tên file .docx
    filename = f"Plan_{session_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
    file_path = os.path.join(export_dir, filename)
    
    doc.save(file_path)

    # 6. Trả về file
    return FileResponse(
        path=file_path, 
        filename=filename, 
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )