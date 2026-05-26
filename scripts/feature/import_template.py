import os
from sqlalchemy.orm import Session
from app.infrastructure.database.database import SessionLocal
from app.modules.drafting.model import DocumentTemplate

# Tên file HTML bạn vừa upload
FILE_NAME = "Mẫu HTML Biện Pháp Thi Công T3.html"

def import_html_template():
    # 1. Kiểm tra file có tồn tại không
    if not os.path.exists(FILE_NAME):
        print(f"❌ Lỗi: Không tìm thấy file '{FILE_NAME}'")
        return

    # 2. Đọc nội dung file
    try:
        with open(FILE_NAME, "r", encoding="utf-8") as f:
            html_content = f.read()
            
        # (Tùy chọn) Làm sạch nội dung nếu cần
        # Ví dụ: Chỉ lấy nội dung trong thẻ <body> nếu editor của bạn bị lỗi khi nhận full HTML
        # Ở đây tôi giữ nguyên toàn bộ file để bảo toàn style CSS của bạn
            
    except Exception as e:
        print(f"❌ Lỗi đọc file: {e}")
        return

    # 3. Kết nối DB và Insert
    db: Session = SessionLocal()
    try:
        # Tạo object Template
        new_template = DocumentTemplate(
            title="Biện Pháp Thi Công (Mẫu T3)",
            content=html_content,       # Nội dung HTML
            category="TECH",            # Phân loại: Kỹ thuật / Biện pháp
            description="Mẫu thuyết minh biện pháp thi công chi tiết (Bao gồm An toàn, PCCC, Vệ sinh môi trường)",
            is_active=True
        )
        
        db.add(new_template)
        db.commit()
        db.refresh(new_template)

        print("✅ Đã import thành công!")
        print(f"   - ID: {new_template.id}")
        print(f"   - Tiêu đề: {new_template.title}")
        print(f"   - Category: {new_template.category}")
        
    except Exception as e:
        print(f"❌ Lỗi khi lưu vào DB: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    import_html_template()
    