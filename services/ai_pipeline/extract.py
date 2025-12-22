import os
from typing import List, Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()

# ==========================================
# 1. ĐỊNH NGHĨA DATA MODELS (SCHEMA)
# ==========================================

class GeneralInfo(BaseModel):
    package_name: Optional[str] = Field(None, description="Tên chính xác của gói thầu")
    e_tbmt_number: Optional[str] = Field(None, description="Số E-TBMT (VD: IB24000...)")
    investor: Optional[str] = Field(None, description="Tên chủ đầu tư / Bên mời thầu")
    funding_source: Optional[str] = Field(None, description="Nguồn vốn")

class AdminRequirements(BaseModel):
    bid_security_value: Optional[str] = Field(None, description="Giá trị bảo đảm dự thầu (VD: 94.000.000 VND)")
    bid_validity_days: Optional[int] = Field(None, description="Số ngày hiệu lực của HSDT")
    contract_duration: Optional[str] = Field(None, description="Thời gian thực hiện hợp đồng")
    submission_fee: Optional[float] = Field(None, description="Chi phí nộp hồ sơ (nếu có)")

class FinancialRequirements(BaseModel):
    avg_revenue: Optional[float] = Field(None, description="Doanh thu bình quân hằng năm yêu cầu (Chuyển về số VNĐ)")
    min_contract_value: Optional[float] = Field(None, description="Giá trị hợp đồng tương tự tối thiểu (Chuyển về số VNĐ)")
    similar_contract_desc: Optional[str] = Field(None, description="Mô tả tính chất tương tự của hợp đồng đã làm")
    working_capital: Optional[float] = Field(None, description="Yêu cầu nguồn lực tài chính / vốn lưu động (VNĐ)")

class PersonnelReq(BaseModel):
    position: str = Field(..., description="Vị trí công việc (VD: Chỉ huy trưởng, Cán bộ kỹ thuật)")
    quantity: int = Field(1, description="Số lượng nhân sự yêu cầu")
    qualification: Optional[str] = Field(None, description="Yêu cầu bằng cấp, chứng chỉ chuyên môn")
    experience_years: Optional[int] = Field(None, description="Số năm kinh nghiệm tối thiểu yêu cầu")

class EquipmentReq(BaseModel):
    name: str = Field(..., description="Tên máy móc thiết bị")
    quantity: int = Field(1, description="Số lượng yêu cầu")
    specs: Optional[str] = Field(None, description="Thông số kỹ thuật / Công suất yêu cầu")

# Model tổng hợp (Root)
class BiddingData(BaseModel):
    section_1_general: GeneralInfo
    section_2_admin: AdminRequirements
    section_3_financial: FinancialRequirements
    section_4_personnel: List[PersonnelReq] = []
    section_5_equipment: List[EquipmentReq] = []

# ==========================================
# 2. HÀM XỬ LÝ CHÍNH
# ==========================================

def prepare_context(chunks: list) -> str:
    """Gom các chunk văn bản thành 1 chuỗi context duy nhất để gửi cho AI"""
    full_text = ""
    for chunk in chunks:
        full_text += f"\n--- PHẦN: {chunk['chapter_title']} (Loại: {chunk['category']}) ---\n{chunk['full_content']}\n"
    return full_text

def extract_bid_info(full_context_text: str) -> BiddingData:
    """
    Gọi Gemini API để trích xuất thông tin JSON từ văn bản context
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("❌ Thiếu GOOGLE_API_KEY trong file .env")

    # Cấu hình Model
    # Dùng gemini-1.5-pro hoặc gemini-2.5-pro (nếu bạn có quyền truy cập)
    llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-pro", 
        temperature=0, # Temperature = 0 để đảm bảo tính nhất quán, không sáng tạo
        google_api_key=api_key,
        convert_system_message_to_human=True
    )

    # Ép kiểu đầu ra theo Pydantic Schema (Structured Output)
    structured_llm = llm.with_structured_output(BiddingData)

    prompt = ChatPromptTemplate.from_messages([
        ("system", """
         Bạn là một chuyên gia phân tích hồ sơ mời thầu (Bid Manager AI). 
         Nhiệm vụ của bạn là đọc nội dung hồ sơ mời thầu và trích xuất các thông tin quan trọng vào định dạng JSON.
         
         LƯU Ý QUAN TRỌNG:
         1. **Số tiền**: Hãy cố gắng chuyển đổi các con số (VD: "10 tỷ", "10.000.000.000") thành số nguyên (Float/Int). Nếu không rõ đơn vị, hãy để nguyên hoặc null.
         2. **Nhân sự & Thiết bị**: Trích xuất đầy đủ danh sách dưới dạng mảng (Array).
         3. **Trung thực**: Chỉ trích xuất thông tin có trong văn bản. Nếu không tìm thấy, hãy để field đó là null.
         """),
        ("human", "Dưới đây là nội dung chi tiết của hồ sơ mời thầu:\n\n{context}")
    ])

    chain = prompt | structured_llm
    
    print("🤖 [Extract] Đang gửi dữ liệu tới Gemini để phân tích...")
    try:
        result = chain.invoke({"context": full_context_text})
        print("✅ [Extract] Trích xuất dữ liệu thành công!")
        return result
    except Exception as e:
        print(f"❌ [Extract] Lỗi khi gọi Gemini API: {e}")
        raise e