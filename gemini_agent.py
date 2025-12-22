import os
import google.generativeai as genai
from dotenv import load_dotenv

# Import service Drive mà bạn đã viết (Tay chân của AI)
from mcp_drive.service import drive_service

# Load cấu hình
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("❌ Lỗi: Chưa có GEMINI_API_KEY trong file .env")
    exit(1)

genai.configure(api_key=GEMINI_API_KEY)

# ======================================================
# 1. ĐỊNH NGHĨA CÁC CÔNG CỤ (TOOLS) CHO AI
# Gemini sẽ đọc phần mô tả (docstring) để biết khi nào dùng hàm nào
# ======================================================

def list_all_projects():
    """
    Xem danh sách các Dự án hiện có trong thư mục gốc.
    Trả về ID và Tên của các dự án.
    """
    print("\n[System] 🔍 AI đang quét danh sách dự án...")
    items = drive_service.list_files_in_folder(None) # None = Root
    # Chỉ lấy folder dự án để AI đỡ bị nhiễu
    return [{"name": i['name'], "id": i['id']} for i in items if 'folder' in i['mimeType']]

def create_new_project(project_name: str):
    """
    Tạo một dự án thầu mới.
    Hệ thống sẽ tự động tạo folder cha và 7 folder con (Pháp lý, Kỹ thuật, Tài chính...) bên trong.
    """
    print(f"\n[System] 🔨 AI đang khởi tạo dự án: '{project_name}'...")
    result = drive_service.create_project_tree(project_name)
    return result

def search_files_in_repository(query: str):
    """
    Tìm kiếm tài liệu và thư mục. 
    Kết quả trả về dạng CÂY (Tree) để biết file nào nằm trong folder nào.
    """
    print(f"\n[System] 🔎 AI đang tìm (Dạng Tree) với từ khóa: '{query}'...")
    
    # 1. Lấy dữ liệu phẳng từ Service
    flat_results = drive_service.search_files(query)
    
    # 2. Xử lý Tree (Giống hệt bên Router)
    item_map = {}
    
    # Bước 2a: Map dữ liệu (Chỉ lấy field cần thiết cho AI để tiết kiệm Token)
    for item in flat_results:
        is_folder = 'application/vnd.google-apps.folder' in item.get('mimeType', '')
        clean_item = {
            "id": item['id'],
            "name": item['name'],
            "type": "📁 FOLDER" if is_folder else "📄 FILE",
            # "link": item['webViewLink'], # Có thể bỏ Link đi để AI đỡ bị rối mắt, chỉ cần ID và Tên
            "parents": item.get('parents', []),
            "children": [] 
        }
        item_map[item['id']] = clean_item

    # Bước 3: Build Tree
    tree_roots = []
    for item_id, item in item_map.items():
        parent_id = item['parents'][0] if item['parents'] else None
        
        # Nếu cha cũng nằm trong kết quả tìm kiếm -> Nhét vào con của cha
        if parent_id and parent_id in item_map:
            item_map[parent_id]['children'].append(item)
        else:
            # Nếu không tìm thấy cha trong đợt này -> Nó là Root
            tree_roots.append(item)
            
    # Bước 4: Clean up (Xóa trường 'parents' thừa đi cho gọn output)
    def clean_output(nodes):
        for node in nodes:
            node.pop("parents", None) # Xóa field parents ko cần thiết nữa
            if node["children"]:
                clean_output(node["children"]) # Đệ quy
        return nodes

    return clean_output(tree_roots)

def clone_documents_to_project(project_name_or_id: str, task_type: str, file_ids: list):
    """
    Copy (Clone) các tài liệu mẫu vào folder chuyên môn của dự án.
    
    Args:
        project_name_or_id: Tên hoặc ID của dự án đích.
        task_type: Loại hồ sơ. Chỉ chấp nhận các giá trị: 'HR' (Nhân sự), 'LEGAL' (Pháp lý), 'TECH' (Kỹ thuật/Biện pháp), 'FINANCE' (Tài chính), 'DEVICE' (Máy móc), 'CONTRACT' (Hợp đồng), 'OTHER' (Khác).
        file_ids: Danh sách các ID file cần copy (lấy từ kết quả tìm kiếm).
    """
    print(f"\n[System] 🚀 AI đang thực hiện Clone {len(file_ids)} file sang dự án '{project_name_or_id}' ({task_type})...")
    
    # Logic phụ: Nếu AI đưa tên dự án, ta phải tìm ra ID của nó
    project_id = project_name_or_id
    if not project_id.startswith("1"): # ID Google Drive thường dài và ko bắt đầu bằng tên
        all_projs = drive_service.list_files_in_folder(None)
        for p in all_projs:
            if p['name'].lower() == project_name_or_id.lower():
                project_id = p['id']
                break
    
    # Gọi hàm service
    result = drive_service.clone_files_for_task(project_id, task_type, file_ids)
    if not result:
        return "Không tìm thấy dự án hoặc folder đích. Hãy kiểm tra lại tên dự án."
    return result

# ======================================================
# 2. KHỞI TẠO GEMINI AGENT
# ======================================================

# Đóng gói các hàm vào danh sách công cụ
my_tools = [
    list_all_projects,
    create_new_project,
    search_files_in_repository,
    clone_documents_to_project
]

# Khởi tạo model với tools
model = genai.GenerativeModel(
    model_name='gemini-2.5-flash', # Bản Flash nhanh và rẻ, rất giỏi gọi tool
    tools=my_tools,
    system_instruction="""
    Bạn là Trợ lý Ảo quản lý Hệ thống Đấu thầu (Bidding AI).
    Bạn có quyền truy cập trực tiếp vào Google Drive của công ty.

    Quy tắc hoạt động:
    1. Trả lời ngắn gọn, thân thiện bằng tiếng Việt.
    2. Khi người dùng yêu cầu làm gì, hãy tự động gọi tool tương ứng.
    3. Nếu cần ID file để copy, hãy chủ động tìm kiếm (search) trước rồi mới copy.
    4. Đối với task_type, hãy tự suy luận từ yêu cầu (VD: "hồ sơ năng lực" -> LEGAL, "báo cáo tài chính" -> FINANCE).
    """
)

# Kích hoạt chế độ Chat tự động gọi hàm
chat_session = model.start_chat(enable_automatic_function_calling=True)

# ======================================================
# 3. GIAO DIỆN CHAT (CONSOLE)
# ======================================================

def run_chat():
    print("-------------------------------------------------------")
    print("🤖 BIDDING AI AGENT - KẾT NỐI GOOGLE DRIVE")
    print("   (Gõ 'exit' để thoát)")
    print("-------------------------------------------------------")

    while True:
        try:
            user_input = input("\n👤 Bạn: ")
            if user_input.lower() in ['exit', 'quit', 'bye']:
                print("👋 Tạm biệt!")
                break
            
            if not user_input.strip(): continue

            # Gửi tin nhắn cho AI -> AI tự chạy hàm Python -> AI trả lời
            response = chat_session.send_message(user_input)
            
            # In câu trả lời của AI
            print(f"🤖 AI: {response.text}")

        except Exception as e:
            print(f"❌ Lỗi: {e}")

if __name__ == "__main__":
    run_chat()