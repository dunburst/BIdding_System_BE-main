from typing import Any, Dict, Optional, Union
from sqlalchemy.orm import Session
import enum
from app.modules.abac_config.model import AbacPolicy, AbacAttribute, PolicyEffect
from app.modules.users.model import User
from app.core.permission.constants import AbacAction
from typing import List
from sqlalchemy.orm import selectinload

# Biến global lưu trữ Policy trong RAM
# Cấu trúc: { "bidding_packages": [PolicyObj1, PolicyObj2], "users": [...] }
# Cách chuyên nghiệp hơn (Optional):
# policies_pydantic = [AbacPolicyResponse.model_validate(p) for p in policies]
# _POLICY_STORE[resource_name] = policies_pydantic
_POLICY_STORE: Dict[str, List[AbacPolicy]] = {}
def get_policies_from_cache(db: Session, resource_name: str) -> List[AbacPolicy]:
    global _POLICY_STORE
    
    # 1. Nếu đã có trong RAM, trả về ngay
    if resource_name in _POLICY_STORE:
        return _POLICY_STORE[resource_name]
    
    # 2. Nếu chưa có, query DB
    print(f"🔄 [CACHE MISS] Loading policies for {resource_name} from DB...")
    
    # --- BƯỚC 1: Xóa .options(selectinload...) ---
    policies = db.query(AbacPolicy).filter(
        AbacPolicy.target_resource == resource_name,
        AbacPolicy.is_active == True
    ).order_by(AbacPolicy.priority.desc()).all()
    
    # --- BƯỚC 2: Cắt object khỏi Session (Quan trọng) ---
    for policy in policies:
        # Expunge giúp biến object thành object độc lập, 
        # giữ nguyên data hiện tại trong RAM và không bao giờ gọi lại DB nữa.
        db.expunge(policy) 
        
    # 3. Lưu vào RAM
    _POLICY_STORE[resource_name] = policies
    
    return policies
def invalidate_policy_cache(resource_name: Optional[str] = None):
    """
    Hàm này dùng để XÓA cache khi Admin cập nhật/thêm/sửa policy.
    Bắt buộc hệ thống phải load lại dữ liệu mới nhất.
    """
    global _POLICY_STORE
    if resource_name and resource_name in _POLICY_STORE:
        del _POLICY_STORE[resource_name]
        print(f"🧹 [CACHE CLEARED] Resource: {resource_name}")
    else:
        _POLICY_STORE.clear()
        print("🧹 [CACHE CLEARED] All resources")
# Biến toàn cục lưu Cache Mapping (Key -> Path)
# VD: { "user.org_unit_type": "org_unit.unit_type" }
ATTRIBUTE_MAPPING_CACHE: Dict[str, str] = {}
def get_allowed_actions(db: Session, user: User, resource: Any) -> List[str]:
    """
    Hàm này chạy thử tất cả các hành động quan trọng 
    để xem user được phép làm những gì.
    """
    # Danh sách các nút bấm có trên màn hình Frontend cần check
    possible_actions = [
        AbacAction.UPDATE,
        AbacAction.DELETE,
        AbacAction.APPROVE_BID,
        AbacAction.REJECT_BID,
        AbacAction.CREATE_PROJECT,
        AbacAction.EXPORT_EXCEL
    ]
    
    allowed = []
    
    # Chạy vòng lặp check từng quyền (Logic check_permission của bạn đủ nhanh để làm việc này)
    for action in possible_actions:
        if check_permission(db=db, user=user, resource=resource, action=action):
            allowed.append(action)
            
    return allowed

def load_attribute_mapping(db: Session):
    """
    Load toàn bộ bảng attributes vào RAM để tra cứu nhanh.
    """
    global ATTRIBUTE_MAPPING_CACHE
    attributes = db.query(AbacAttribute).all()
    ATTRIBUTE_MAPPING_CACHE = {
        attr.attr_key: attr.mapping_path 
        for attr in attributes 
        if attr.mapping_path
    }
    print(f"✅ [SYSTEM] Cache Loaded: {ATTRIBUTE_MAPPING_CACHE}")

def get_value_deep(target_obj: Any, path_str: str) -> Any:
    """
    Hàm Reflection: Đi xuyên qua object bằng chuỗi path (dot notation).
    VD: user -> org_unit -> unit_type
    """
    if not target_obj or not path_str:
        return None
    
    parts = path_str.split(".")
    current = target_obj
    
    for part in parts:
        if current is None:
            return None
        # Nếu là Dict
        if isinstance(current, dict):
            current = current.get(part)
        # Nếu là Object Class
        else:
            current = getattr(current, part, None)
            
    # Tự động lấy value nếu là Enum (để so sánh với String trong JSON)
    if isinstance(current, enum.Enum):
        return current.value
        
    return current

