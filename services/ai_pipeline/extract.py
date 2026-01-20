import os
from typing import List, Optional, cast
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
import pathlib
from langchain_ollama import ChatOllama

# Load biến môi trường
# Thử load từ file .env ở thư mục gốc (nếu script chạy từ folder con)
env_path = pathlib.Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)
# Fallback: load mặc định
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
    bid_security_duration: Optional[int] = Field(None, description="Thời gian thực hiện bảo đảm dự thầu (ngày)")
    contract_duration: Optional[str] = Field(None, description="Thời gian thực hiện hợp đồng")
    submission_fee: Optional[float] = Field(None, description="Chi phí nộp hồ sơ (nếu có)")

class FinancialRequirements(BaseModel):
    avg_revenue: Optional[float] = Field(None, description="Doanh thu bình quân hằng năm yêu cầu (Chuyển về số VNĐ, bỏ chữ)")
    min_contract_value: Optional[float] = Field(None, description="Giá trị hợp đồng tương tự tối thiểu (Chuyển về số VNĐ)")
    similar_contract_qty: Optional[int] = Field(None, description="Số lượng hợp đồng tương tự yêu cầu")
    similar_contract_desc: Optional[str] = Field(None, description="Mô tả tính chất tương tự của hợp đồng đã làm")
    working_capital: Optional[float] = Field(None, description="Yêu cầu nguồn lực tài chính / vốn lưu động (VNĐ)")

class PersonnelReq(BaseModel):
    position: str = Field(..., description="Vị trí công việc (Trích nguyên văn tiếng Việt, VD: 'Chỉ huy trưởng', KHÔNG dịch sang tiếng Anh)")#(VD: Chỉ huy trưởng, Cán bộ kỹ thuật)")
    quantity: int = Field(1, description="Số lượng nhân sự yêu cầu")
    qualification: Optional[str] = Field(None, description="Yêu cầu bằng cấp, chứng chỉ chuyên môn(Đại học, Cao đẳng...)")
    experience_years: Optional[int] = Field(None, description="Số năm kinh nghiệm tối thiểu yêu cầu(Chỉ lấy số)")
    similar_project_exp: Optional[int] = Field(None, description="Số lượng dự án tương tự nhân sự đã từng làm")

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
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("❌ Thiếu GEMINI_API_KEY trong file .env")

    # Cấu hình Model
    # Dùng gemini-2.5-flash hoặc gemini-2.5-pro (nếu bạn có quyền truy cập)
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-pro", 
        temperature=0, # Temperature = 0 để đảm bảo tính nhất quán, không sáng tạo
        google_api_key=api_key,
        convert_system_message_to_human=True
    )

    # Ép kiểu đầu ra theo Pydantic Schema
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
    
    print(f"🤖 [Extract] Đang gửi dữ liệu tới Gemini ...")
    try:
        result = chain.invoke({"context": full_context_text})
        print("✅ [Extract] Trích xuất dữ liệu thành công!")
        return cast(BiddingData, result)
    except Exception as e:
        print(f"❌ [Extract] Lỗi khi gọi Gemini API: {e}")
        raise e
# --- HÀM TRÍCH XUẤT LOCAL ---
# def extract_bid_info(full_context_text: str) -> BiddingData:
#     """
#     Sử dụng Ollama (Local LLM) để trích xuất thông tin.
#     Không tốn phí, bảo mật dữ liệu.
#     """
    
#     # Cấu hình Model Local
#     # model: tên model bạn đã pull về (qwen2.5:14b hoặc qwen2.5:7b)
#     # num_ctx: Quan trọng! Tăng cửa sổ ngữ cảnh để đọc được hồ sơ dài.
#     llm = ChatOllama(
#         model="qwen2.5:7b", 
#         temperature=0,        # Quan trọng: 0 để loại bỏ sự sáng tạo
#         num_ctx=8192,         # Đảm bảo đọc hết hồ sơ
#         repeat_penalty=1.1,   # Tránh lặp từ (tùy chọn)
#         top_k=10,             # Giới hạn không gian lấy mẫu để tập trung vào từ khóa chính xác
#     )

#     # Ép kiểu đầu ra JSON
#     structured_llm = llm.with_structured_output(BiddingData)

#     prompt = ChatPromptTemplate.from_messages([
#         ("system", """
#         Bạn là một Hệ thống Trích xuất Dữ liệu Hồ sơ thầu (Bidding Data Extractor).
#         Nhiệm vụ của bạn là đọc văn bản và điền dữ liệu vào khuôn mẫu JSON chính xác từng ký tự.

#         ### QUY TẮC BẤT DI BẤT DỊCH (NGHIÊM CẤM VI PHẠM):
        
#         1. NGUYÊN TẮC "COPY-PASTE":
#            - Tuyệt đối KHÔNG dịch thuật ngữ (Ví dụ: Thấy "Chỉ huy trưởng" -> Ghi "Chỉ huy trưởng". CẤM ghi "Site Manager").
#            - Tuyệt đối KHÔNG tóm tắt chức danh (Ví dụ: Thấy "Cán bộ kỹ thuật phụ trách thi công phần điện" -> Ghi đầy đủ, không được cắt bớt thành "Cán bộ điện").

#         2. XỬ LÝ SỐ LIỆU & TIỀN TỆ:
#            - Với số tiền (Doanh thu, Hợp đồng): Hãy cố gắng loại bỏ chữ (VNĐ, đồng, tỷ), chỉ giữ lại con số thuần túy.
#            - Nếu văn bản ghi "3 năm" -> trích xuất số: 3.
#            - Nếu văn bản ghi "01 người" -> trích xuất số: 1.

#         3. TÍNH TRUNG THỰC:
#            - Chỉ trích xuất thông tin CÓ trong văn bản.
#            - Nếu trường nào không tìm thấy thông tin -> Trả về null (hoặc mảng rỗng []).
#            - KHÔNG được tự ý điền dữ liệu mặc định.

#         ### VÍ DỤ MINH HỌA:
#         Input: "Yêu cầu 01 Chỉ huy trưởng công trường, có bằng Đại học Xây dựng, kinh nghiệm 5 năm."
#         Output Đúng: {{ "position": "Chỉ huy trưởng công trường", "quantity": 1, "experience_years": 5, "qualification": "Đại học Xây dựng" }}
#         Output SAI: {{ "position": "Project Manager", "quantity": 1, "experience_years": 15 ... }} (Sai vì tự dịch và bịa số năm)
#         """),
#         ("human", "Hãy trích xuất thông tin từ văn bản dưới đây:\n\n{context}")
#     ])

#     chain = prompt | structured_llm
    
#     print(f"🤖 [Local-Ollama] Đang phân tích dữ liệu trên máy của bạn (Model: Qwen2.5)...")
#     try:
#         # Gọi invoke
#         result = chain.invoke({"context": full_context_text})
#         print("✅ [Local-Ollama] Trích xuất thành công!")
#         return cast(BiddingData, result)
    
#     except Exception as e:
#         print(f"❌ [Local-Ollama] Lỗi: {e}")
#         # Mẹo debug: Đôi khi model local trả về JSON lỗi nhẹ, có thể dùng OutputFixingParser nếu cần
#         raise e