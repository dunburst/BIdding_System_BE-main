import logging
import os
from typing import List, Optional, cast
from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
import pathlib
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
import json
from langchain_core.output_parsers import JsonOutputParser
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Load biến môi trường
# Thử load từ file .env ở thư mục gốc (nếu script chạy từ folder con)
env_path = pathlib.Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)
# Fallback: load mặc định
load_dotenv()
# --- 1. SETUP LOGGER (Phần còn thiếu) ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    position: Optional[str] = Field(..., description="Vị trí công việc (Trích nguyên văn tiếng Việt, VD: 'Chỉ huy trưởng', KHÔNG dịch sang tiếng Anh)")#(VD: Chỉ huy trưởng, Cán bộ kỹ thuật)")
    quantity: Optional[int] = Field(1, description="Số lượng nhân sự yêu cầu")
    qualification: Optional[str] = Field(None, description="Yêu cầu bằng cấp, chứng chỉ chuyên môn(Đại học, Cao đẳng...)")
    experience_years: Optional[int] = Field(None, description="Số năm kinh nghiệm tối thiểu yêu cầu(Chỉ lấy số)")
    similar_project_exp: Optional[int] = Field(None, description="Số lượng dự án tương tự nhân sự đã từng làm")

class EquipmentReq(BaseModel):
    name: Optional[str] = Field(..., description="Tên máy móc thiết bị")
    quantity: Optional[int] = Field(1, description="Số lượng yêu cầu")
    specs: Optional[str] = Field(None, description="Thông số kỹ thuật / Công suất yêu cầu")

# Model tổng hợp (Root)
class BiddingData(BaseModel):
    section_1_general: GeneralInfo
    section_2_admin: AdminRequirements
    section_3_financial: FinancialRequirements
    section_4_personnel: List[PersonnelReq] = []
    section_5_equipment: List[EquipmentReq] = []
    
    # section_1_general: Optional[GeneralInfo] = Field(default=None)
    # section_2_admin: Optional[AdminRequirements] = Field(default=None)
    # section_3_financial: Optional[FinancialRequirements] = Field(default=None)

    # # List thì default là list rỗng
    # section_4_personnel: Optional[List[PersonnelReq]] = Field(default_factory=list)
    # section_5_equipment: Optional[List[EquipmentReq]] = Field(default_factory=list)

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
# def extract_bid_info(full_context_text: str) -> dict:
#     """
#     Hàm gọi AI trả về Dict (để dễ xử lý rỗng và merge thủ công).
#     """
#     api_key = os.getenv("DEEPSEEK_API_KEY") 
#     if not api_key: raise ValueError("❌ Chưa tìm thấy DEEPSEEK_API_KEY!")

#     llm = ChatOpenAI(
#         model="deepseek-chat",
#         api_key=SecretStr(api_key),
#         base_url="https://api.deepseek.com",
#         temperature=0.0, 
#         model_kwargs={
#             "max_tokens": 4096,
#             "response_format": {"type": "json_object"}}
#     )

#     prompt = ChatPromptTemplate.from_messages([
#         ("system", """
#         Bạn là Chuyên gia Đấu thầu. Nhiệm vụ là trích xuất dữ liệu JSON từ văn bản.
        
#         ### MỤC TIÊU QUAN TRỌNG:
#         1. **TÀI CHÍNH**: Doanh thu bình quân, Vốn lưu động.
#         2. **KINH NGHIỆM**: Tìm "Hợp đồng tương tự", "Công trình tương tự".
#            - `min_contract_value`: Giá trị hợp đồng (Chuyển "5 tỷ" -> 5000000000).
#            - `similar_contract_qty`: Số lượng.
#            - `similar_contract_desc`: Mô tả ngắn gọn (VD: "Giao thông cấp III").

#         ### CẤU TRÚC JSON:
#         {{
#             "section_2_admin": {{ "bid_security_value": "...", "contract_duration": "..." }},
#             "section_3_financial": {{ 
#                 "avg_revenue": "...", 
#                 "working_capital": "...",
#                 "min_contract_value": 0.0, 
#                 "similar_contract_qty": 0,
#                 "similar_contract_desc": "..."
#             }},
#             "section_4_personnel": [ {{ "position": "...", "quantity": 1, "experience_years": 0 }} ],
#             "section_5_equipment": [ {{ "name": "...", "quantity": 1, "specs": "..." }} ]
#         }}

