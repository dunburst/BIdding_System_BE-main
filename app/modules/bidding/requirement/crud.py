from sqlalchemy.orm import Session
from sqlalchemy import select
from app.modules.bidding.requirement.model import BiddingReqFinancialAdmin, BiddingReqPersonnel, BiddingReqEquipment
from app.modules.bidding.package.model import BiddingPackage
from typing import List, Optional
import app.modules.bidding.requirement.schema as schemas
from decimal import Decimal
from app.modules.bidding.requirement import crud
import os
import google.generativeai as genai
import json
from fastapi import HTTPException

# --- 1. FINANCIAL (1-1) ---
def get_financial_req_by_hsmt(db: Session, hsmt_id: int) -> Optional[BiddingReqFinancialAdmin]:
    """Lấy yêu cầu tài chính theo ID gói thầu (chỉ có 1 record)"""
    stmt = select(BiddingReqFinancialAdmin).where(BiddingReqFinancialAdmin.hsmt_id == hsmt_id)
    return db.scalar(stmt)

# --- 2. PERSONNEL (1-N) ---
def get_personnel_reqs_by_hsmt(db: Session, hsmt_id: int) -> List[BiddingReqPersonnel]:
    """Lấy danh sách toàn bộ nhân sự yêu cầu của 1 gói thầu"""
    stmt = select(BiddingReqPersonnel).where(BiddingReqPersonnel.hsmt_id == hsmt_id).order_by(BiddingReqPersonnel.stt)
    return list(db.scalars(stmt).all())

def get_personnel_req_detail(db: Session, req_id: int) -> Optional[BiddingReqPersonnel]:
    """Xem chi tiết 1 vị trí nhân sự cụ thể (theo ID dòng)"""
    stmt = select(BiddingReqPersonnel).where(BiddingReqPersonnel.id == req_id)
    return db.scalar(stmt)

# --- 3. EQUIPMENT (1-N) ---
def get_equipment_reqs_by_hsmt(db: Session, hsmt_id: int) -> List[BiddingReqEquipment]:
    """Lấy danh sách toàn bộ thiết bị yêu cầu của 1 gói thầu"""
    stmt = select(BiddingReqEquipment).where(BiddingReqEquipment.hsmt_id == hsmt_id).order_by(BiddingReqEquipment.stt)
    return list(db.scalars(stmt).all())

def get_equipment_req_detail(db: Session, req_id: int) -> Optional[BiddingReqEquipment]:
    """Xem chi tiết 1 thiết bị cụ thể"""
    stmt = select(BiddingReqEquipment).where(BiddingReqEquipment.id == req_id)
    return db.scalar(stmt)
def get_bidding_package_by_id(db: Session, hsmt_id: int) -> Optional[BiddingPackage]:
    """Lấy thông tin chung của gói thầu từ bảng BiddingPackage"""
    stmt = select(BiddingPackage).where(BiddingPackage.hsmt_id == hsmt_id)
    return db.scalar(stmt)


# Cấu hình API Key cho Gemini (Nên lấy từ file .env)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "ĐIỀN_API_KEY_CỦA_BẠN_VÀO_ĐÂY")
genai.configure(api_key=GEMINI_API_KEY)
# ==========================================================
# 1. DỮ LIỆU FIX CỨNG (MOCK DATA) NĂNG LỰC CỦA CÔNG TY
# Sau này sẽ thay thế bằng việc query từ bảng CompanyProfile
# ==========================================================
MOCK_COMPANY_PROFILE = {
    "financial": {
        "revenue_avg": Decimal('500000000000'),       # 500 Tỷ
        "working_capital": Decimal('150000000000'),   # 150 Tỷ
        "similar_contract_qty": 300,
        "similar_contract_value": Decimal('300000000000') # 300 Tỷ
    },
    "personnel": {
        # Key là keyword để match với tên vị trí, value là danh sách nhân sự đáp ứng
        "chỉ huy trưởng": {"quantity": 100, "exp_years": 10},
        "kỹ sư": {"quantity": 100, "exp_years": 5},
        "cán bộ": {"quantity": 20, "exp_years": 4},
        "nhân sự": {"quantity": 300, "exp_years":2}
    },
    "equipment": {
        "xe cẩu": {"quantity": 5},
        "xe tải": {"quantity":10},
        "thiêt bị nâng hạ": {"quantity": 6},
        "máy tời": {"quantity": 9},
        "máy hãm": {"quantity": 10},
        "thiết bị cắt ép thủy lực": {"quantity": 4},
        "máy xúc": {"quantity": 3},
        "máy ủi": {"quantity": 4},
        "máy đầm": {"quantity": 6},
        "máy phát điện": {"quantity": 4},
        "máy trộn bê tông": {"quantity": 3},
        "máy nén khí": {"quantity": 4},
        "máy hàn": {"quantity":3},
        "máy đo điện trở": {"quantity": 3},
        "thiết bị thí nghiệm điện": {"quantity":2},
        "máy trắc địa": {"quantity": 2},
        "thiết bị tiếp địa": {"quantity": 3}
    }
}

