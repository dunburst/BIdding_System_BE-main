from sqlalchemy.orm import Session
from sqlalchemy import select, or_
from typing import Dict

# Import đầy đủ các model cần thiết
from app.modules.users.model import User, UserRole
from app.core.utils.enum import TaskTag
from app.modules.bidding.task.model import BiddingTask, TaskAssignment
from app.modules.bidding.project.model import BiddingProject

def get_user_allowed_tags_with_name(db: Session, user: User, project_id: int) -> Dict[str, str]:
    """
    Trả về Dictionary các TAG mà user được phép truy cập.
    Format: { "TAG_CODE": "Tên Dự Án Cấp Quyền" }
    VD: { "FINANCE": "Dự án Cầu Đường 1" }
    """
    
    # 0. Lấy Tên Dự Án hiện tại (Để hiển thị làm nguồn cấp quyền)
    project = db.get(BiddingProject, project_id)
    project_name = project.name if project else "Dự án không xác định"

    # 1. Nhóm VIP (Admin/Manager): Được xem tất cả Tag
    VIP_ROLES = [UserRole.ADMIN, UserRole.MANAGER, UserRole.BID_MANAGER]
    if user.role in VIP_ROLES:
        # Với Sếp, nguồn cấp quyền cũng là Dự án (hoặc ghi chú thêm là Quản trị)
        return {tag.value: f"{project_name} (Quản trị)" for tag in TaskTag}

    # 2. Lấy TOÀN BỘ Task của dự án (Chỉ cần ID, Parent và Tag để dựng cây)
    all_tasks = db.execute(
        select(BiddingTask.id, BiddingTask.parent_task_id, BiddingTask.tag)
        .where(BiddingTask.bidding_project_id == project_id)
    ).all()
    
    # Map để tra cứu nhanh: {task_id: {'parent': ..., 'tag': ...}}
    task_map = {
        row.id: {"parent_id": row.parent_task_id, "tag": row.tag} 
        for row in all_tasks
    }

    # 3. Lọc danh sách Task mà User sở hữu
    # Điều kiện:
    #   a. Giao đích danh user (assignee_id)
    #   b. Giao đích danh user qua bảng phụ (assigned_user_id)
    #   c. Giao cho PHÒNG BAN của user (assigned_unit_id) <--- Logic bạn yêu cầu
    
    filter_conditions = [
        BiddingTask.assignee_id == user.user_id,
        TaskAssignment.assigned_user_id == user.user_id 
    ]
    
    if user.org_unit_id is not None:
        filter_conditions.append(
            TaskAssignment.assigned_unit_id == user.org_unit_id
        )

    assigned_query = select(BiddingTask.id).outerjoin(TaskAssignment, BiddingTask.assignments).where(
        BiddingTask.bidding_project_id == project_id,
        or_(*filter_conditions)
    )
    
    my_task_ids = db.execute(assigned_query).scalars().all()

    # 4. Truy vết ngược lên cha để tìm Tag (Resolution Logic)
    allowed_tags_map = {}

    for task_id in my_task_ids:
        current_id = task_id
        depth = 0
        
        # Vòng lặp leo cây (tìm tag từ task hiện tại -> cha -> ông...)
        while current_id is not None and depth < 10:
            node = task_map.get(current_id)
            if not node: break 

            # Nếu tìm thấy Tag ở node hiện tại
            if node["tag"] is not None:
                tag_code = node["tag"].value
                
                # --- THAY ĐỔI Ở ĐÂY: Gán tên Project làm nguồn cấp quyền ---
                allowed_tags_map[tag_code] = project_name 
                # -----------------------------------------------------------
                
                break # Đã tìm thấy tag cho nhánh này, dừng leo
            
            # Chưa thấy, leo tiếp lên cha
            current_id = node["parent_id"]
            depth += 1
            
    return allowed_tags_map