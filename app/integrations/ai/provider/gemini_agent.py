import os
import google.generativeai as genai
from dotenv import load_dotenv
from app.integrations.google.mcp_drive.service import drive_service

# Load biến môi trường
load_dotenv()

class GeminiAgent:
    def __init__(self):
        # 1. Cấu hình API Key
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("⚠️ Cảnh báo: Chưa cấu hình GEMINI_API_KEY trong file .env")
            self.model = None
            self.chat_session = None
            return

        genai.configure(api_key=api_key)

        # 2. Định nghĩa Tools (Các hàm AI được phép gọi)
        self.tools = [
            self.list_all_projects,
            self.create_new_project,
            self.search_files_in_repository,
            self.clone_documents_to_project
        ]

        # 3. Khởi tạo Model với Tools
        self.model = genai.GenerativeModel(
            model_name='gemini-2.5-flash', # Dùng bản Flash mới nhất để gọi tool nhanh
            tools=self.tools,
            system_instruction="""
            Bạn là Trợ lý Ảo quản lý Hệ thống Đấu thầu (Bidding AI).
            Bạn có quyền truy cập trực tiếp vào Google Drive của công ty thông qua các công cụ được cung cấp.

            QUY TẮC HOẠT ĐỘNG:
            1. Trả lời ngắn gọn, súc tích bằng tiếng Việt.
            2. Khi người dùng yêu cầu thao tác (tạo dự án, tìm file, copy file), hãy TỰ ĐỘNG GỌI TOOL tương ứng.
            3. Nếu là yêu cầu soạn thảo văn bản (drafting), hãy trả về định dạng HTML chuẩn.
            4. Đối với task_type, hãy tự suy luận từ yêu cầu (VD: "hồ sơ năng lực" -> LEGAL, "báo cáo tài chính" -> FINANCE).
            """
        )
        
        # 4. Khởi tạo Chat Session (để nhớ ngữ cảnh hội thoại)
        # enable_automatic_function_calling=True giúp AI tự chạy hàm Python và lấy kết quả trả về
        self.chat_session = self.model.start_chat(enable_automatic_function_calling=True)

    # --- PUBLIC METHOD ĐỂ GỌI TỪ BÊN NGOÀI ---
    def chat(self, prompt: str) -> str:
        """
        Hàm chính để giao tiếp với AI.
        Router sẽ gọi hàm này.
        """
        if not self.chat_session:
            return "Lỗi: Chưa kết nối được với Gemini (Thiếu API Key)."
            
        try:
            # Gửi tin nhắn -> AI tự gọi tool (nếu cần) -> Trả về text cuối cùng
            response = self.chat_session.send_message(prompt)
            return response.text
        except Exception as e:
            print(f"❌ Lỗi gọi Gemini: {e}")
            return f"Đã xảy ra lỗi khi xử lý yêu cầu: {str(e)}"

    # ======================================================
    # ĐỊNH NGHĨA CÁC TOOL (Phương thức nội bộ)
    # ======================================================

    def list_all_projects(self):
        """
        Xem danh sách các Dự án hiện có trong thư mục gốc.
        Trả về ID và Tên của các dự án.
        """
        print("\n[AI Action] 🔍 Đang quét danh sách dự án...")
        items = drive_service.list_files_in_folder(None) # None = Root
        return [{"name": i['name'], "id": i['id']} for i in items if 'folder' in i['mimeType']]

    def create_new_project(self, project_name: str):
        """
        Tạo một dự án thầu mới.
        Hệ thống sẽ tự động tạo folder cha và 7 folder con (Pháp lý, Kỹ thuật, Tài chính...) bên trong.
        """
        print(f"\n[AI Action] 🔨 Đang khởi tạo dự án: '{project_name}'...")
        result = drive_service.create_project_tree(project_name)
        return result

    def search_files_in_repository(self, query: str):
        """
        Tìm kiếm tài liệu và thư mục trong kho.
        Kết quả trả về dạng CÂY (Tree) để biết file nào nằm trong folder nào.
        """
        print(f"\n[AI Action] 🔎 Đang tìm kiếm: '{query}'...")
        
        flat_results = drive_service.search_files(query)
        item_map = {}
        
        for item in flat_results:
            is_folder = 'application/vnd.google-apps.folder' in item.get('mimeType', '')
            clean_item = {
                "id": item['id'],
                "name": item['name'],
                "type": "📁 FOLDER" if is_folder else "📄 FILE",
                "parents": item.get('parents', []),
                "children": [] 
            }
            item_map[item['id']] = clean_item

        tree_roots = []
        for item_id, item in item_map.items():
            parent_id = item['parents'][0] if item['parents'] else None
            if parent_id and parent_id in item_map:
                item_map[parent_id]['children'].append(item)
            else:
                tree_roots.append(item)
                
        def clean_output(nodes):
            for node in nodes:
                node.pop("parents", None)
                if node["children"]:
                    clean_output(node["children"])
            return nodes

        return clean_output(tree_roots)

    def clone_documents_to_project(self, project_name_or_id: str, task_type: str, file_ids: list):
        """
        Copy (Clone) các tài liệu mẫu vào folder chuyên môn của dự án.
        
        Args:
            project_name_or_id: Tên hoặc ID của dự án đích.
            task_type: Loại hồ sơ (HR, LEGAL, TECH, FINANCE, DEVICE, CONTRACT, OTHER).
            file_ids: Danh sách ID file cần copy.
        """
        print(f"\n[AI Action] 🚀 Đang clone {len(file_ids)} file sang dự án '{project_name_or_id}' ({task_type})...")
        
        # Logic tìm ID dự án từ tên (nếu cần)
        project_id = project_name_or_id
        # ID Google Drive thường dài > 10 ký tự và ko chứa dấu cách
        if " " in project_id or len(project_id) < 10: 
            all_projs = drive_service.list_files_in_folder(None)
            for p in all_projs:
                if p['name'].lower() == project_name_or_id.lower():
                    project_id = p['id']
                    break
        
        result = drive_service.clone_files_for_task(project_id, task_type, file_ids)
        if not result:
            return "Lỗi: Không tìm thấy dự án hoặc folder đích."
        return result

# ======================================================
# KHỞI TẠO SINGLETON OBJECT
# Các file khác sẽ import biến này để dùng
# ======================================================
gemini_agent = GeminiAgent()