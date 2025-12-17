from sqlalchemy.orm import Session
from typing import Union, Any, List, Optional
from models import AbacPolicy, User, PolicyEffect
from utils.constants import AbacAction
import enum

# 1. Hàm hỗ trợ: Lấy giá trị từ đối tượng an toàn
def get_attribute_value(target_obj: Any, attr_path: str) -> Any:
    """
    Lấy giá trị thuộc tính động. Trả về None nếu không lấy được.
    """
    if target_obj is None or not attr_path:
        return None
        
    parts = attr_path.split(".")
    if len(parts) < 2:
        return None
    
    attr_name = parts[1] # Lấy phần sau dấu chấm (VD: "role" trong "user.role")
    
    # getattr(obj, name, default): Trả về None nếu không tìm thấy thuộc tính
    return getattr(target_obj, attr_name, None)

# 2. Hàm hỗ trợ: So sánh logic
def evaluate_rule(user: User, resource: Any, rule: dict) -> bool:
    """
    Đánh giá 1 dòng rule JSON. 
    Đã fix lỗi Type Hinting cho phép so sánh số an toàn.
    """
    field = rule.get("field")
    if not isinstance(field, str): 
        return False
        
    operator = rule.get("operator")
    target_value = rule.get("value")

    # A. Lấy giá trị thực tế của Vế Trái (Left Value)
    left_value: Any = None
    if field.startswith("user."):
        left_value = get_attribute_value(user, field)
    elif field.startswith("resource."):
        left_value = get_attribute_value(resource, field)
    else:
        return False

    # B. Xử lý giá trị của Vế Phải (Target Value)
    real_target_value: Any = target_value
    if isinstance(target_value, str):
        if target_value.startswith("resource."):
            real_target_value = get_attribute_value(resource, target_value)
        elif target_value.startswith("user."):
            real_target_value = get_attribute_value(user, target_value)

    # --- LỘT VỎ ENUM THÔNG MINH ---
    if isinstance(left_value, enum.Enum):
        if operator in ["gt", "gte", "lt", "lte"]:
            left_value = left_value.value
        elif isinstance(real_target_value, str) and not real_target_value.isdigit():
            left_value = left_value.name 
        elif operator == "in" and isinstance(real_target_value, list) and len(real_target_value) > 0 and isinstance(real_target_value[0], str):
            left_value = left_value.name
        else:
            left_value = left_value.value

    if isinstance(real_target_value, enum.Enum):
        if isinstance(left_value, str):
            real_target_value = real_target_value.name
        else:
            real_target_value = real_target_value.value
    # -------------------------------

    # C. So sánh (Core Logic)
    
    # 1. So sánh Bằng / Khác
    if operator == "eq":
        return str(left_value) == str(real_target_value)
    
    elif operator == "neq":
        return str(left_value) != str(real_target_value)
    
    # 2. So sánh Số (SỬA LỖI TYPE HINT Ở ĐÂY)
    elif operator in ["gt", "gte", "lt", "lte"]:
        # Bước 1: Loại bỏ List/Dict ngay lập tức để Type Checker không báo lỗi
        if isinstance(left_value, (list, dict)) or isinstance(real_target_value, (list, dict)):
            return False 
            
        # Bước 2: Kiểm tra None
        if left_value is None or real_target_value is None:
            return False 
            
        try:
            # Lúc này Type Checker đã yên tâm đây là scalar type (int, float, str...)
            val_left = float(left_value)
            val_right = float(real_target_value)
            
            if operator == "gt": return val_left > val_right
            if operator == "gte": return val_left >= val_right
            if operator == "lt": return val_left < val_right
            if operator == "lte": return val_left <= val_right
        except (ValueError, TypeError):
            return False 

    # 3. So sánh Danh sách (IN)
    elif operator == "in":
        if isinstance(real_target_value, list):
            return str(left_value) in [str(x) for x in real_target_value]
        return False

    return False

# 3. Hàm chính: Kiểm tra quyền
def check_permission(
    db: Session, 
    user: User, 
    resource: Union[str, Any], 
    required_action: str
) -> bool:
    """
    Hàm quyết định quyền truy cập.
    """
    if not user:
        return False

    # 1. Xác định tên resource (String) để query DB tìm Policies
    resource_name = ""
    if isinstance(resource, str):
        resource_name = resource
    elif hasattr(resource, "__tablename__"):
        resource_name = resource.__tablename__
    else:
        # Fallback: Nếu không xác định được tên resource thì coi như là bidding_package
        # Bạn có thể sửa chỗ này tùy logic
        resource_name = "bidding_package"

    # 2. Lấy tất cả Policy ACTIVE liên quan đến Resource này
    policies = db.query(AbacPolicy).filter(
        AbacPolicy.target_resource == resource_name,
        AbacPolicy.is_active == True
    ).order_by(AbacPolicy.priority.desc()).all()

    if not policies:
        # Nếu không có policy nào -> Mặc định CẤM (Zero Trust)
        return False 

    allowed = False

    for policy in policies:
        # 3. Kiểm tra Action
        # policy.action là list (VD: ["VIEW", "UPDATE"])
        if required_action not in policy.action:
            continue 

        # 4. Đánh giá Condition JSON
        condition_json = policy.condition_json or {} # Handle None
        logic = condition_json.get("condition", "AND")
        rules = condition_json.get("rules", [])
        
        if not rules:
            # Nếu policy không có rules điều kiện -> Mặc định là áp dụng luôn
            is_policy_match = True
        else:
            is_policy_match = True if logic == "AND" else False
            
            if logic == "AND":
                # AND: Chỉ cần 1 rule sai là toàn bộ sai
                for rule in rules:
                    if not evaluate_rule(user, resource, rule):
                        is_policy_match = False
                        break
            
            elif logic == "OR":
                # OR: Chỉ cần 1 rule đúng là toàn bộ đúng
                for rule in rules:
                    if evaluate_rule(user, resource, rule):
                        is_policy_match = True
                        break

        # 5. Quyết định kết quả
        if is_policy_match:
            if policy.effect == PolicyEffect.DENY:
                return False # Gặp DENY là chặn luôn
            elif policy.effect == PolicyEffect.ALLOW:
                allowed = True
                # Với priority giảm dần, gặp ALLOW đầu tiên có thể return luôn
                return True

    return allowed