#         ### QUY TẮC:
#         - Nếu không có dữ liệu: KHÔNG trả về trường đó (hoặc trả về null).
#         - Nếu đoạn văn vô nghĩa: Trả về object rỗng {{}}.
#         """),
#         ("human", "Văn bản hồ sơ thầu:\n\n{context}")
#     ])

#     chain = prompt | llm
    
#     try:
#         response = chain.invoke({"context": full_context_text})
#         # --- SỬA LỖI Ở ĐÂY ---
#         # Lấy content ra
#         content = response.content
        
#         # Nếu content không phải string (hiếm gặp với DeepSeek nhưng để chiều lòng Linter)
#         if not isinstance(content, str):
#             content = str(content)
            
#         if not content: return {}
        
#         return json.loads(content)
#     except Exception as e:
#         logger.warning(f"⚠️ [AI Chunk Error] {e}")
#         return {}

# def extract_list_from_large_context(full_text: str, data_type: str = "personnel") -> BiddingData:
#     """
#     Hàm xử lý file lớn: Cắt nhỏ -> Gọi AI -> Gộp kết quả
#     """
    
#     # 1. Cấu hình Chunk Size an toàn (8000 chars)
#     splitter = RecursiveCharacterTextSplitter(
#         chunk_size=8000, 
#         chunk_overlap=500,
#         separators=["\n\n", "\n", "##", ".", " ", ""]
#     )
    
#     chunks = splitter.split_text(full_text)
#     logger.info(f"🔪 Đã cắt context thành {len(chunks)} đoạn (8k chars).")

#     final_data = BiddingData()
#     final_data.section_4_personnel = []
#     final_data.section_5_equipment = []

#     for i, chunk in enumerate(chunks):
#         logger.info(f"🔄 Đang xử lý đoạn {i+1}/{len(chunks)} ({data_type})...")
        
#         try:
#             # --- ĐỊNH NGHĨA BIẾN raw_data Ở ĐÂY ---
#             raw_data = extract_bid_info(chunk)
            
#             # Nếu kết quả rỗng, bỏ qua
#             if not raw_data: 
#                 continue

#             # --- LOGIC GỘP DỮ LIỆU ---
            
#             # 1. Gộp Nhân sự
#             if data_type == "personnel" and "section_4_personnel" in raw_data:
#                 items = raw_data["section_4_personnel"]
#                 if items and isinstance(items, list):
#                     for item in items:
#                         # Convert dict -> Pydantic Object
#                         final_data.section_4_personnel.append(PersonnelReq(**item))

#             # 2. Gộp Thiết bị
#             elif data_type == "equipment" and "section_5_equipment" in raw_data:
#                 items = raw_data["section_5_equipment"]
#                 if items and isinstance(items, list):
#                     for item in items:
#                         final_data.section_5_equipment.append(EquipmentReq(**item))
            
#             # 3. Gộp Tài chính (Logic Merge thông minh)
#             elif data_type == "financial":
                
#                 # Merge Admin Section
#                 if "section_2_admin" in raw_data and raw_data["section_2_admin"]:
#                     new_admin = raw_data["section_2_admin"]
#                     if not final_data.section_2_admin:
#                         final_data.section_2_admin = AdminRequirements(**new_admin)
#                     else:
#                         # Chỉ update các trường có dữ liệu
#                         current = final_data.section_2_admin.model_dump(exclude_unset=True)
#                         for k, v in new_admin.items():
#                             if v is not None and v != "":
#                                 current[k] = v
#                         final_data.section_2_admin = AdminRequirements(**current)

#                 # Merge Financial Section
#                 if "section_3_financial" in raw_data and raw_data["section_3_financial"]:
#                     new_fin = raw_data["section_3_financial"]
#                     if not final_data.section_3_financial:
#                         final_data.section_3_financial = FinancialRequirements(**new_fin)
#                     else:
#                         current_fin = final_data.section_3_financial.model_dump(exclude_unset=True)
#                         for k, v in new_fin.items():
#                             # Logic: Chỉ ghi đè nếu giá trị mới khác None và khác 0
#                             if v is not None and v != "" and v != 0:
#                                 current_fin[k] = v
#                         final_data.section_3_financial = FinancialRequirements(**current_fin)
                
#         except Exception as e:
#             logger.error(f"⚠️ Lỗi xử lý đoạn {i+1}: {e}")
#             continue

#     total_p = len(final_data.section_4_personnel or [])
#     total_e = len(final_data.section_5_equipment or [])
#     logger.info(f"✅ Hoàn tất. Tổng: {total_p} NS, {total_e} TB.")
    
#     return final_data