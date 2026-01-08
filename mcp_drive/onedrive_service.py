import os
import io
import asyncio
import requests
import msal
import urllib.parse
import tempfile
import zipfile
import collections
from typing import List, Optional, Any, Dict
from fastapi import UploadFile
from dotenv import load_dotenv

load_dotenv()

GRAPH_API_ENDPOINT = 'https://graph.microsoft.com/v1.0'

class OneDriveService:
    def __init__(self):
        self.client_id = os.getenv("AZURE_CLIENT_ID")
        self.target_user_id = os.getenv("AZURE_DRIVE_OWNER_ID")
        
        # Xử lý ID Folder
        raw_root_id = os.getenv("ONEDRIVE_ROOT_FOLDER_ID", "root")
        self.ROOT_FOLDER_ID = urllib.parse.unquote(raw_root_id)

        # [THAY ĐỔI] Lấy Refresh Token từ env
        self.refresh_token = os.getenv("ONEDRIVE_REFRESH_TOKEN")
        
        # Scopes
        self.scopes = ["Files.ReadWrite.All", "User.Read"]

        self.app = None
        if self.client_id:
            # Public Client cho Personal Account
            self.app = msal.PublicClientApplication(
                client_id=self.client_id,
                authority="https://login.microsoftonline.com/common"
            )
        
        # Session Setup
        self.session = requests.Session()
        self.session.verify = False 
        self.session.trust_env = False 
        self.session.headers.update({
            "User-Agent": "FastAPI_OneDrive_Bot/1.0",
            "Accept": "application/json"
        })
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _get_headers(self) -> Optional[Dict[str, str]]:
        """Lấy Access Token từ Refresh Token (Chạy ngầm vĩnh viễn)"""
        if not self.app or not self.refresh_token: 
            print("❌ Thiếu Client ID hoặc Refresh Token trong .env")
            return None
        
        result = None
        
        # 1. Thử lấy từ cache (nếu có phiên trước đó)
        accounts = self.app.get_accounts()
        if accounts:
            result = self.app.acquire_token_silent(self.scopes, account=accounts[0])

        # 2. Nếu không có cache hoặc hết hạn, dùng Refresh Token để lấy mới
        if not result:
            try:
                result = self.app.acquire_token_by_refresh_token(
                    self.refresh_token, 
                    scopes=self.scopes
                )
                # [Mẹo] Nếu MS trả về refresh token mới, bạn có thể lưu lại vào DB/File để dùng lần sau
                # nhưng với script đơn giản, token cũ thường sống được 90 ngày.
            except Exception as e:
                print(f"❌ Exception Refresh Token: {e}")
                return None

        if result and "access_token" in result:
            return {
                "Authorization": f"Bearer {result['access_token']}",
                "Content-Type": "application/json"
            }
        else:
            print(f"❌ Lỗi Refresh Token: {result.get('error_description') if result else 'Unknown'}")
            return None

    def _get_base_url(self):
        if self.target_user_id:
             return f"{GRAPH_API_ENDPOINT}/drives/{self.target_user_id}"
        return f"{GRAPH_API_ENDPOINT}/me/drive"

    # --- CÁC HÀM KHÁC GIỮ NGUYÊN KHÔNG ĐỔI ---
    async def _run_in_thread(self, func, *args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)

    def list_files_in_folder(self, folder_id: Optional[str] = None):
        headers = self._get_headers()
        if not headers: return []
        
        target_id = folder_id if folder_id else self.ROOT_FOLDER_ID
        target_id = urllib.parse.unquote(target_id)

        url = f"{self._get_base_url()}/items/{target_id}/children"
        
        try:
            response = self.session.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                items = data.get("value", [])
                mapped_items = []
                for item in items:
                    is_folder = "folder" in item
                    mime_type = "application/vnd.google-apps.folder" if is_folder else item.get("file", {}).get("mimeType", "application/octet-stream")
                    mapped_items.append({
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "mimeType": mime_type,
                        "webViewLink": item.get("webUrl"),
                        "downloadUrl": item.get("@microsoft.graph.downloadUrl"),
                        "modifiedTime": item.get("lastModifiedDateTime"),
                        "parents": [target_id]
                    })
                return mapped_items
            else:
                print(f"❌ API List Error {response.status_code}: {response.text}")
                return []
        except Exception as e:
            print(f"❌ Exception List Files: {e}")
            return []

    async def upload_file_with_security(self, file: UploadFile, folder_id: str, security_level: int = 1):
        try:
            file_content = await file.read()
            def _blocking_upload():
                headers = self._get_headers()
                if not headers: return None
                filename = file.filename if file.filename else "unknown"
                safe_name = filename.replace(" ", "_")
                url = f"{self._get_base_url()}/items/{folder_id}:/{safe_name}:/content"
                headers.update({"Content-Type": "application/octet-stream"})
                response = self.session.put(url, headers=headers, data=file_content)
                if response.status_code in [200, 201]:
                    data = response.json()
                    return {"id": data.get("id"), "name": data.get("name"), "status": "success", "link": data.get("webUrl")}
                return None
            return await self._run_in_thread(_blocking_upload)
        except Exception: return None

    def create_project_tree(self, project_name: str):
        # 1. Tạo folder dự án
        print(f"🔨 Creating Project: {project_name}")
        project_id = self.create_folder(project_name, self.ROOT_FOLDER_ID)
        if not project_id: return None

        structure_config = [
            {"name": "1. HSPL, BCTC, HDTT, TTLD", "children": ["Hồ sơ pháp lý", "Báo cáo tài chính", "Hợp đồng tương tự"]},
            {"name": "2. BLDT, CKTD", "children": []},
            {"name": "3. BPTC", "children": ["Nhân sự", "Máy móc", "Biện pháp thi công"]},
            {"name": "4. Hồ sơ VT", "children": []},
            {"name": "5. Giá", "children": []}
        ]
        log = []
        for p in structure_config:
            p_id = self.create_folder(p["name"], project_id)
            if p_id:
                log.append({"name": p["name"], "id": p_id, "type": "PARENT"})
                for c_name in p["children"]:
                    c_id = self.create_folder(c_name, p_id)
                    if c_id: log.append({"name": c_name, "id": c_id, "type": "CHILD"})
        return {"project_name": project_name, "project_id": project_id, "structure_log": log}

    def create_folder(self, folder_name: str, parent_id: Optional[str] = None) -> Optional[str]:
        headers = self._get_headers()
        if not headers: return None
        target = parent_id if parent_id else self.ROOT_FOLDER_ID
        url = f"{self._get_base_url()}/items/{target}/children"
        body = {"name": folder_name, "folder": {}, "@microsoft.graph.conflictBehavior": "rename"}
        try:
            res = self.session.post(url, headers=headers, json=body)
            if res.status_code in [200, 201]: return res.json().get("id")
            return None
        except: return None

    def get_file_content(self, file_id: str):
        headers = self._get_headers()
        if not headers: return None
        url = f"{self._get_base_url()}/items/{file_id}/content"
        try:
            res = self.session.get(url, headers=headers, stream=True, allow_redirects=True)
            return res.content if res.status_code == 200 else None
        except: return None

    def zip_folder_recursive(self, root_folder_id: str):
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        temp_zip_path = temp_zip.name
        temp_zip.close()
        try:
            with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                queue = collections.deque([(root_folder_id, "")])
                while queue:
                    cid, cpath = queue.popleft()
                    items = self.list_files_in_folder(cid)
                    for item in items:
                        safe_name = item['name'].replace("/", "_")
                        zpath = os.path.join(cpath, safe_name)
                        if item['mimeType'] == "application/vnd.google-apps.folder":
                            queue.append((item['id'], zpath))
                            zf.writestr(zpath + "/", "")
                        else:
                            content = self.get_file_content(item['id'])
                            if content: zf.writestr(zpath, content)
            return temp_zip_path
        except: return None

    def count_files_recursive(self, folder_id: Optional[str] = None):
        target = folder_id if folder_id else self.ROOT_FOLDER_ID
        count = 0
        queue = collections.deque([target])
        while queue:
            curr = queue.popleft()
            items = self.list_files_in_folder(curr)
            for item in items:
                if item['mimeType'] == "application/vnd.google-apps.folder":
                    queue.append(item['id'])
                else:
                    count += 1
        return count

onedrive_service = OneDriveService()