def resolve_attribute_value(user: User, resource: Any, attr_key: str) -> Any:
    """
    Hàm Resolve thông minh:
    1. Nhận attr_key (VD: user.org_unit_type)
    2. Tra Cache lấy mapping (VD: org_unit.unit_type)
    3. Gọi get_value_deep
    """
    # Lấy đường dẫn mapping thực tế, nếu không có thì dùng chính key đó
    mapping_path = ATTRIBUTE_MAPPING_CACHE.get(attr_key, attr_key)
    
    # Xác định đối tượng gốc (User hay Resource)
    if attr_key.startswith("user."):
        # Xóa prefix "user." nếu mapping_path vẫn còn giữ nó (để get_value_deep chạy từ root obj)
        clean_path = mapping_path.replace("user.", "") if mapping_path.startswith("user.") else mapping_path
        return get_value_deep(user, clean_path)
        
    elif attr_key.startswith("resource."):
        clean_path = mapping_path.replace("resource.", "") if mapping_path.startswith("resource.") else mapping_path
        return get_value_deep(resource, clean_path)
        
    return None

def compare_values(left: Any, operator: str, right: Any) -> bool:
    """Logic so sánh cơ bản"""
    # 1. So sánh bằng
    if operator == "eq": return str(left) == str(right)
    if operator == "neq": return str(left) != str(right)
    
    # 2. So sánh danh sách
    if operator == "in":
        if isinstance(right, list):
            return str(left) in [str(x) for x in right]
        return False
        
    # 3. So sánh số học
    if operator in ["gt", "gte", "lt", "lte"]:
        try:
            if left is None or right is None: return False
            l, r = float(left), float(right)
            if operator == "gt": return l > r
            if operator == "gte": return l >= r
            if operator == "lt": return l < r
            if operator == "lte": return l <= r
        except:
            return False
    return False

def evaluate_logic_block(user: User, resource: Any, logic_block: Dict) -> bool:
    """Đệ quy xử lý AND/OR"""
    condition = logic_block.get("condition", "AND")
    rules = logic_block.get("rules", [])
    
    if not rules: return True
    
    results = []
    for rule in rules:
        # Nếu rule con là một nhóm logic (có condition/rules) -> Đệ quy
        if "condition" in rule or "rules" in rule:
            results.append(evaluate_logic_block(user, resource, rule))
        else:
            # Nếu là rule đơn lẻ
            attr_key = rule.get("field")
            target_val = rule.get("value")
            operator = rule.get("operator")
            
            # Lấy giá trị thực tế (User/Resource)
            left_val = resolve_attribute_value(user, resource, attr_key)
            
            # Nếu vế phải cũng là biến động (VD: so sánh user.id == resource.owner_id)
            final_target = target_val
            if isinstance(target_val, str) and (target_val.startswith("user.") or target_val.startswith("resource.")):
                final_target = resolve_attribute_value(user, resource, target_val)
                
            results.append(compare_values(left_val, operator, final_target))
            
    if condition == "AND": return all(results)
    if condition == "OR": return any(results)
    return False

def check_permission(db: Session, user: User, resource: Union[str, Any], action: str) -> bool:
    """Hàm Main Check Quyền"""
    if not user: return False
    
    # Xác định tên Resource
    res_name = resource if isinstance(resource, str) else resource.__tablename__
    res_obj = resource if not isinstance(resource, str) else {}
    
    # Load Cache nếu chưa có
    if not ATTRIBUTE_MAPPING_CACHE:
        load_attribute_mapping(db)
        
    # # Query Policy
    # policies = db.query(AbacPolicy).filter(
    #     AbacPolicy.target_resource == res_name,
    #     AbacPolicy.is_active == True
    # ).order_by(AbacPolicy.priority.desc()).all()
    # --- THAY ĐỔI Ở ĐÂY ---
    # Thay vì: policies = db.query(AbacPolicy)...
    # Dùng hàm cache:
    policies = get_policies_from_cache(db, res_name) 
    # ----------------------
    
    if not policies: return False # Zero Trust
    
    for policy in policies:
        if action not in policy.action: continue
        
        # Check logic JSON
        matched = True
        if policy.condition_json:
            matched = evaluate_logic_block(user, res_obj, policy.condition_json)
            
        if matched:
            print(f"👉 Matched Policy: {policy.name} -> {policy.effect.value}")
            return policy.effect == PolicyEffect.ALLOW
            
    return False