# --- THÊM ĐOẠN NÀY VÀO ĐẦU FILE ---
class DecimalEncoder(json.JSONEncoder):
    def default(self, o): # Đổi 'obj' thành 'o' để khớp hoàn toàn với class gốc
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)
# ==========================================================
# 2. LOGIC SO SÁNH
# ==========================================================
def perform_health_check(db: Session, hsmt_id: int) -> schemas.HealthCheckResponse:
    # 1. LẤY DỮ LIỆU TỪ DATABASE
    fin_req = crud.get_financial_req_by_hsmt(db, hsmt_id)
    per_reqs = crud.get_personnel_reqs_by_hsmt(db, hsmt_id)
    eq_reqs = crud.get_equipment_reqs_by_hsmt(db, hsmt_id)

    # 2. CHUẨN BỊ DỮ LIỆU YÊU CẦU CỦA HSMT THÀNH DICT (ĐỂ ĐƯA CHO AI)
    hsmt_requirements = {
        "financial": {
            "req_revenue_avg": float(fin_req.req_revenue_avg) if fin_req and fin_req.req_revenue_avg else None,
            "req_similar_contract_qty": fin_req.req_similar_contract_qty if fin_req else None,
        },
        "personnel": [
            {"position": p.position_name, "quantity": p.quantity, "min_exp_years": p.min_exp_years} 
            for p in per_reqs
        ],
        "equipment": [
            {"name": e.equipment_name, "quantity": e.quantity} 
            for e in eq_reqs
        ]
    }

    # 3. XÂY DỰNG PROMPT CHO GEMINI
    prompt = f"""
    Bạn là một chuyên gia đánh giá Hồ sơ mời thầu (HSMT). Nhiệm vụ của bạn là so sánh Năng lực thực tế của công ty với Yêu cầu của gói thầu và chấm điểm (thang điểm 10).
    Hãy linh hoạt trong việc hiểu ngữ nghĩa (ví dụ: 'xe cẩu tự hành' có thể đáp ứng 'ô tô tải gắn cẩu', 'kỹ sư xây dựng' có thể đáp ứng 'kỹ sư thi công').

    --- DỮ LIỆU ĐẦU VÀO ---
    Yêu cầu của HSMT: {json.dumps(hsmt_requirements, ensure_ascii=False, cls=DecimalEncoder)}
    Năng lực hiện tại của công ty: {json.dumps(MOCK_COMPANY_PROFILE, ensure_ascii=False, cls=DecimalEncoder)}
    
    --- QUY TẮC ĐÁNH GIÁ ---
    1. Trạng thái (status) chỉ được chọn 1 trong 3 giá trị: "PASS", "FAIL", "WARNING".
    2. Điểm số (score): Tính theo tỷ lệ % số tiêu chí đạt được quy ra thang 10.
    3. overall_status: PASS nếu score >= 8.0, ngược lại là FAIL.
    4. note: Giải thích ngắn gọn lý do tại sao FAIL/WARNING hoặc gợi ý cách khắc phục (đi thuê, liên danh).

    --- YÊU CẦU ĐẦU RA (ĐỊNH DẠNG JSON) ---
    Trả về ĐÚNG cấu trúc JSON sau, không kèm markdown code block (như ```json):
    {{
      "hsmt_id": {hsmt_id},
      "score": <float>,
      "overall_status": "<PASS | FAIL | WARNING>",
      "categories": [
        {{
          "category_name": "<Tên hạng mục: Tài chính & Kinh nghiệm / Nhân sự chủ chốt / Thiết bị thi công>",
          "status": "<PASS | FAIL | WARNING>",
          "details": [
            {{
              "criteria_name": "<Tên tiêu chí>",
              "required_value": "<Yêu cầu>",
              "actual_value": "<Thực tế công ty có>",
              "status": "<PASS | FAIL>",
              "note": "<Ghi chú của bạn>"
            }}
          ]
        }}
      ]
    }}
    """

    # 4. GỌI GEMINI API VỚI JSON MODE
    try:
        # Sử dụng model gemini-1.5-flash vì nó nhanh và hỗ trợ JSON mode rất tốt
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Ép AI trả về JSON chuẩn
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json"
            )
        )
        
        # 5. PARSE KẾT QUẢ VÀ TRẢ VỀ THEO SCHEMA
        result_json = json.loads(response.text)
        return schemas.HealthCheckResponse(**result_json)
        
    except Exception as e:
        print(f"Lỗi khi gọi Gemini AI: {e}")
        raise HTTPException(status_code=500, detail="Không thể thực hiện đánh giá năng lực qua AI lúc này.")