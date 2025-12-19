class AbacAction:
    """
    Danh sách các hành động chuẩn trong hệ thống.
    Dùng class này trong Code để tránh gõ sai chính tả (Typo).
    """
    # --- BASIC CRUD ---
    VIEW = "VIEW"
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    LIST = "LIST"

    # --- NGHIỆP VỤ ĐẤU THẦU (BIDDING) ---
    APPROVE_BID = "APPROVE_BID"       # Phê duyệt gói thầu
    REJECT_BID = "REJECT_BID"         # Từ chối/Trả về
    SUBMIT_BID = "SUBMIT_BID"         # Nộp thầu
    EVALUATE_BID = "EVALUATE_BID"     # Chấm thầu
    OPEN_BID = "OPEN_BID"             # Mở thầu
    
    # --- NGHIỆP VỤ DỰ ÁN ---
    CREATE_PROJECT = "CREATE_PROJECT" # Tạo dự án mới

    # --- NGHIỆP VỤ KHÁC ---
    ASSIGN_TASK = "ASSIGN_TASK"       # Giao việc
    EXPORT_EXCEL = "EXPORT_EXCEL"     # Xuất báo cáo
    
    @classmethod
    def list_all(cls):
        """Helper để lấy danh sách gợi ý cho Frontend"""
        # SỬA LỖI TẠI ĐÂY:
        # Chỉ lấy những attribute nào là chuỗi (str) và không bắt đầu bằng __
        return [value for key, value in cls.__dict__.items() 
                if not key.startswith("__") and isinstance(value, str)]