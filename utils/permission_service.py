from sqlalchemy.orm import Session
from sqlalchemy import select, or_
from models import BiddingTask, TaskAssignment, User, UserRole, TaskTag

def get_user_allowed_tags(db: Session, user: User, project_id: int) -> set[str]:
    """
    Trả về tập hợp các TAG mà user được phép truy cập trong dự án.
    
    Logic cập nhật:
    1. VIP (Manager/Admin): Xem hết.
    2. Nhân viên thường, lấy Task nếu:
       - Được giao đích danh (assignee_id).
       - Được giao đích danh qua bảng phụ (assigned_user_id).
       - HOẶC: Task được giao cho Phòng/Ban mà User đang thuộc về (assigned_unit_id == user.org_unit_id).
    """
    
    # 1. Nhóm VIP: Xem hết (Full quyền)
    VIP_ROLES = [UserRole.ADMIN, UserRole.MANAGER, UserRole.BID_MANAGER]
    if user.role in VIP_ROLES:
        # Trả về tất cả các tag có trong Enum
        return {tag.value for tag in TaskTag}

    # 2. Lấy TOÀN BỘ Task của dự án để dựng cây phả hệ (Parent/Child)
    # Mục đích: Để nếu task con không có tag thì leo lên tìm tag của cha
    all_tasks = db.execute(
        select(BiddingTask.id, BiddingTask.parent_task_id, BiddingTask.tag)
        .where(BiddingTask.bidding_project_id == project_id)
    ).all()
    
    # Map để tra cứu nhanh: {task_id: {'parent': ..., 'tag': ...}}
    task_map = {
        row.id: {"parent_id": row.parent_task_id, "tag": row.tag} 
        for row in all_tasks
    }

    # 3. Xây dựng điều kiện lọc (User sở hữu task khi nào?)
    filter_conditions = [
        BiddingTask.assignee_id == user.user_id,             # 1. Giao trực tiếp trên bảng Task
        TaskAssignment.assigned_user_id == user.user_id,     # 2. Giao trực tiếp trên bảng Assignment
    ]

    # --- ĐIỂM QUAN TRỌNG: LOGIC GIAO CHO PHÒNG ---
    # Nếu user có thuộc một phòng ban nào đó, thêm điều kiện tìm task của phòng đó
    if user.org_unit_id is not None:
        filter_conditions.append(
            TaskAssignment.assigned_unit_id == user.org_unit_id
        )
    # ---------------------------------------------

    # 4. Thực hiện Query tìm ID các task mà User liên quan
    assigned_query = select(BiddingTask.id).outerjoin(TaskAssignment, BiddingTask.assignments).where(
        BiddingTask.bidding_project_id == project_id,
        or_(*filter_conditions) # Dùng toán tử OR cho các điều kiện trên
    )
    
    my_task_ids = db.execute(assigned_query).scalars().all()

    # 5. Truy vết ngược lên cha để tìm Tag (Resolution Logic)
    allowed_tags = set()

    for task_id in my_task_ids:
        current_id = task_id
        
        # Vòng lặp leo cây (tối đa 10 cấp để an toàn)
        depth = 0
        while current_id is not None and depth < 10:
            node = task_map.get(current_id)
            if not node: break # Task không tồn tại hoặc dữ liệu lỗi

            # A. Nếu tìm thấy Tag ở node hiện tại -> Lấy luôn
            if node["tag"] is not None:
                allowed_tags.add(node["tag"].value) # Lưu tag (VD: 'FINANCE')
                break 
            
            # B. Nếu chưa thấy -> Leo lên cha
            current_id = node["parent_id"]
            depth += 1
            
    return allowed_tags