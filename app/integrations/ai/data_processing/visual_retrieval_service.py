import os
import base64
from io import BytesIO
from typing import List, Dict
from litepali import LitePali, ImageFile
from PIL import Image
import time

# Import Docling Service để nhờ cắt ảnh
from app.integrations.ai.provider.docling_service import get_docling_service

class VisualRetrievalService:
    def __init__(self, index_path=None):
        # --- SỬA ĐOẠN NÀY ĐỂ TRỎ ĐÚNG PATH ---
        if index_path is None:
            # 1. Lấy thư mục gốc dự án (giả định chạy từ root)
            project_root = os.getcwd()
            
            # 2. Trỏ vào: app/infrastructure/vectordb/visual_index_storage
            self.index_path = os.path.join(
                project_root, 
                "app", "infrastructure", "vectordb", "visual_index_storage"
            )
        else:
            self.index_path = index_path

        # 3. Tạo thư mục cha nếu chưa có (quan trọng)
        os.makedirs(self.index_path, exist_ok=True)
        
        print(f"📂 Visual Index sẽ được lưu tại: {self.index_path}")
        # -------------------------------------

        print("🐢 [LitePali] Đang khởi động Model (Sẽ tốn nhiều RAM)...")
        self.litepali = LitePali() 
        
        # Kiểm tra xem folder đã có dữ liệu index chưa
        # (LitePali thường tạo file config.json hoặc index.bin trong folder này)
        if os.path.exists(self.index_path) and os.listdir(self.index_path):
            print(f"👁️ [LitePali] Đang tải index cũ từ {self.index_path}...")
            try:
                self.litepali.load_index(self.index_path)
            except Exception as e:
                print(f"⚠️ Không thể tải index cũ (có thể do lỗi version hoặc file hỏng): {e}. Sẽ tạo mới.")
    # def __init__(self, index_path="visual_index_storage"):
    #     self.index_path = index_path
    #     print("🐢 [LitePali] Đang khởi động Model (Sẽ tốn nhiều RAM)...")
    #     self.litepali = LitePali() 
        
    #     if os.path.exists(index_path):
    #         print(f"👁️ [LitePali] Đang tải index cũ từ {index_path}...")
    #         try:
    #             self.litepali.load_index(index_path)
    #         except Exception as e:
    #             print(f"⚠️ Không thể tải index cũ: {e}. Sẽ tạo mới.")

    def ingest_images_from_pdf(self, pdf_path: str, document_id: str, metadata: Dict = {}):
        """
        Luồng mới: Docling cắt ảnh -> LitePali vector hóa.
        Cập nhật: Xử lý theo BATCH (cuốn chiếu) để không bị tràn RAM.
        """
        print(f"🚀 [Visual Pipeline] Bắt đầu xử lý file: {os.path.basename(pdf_path)}")
        
        try:
            # BƯỚC 1: Dùng Docling để cắt ảnh (Crop)
            docling = get_docling_service()
            # --- SỬA ĐOẠN NÀY ---
            # Xác định đường dẫn gốc (nếu chưa có biến global PROJECT_ROOT thì dùng os.getcwd())
            project_root = os.getcwd() 
            
            # Trỏ thẳng vào thư mục: app/infrastructure/temp_storage/temp_visuals
            temp_dir = os.path.join(
                project_root, 
                "app", "infrastructure", "temp_storage", "temp_visuals"
            )
            
            # Đảm bảo thư mục tồn tại trước khi lưu
            os.makedirs(temp_dir, exist_ok=True)
            # --------------------
            # temp_dir = "temp_visuals" # Thư mục tạm chứa ảnh cắt
            
            # Gọi hàm mới bên DoclingService
            cropped_images = docling.extract_images_from_pdf(pdf_path, temp_dir)
            
            total_imgs = len(cropped_images)
            if total_imgs == 0:
                print("⚠️ Không tìm thấy hình ảnh/sơ đồ nào trong file PDF này. Bỏ qua bước Visual Index.")
                return

            print(f"📥 Đã tìm thấy {total_imgs} ảnh. Bắt đầu xử lý cuốn chiếu (Batch)...")

            # BƯỚC 2: Xử lý theo Batch (Chia để trị)
            # Thay vì nạp hết vào RAM, ta làm 5 ảnh một -> Lưu -> Xả RAM -> Làm tiếp
            BATCH_SIZE = 5 
            
            for i in range(0, total_imgs, BATCH_SIZE):
                # Lấy ra 5 ảnh tiếp theo
                batch = cropped_images[i : i + BATCH_SIZE]
                current_batch_num = (i // BATCH_SIZE) + 1
                print(f"\n🔄 Đang xử lý Batch {current_batch_num} ({len(batch)} ảnh)...")

                # [QUAN TRỌNG] Load lại index cũ trước khi thêm mới để đảm bảo tính liên tục
                if os.path.exists(self.index_path):
                    try:
                        self.litepali.load_index(self.index_path)
                    except:
                        pass # Nếu lỗi load thì thôi, coi như tạo mới hoặc append tiếp

                for img_info in batch:
                    # Tạo metadata chi tiết
                    page_meta = metadata.copy()
                    page_meta.update({
                        "source": pdf_path,
                        "page_number": img_info["page_number"],
                        "is_cropped_figure": True # Đánh dấu đây là ảnh cắt
                    })
                    
                    # Thêm vào hàng đợi xử lý
                    self.litepali.add(ImageFile(
                        path=img_info["path"],
                        document_id=document_id,
                        page_id=img_info["page_number"],
                        metadata=page_meta
                    ))

                # BƯỚC 3: Chạy AI (Inference) ngay cho Batch này
                print(f"   🧠 Đang chạy AI cho Batch {current_batch_num}...")
                self.litepali.process() 
                
                # BƯỚC 4: Lưu ngay xuống ổ cứng
                # Việc này giúp giải phóng bộ nhớ đệm của Batch vừa rồi
                self.litepali.save_index(self.index_path)
                print(f"   💾 Đã lưu xong Batch {current_batch_num}. RAM đã được giải phóng.")
            
            print(f"✅ [LitePali] HOÀN TẤT TOÀN BỘ {total_imgs} ẢNH!")
            
        except Exception as e:
            print(f"❌ Lỗi Visual Ingest: {e}")
            # Không raise e để tránh crash luồng chính, chỉ log lỗi visual
            
    def search_visuals(self, query: str, top_k: int = 2) -> List[Dict]:
        print(f"👁️ Visual Search: '{query}'")
        try:
            results = self.litepali.search(query, k=top_k)
            processed_results = []
            for res in results:
                image_obj = res['image']
                pil_img = None
                
                try:
                    # --- PHẦN SỬA LỖI QUAN TRỌNG ---
                    
                    # Trường hợp 1: image_obj là instance của ImageFile (LitePali wrapper)
                    if isinstance(image_obj, ImageFile):
                        if hasattr(image_obj, 'path') and image_obj.path:
                            pil_img = Image.open(image_obj.path)
                        else:
                            print(f"⚠️ ImageFile object bị thiếu path.")
                            continue

                    # Trường hợp 2: image_obj là đường dẫn string
                    elif isinstance(image_obj, str):
                        if os.path.exists(image_obj):
                            pil_img = Image.open(image_obj)
                        else:
                            print(f"⚠️ Không tìm thấy file ảnh: {image_obj}")
                            continue

                    # Trường hợp 3: image_obj đã là PIL Image (ít gặp nhưng có thể)
                    elif isinstance(image_obj, Image.Image):
                        pil_img = image_obj
                    
                    # Trường hợp 4: Lọc bỏ nhiễu (float, int, None...)
                    else:
                        # Bỏ qua nếu gặp float hoặc các kiểu lạ
                        continue

                    # --- XỬ LÝ ẢNH SANG BASE64 ---
                    if pil_img:
                        buffered = BytesIO()
                        # Convert sang RGB để tránh lỗi nếu ảnh gốc là RGBA khi lưu JPEG
                        if pil_img.mode in ("RGBA", "P"): 
                            pil_img = pil_img.convert("RGB")
                            
                        pil_img.save(buffered, format="JPEG")
                        img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
                        
                        processed_results.append({
                            "score": res['score'],
                            "base64": img_b64,
                            "metadata": res.get('metadata', {})
                        })
                        
                except Exception as inner_e:
                    print(f"⚠️ Lỗi khi xử lý 1 ảnh trong kết quả tìm kiếm: {inner_e}")
                    continue

            return processed_results
        except Exception as e:
            print(f"⚠️ Lỗi Visual Search (Tổng quát): {e}")
            return []

# Singleton
visual_service = VisualRetrievalService()
def get_visual_service():
    return visual_service