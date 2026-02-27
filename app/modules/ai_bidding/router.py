import logging
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends, Query
from fastapi.responses import StreamingResponse, HTMLResponse
from sqlalchemy.orm import Session

# --- DEPENDENCIES ---
from app.infrastructure.database.database import get_db
from app.integrations.ai.data_processing.chroma_service import ChromaService, get_chroma_service
from app.integrations.ai.data_processing.retrieval_service import RetrievalService, get_retrieval_service
from app.integrations.ai.data_processing.visual_retrieval_service import VisualRetrievalService, get_visual_service
from app.integrations.ai.data_processing.requirement_service import RequirementService, get_req_service
from app.integrations.ai.agent.bid_preparation import DraftingBot, get_drafting_bot
from app.modules.drafting.model import DocumentRegistry

# --- MODULE IMPORTS ---
from app.modules.ai_bidding.schema import DraftingRequest
from app.modules.ai_bidding import crud # <--- Gọi file CRUD ở trên

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/ai-bidding",
    tags=["AI Bidding (RAG)"],
    responses={404: {"description": "Not found"}},
)

# ==============================================================================
# 1. API CŨ ĐƯỢC KHÔI PHỤC (RESTORED)
# ==============================================================================

# [RESTORED] API: Dạy bot (Tương đương ingest-async nhưng giữ tên cũ cho bạn)
@router.post("/learn-sample-document", summary="Dạy Bot (Legacy)")
async def learn_document_async(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    # Mapping sang logic chuẩn của MinIO ingest trong CRUD
    metadata = {"collection_name": "legal_docs", "source": "learn_api"}
    return await crud.ingest_file_logic(
        file=file, 
        background_tasks=background_tasks, 
        minio_folder="raw_inputs", 
        metadata=metadata
    )

# [RESTORED] API: Upload Requirement (Xử lý ngay lập tức)
@router.post("/upload-requirement", summary="Upload HSMT (Sync)")
async def upload_requirement(
    file: UploadFile = File(...), 
    project_name: str = Form(..., description="Tên dự án"),
    service: RequirementService = Depends(get_req_service)
):
    return crud.process_requirement_sync_logic(file, project_name, service)

# [RESTORED] API: Viết bài HTML đơn giản
@router.post("/generate-section", summary="Viết bài & Xem HTML")
async def generate_section_view(
    topic: str = Form(...),
    drafting_bot: DraftingBot = Depends(get_drafting_bot)
):
    try:
        html_content = crud.generate_simple_html_logic(topic, drafting_bot)
        return HTMLResponse(content=html_content, status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# [RESTORED] API: Status & Reset
@router.get("/status", summary="Check Session Status")
async def get_status():
    return crud.get_session_status_logic()

@router.post("/reset-session", summary="Clear Session")
async def reset_session(chroma_service: ChromaService = Depends(get_chroma_service)):
    return crud.reset_session_logic(chroma_service)

# [RESTORED] API: Task Status
@router.get("/tasks/{task_id}", summary="Check Background Task")
async def get_task_status(task_id: str):
    return crud.get_task_status_logic(task_id)


# ==============================================================================
# 2. CÁC API MỚI (MODULAR & AGENT)
# ==============================================================================

@router.post("/ingest-async", summary="Upload RAG (Standard)")
async def ingest_document_async(
    background_tasks: BackgroundTasks, 
    file: UploadFile = File(...),
    legal_level: Optional[str] = Form(None),
    promulgation_year: Optional[int] = Form(None),
    collection_name: str = Form("legal_docs")
):
    metadata = {
        "legal_level": legal_level,
        "promulgation_year": promulgation_year,
        "collection_name": collection_name
    }
    return await crud.ingest_file_logic(file, background_tasks, "raw_inputs", metadata)

@router.post("/ingest/template", summary="Upload Template")
async def ingest_template(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    metadata = {"collection_name": "bidding_docs", "is_template": True}
    return await crud.ingest_file_logic(file, background_tasks, "templates", metadata)

@router.post("/ingest/requirement", summary="Upload Requirement (Async)")
async def ingest_req_async(
    background_tasks: BackgroundTasks, 
    file: UploadFile = File(...), 
    project_name: str = Form(...)
):
    metadata = {"collection_name": "current_requirements", "project_name": project_name}
    return await crud.ingest_file_logic(file, background_tasks, f"projects/{project_name}", metadata)

@router.post("/search", summary="Search Streaming")
async def search_knowledge(
    query: str, 
    retrieval_service: RetrievalService = Depends(get_retrieval_service)
):
    return StreamingResponse(
        crud.generate_search_stream(query, retrieval_service), 
        media_type="text/event-stream"
    )

@router.post("/agent/draft-full-proposal", summary="Agent HITL Generation")
async def draft_full_proposal(
    req: DraftingRequest,
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    visual_service: VisualRetrievalService = Depends(get_visual_service)
):
    try:
        return crud.run_drafting_agent_logic(req, retrieval_service, visual_service)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/documents", summary="List Documents")
async def get_documents_from_sql(db: Session = Depends(get_db)):
    docs = db.query(DocumentRegistry).order_by(DocumentRegistry.created_at.desc()).all()
    return {"count": len(docs), "data": docs}

@router.delete("/documents/{filename}", summary="Delete Document")
async def delete_document(
    filename: str,
    collection_name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    chroma_service: ChromaService = Depends(get_chroma_service)
):
    return crud.delete_document_logic(filename, collection_name, db, chroma_service)

@router.get("/collections", summary="List Collections")
async def get_collections(chroma_service: ChromaService = Depends(get_chroma_service), db: Session = Depends(get_db)):
    # Logic ngắn để trực tiếp trong router cũng được
    chroma_cols = chroma_service.list_all_collections()
    sql_cols = [row[0] for row in db.query(DocumentRegistry.collection_name).distinct().all() if row[0]]
    return {"active_in_chroma": chroma_cols, "used_in_sql": sql_cols}

@router.get("/collection/{collection_name}/files", summary="List Files in Collection")
async def list_files(collection_name: str, chroma_service: ChromaService = Depends(get_chroma_service)):
    files = chroma_service.list_files_in_collection(collection_name)
    return {"collection": collection_name, "total_files": len(files), "files": files}