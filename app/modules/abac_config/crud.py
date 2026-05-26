from sqlalchemy.orm import Session
from app.modules.abac_config.model import AbacAttribute, AbacPolicy
from app.modules.abac_config.schema import AbacAttributeCreate, AbacAttributeUpdate, AbacPolicyCreate, AbacPolicyUpdate
from typing import List, Optional
from app.core.permission.abac import invalidate_policy_cache
# ==========================================
# CRUD CHO ABAC ATTRIBUTE
# ==========================================

def get_attribute(db: Session, attribute_id: int):
    return db.query(AbacAttribute).filter(AbacAttribute.id == attribute_id).first()

def get_attribute_by_key(db: Session, attr_key: str):
    return db.query(AbacAttribute).filter(AbacAttribute.attr_key == attr_key).first()

def get_attributes(db: Session, skip: int = 0, limit: int = 100):
    return db.query(AbacAttribute).order_by(AbacAttribute.id).offset(skip).limit(limit).all()

def create_attribute(db: Session, attribute: AbacAttributeCreate):
    db_obj = AbacAttribute(
        attr_key=attribute.attr_key,
        attr_type=attribute.attr_type,
        source_table=attribute.source_table,
        description=attribute.description
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def update_attribute(db: Session, attribute_id: int, attribute_in: AbacAttributeUpdate):
    db_obj = get_attribute(db, attribute_id)
    if not db_obj:
        return None
    
    update_data = attribute_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_obj, field, value)
        
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def delete_attribute(db: Session, attribute_id: int):
    db_obj = get_attribute(db, attribute_id)
    if db_obj:
        db.delete(db_obj)
        db.commit()
    return db_obj

# ==========================================
# CRUD CHO ABAC POLICY
# ==========================================

def get_policy(db: Session, policy_id: int):
    return db.query(AbacPolicy).filter(AbacPolicy.id == policy_id).first()

def get_policies(db: Session, skip: int = 0, limit: int = 100, resource: Optional[str] = None):
    query = db.query(AbacPolicy)
    if resource:
        query = query.filter(AbacPolicy.target_resource == resource)
    return query.order_by(AbacPolicy.priority.desc()).offset(skip).limit(limit).all()

def create_policy(db: Session, policy: AbacPolicyCreate):
    db_obj = AbacPolicy(
        name=policy.name,
        description=policy.description,
        target_resource=policy.target_resource,
        action=policy.action,
        effect=policy.effect,
        priority=policy.priority,
        condition_json=policy.condition_json,
        is_active=policy.is_active
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    # 👉 THÊM DÒNG NÀY: Xóa cache của resource tương ứng để lần sau load lại cái mới
    invalidate_policy_cache(policy.target_resource)
    return db_obj

def update_policy(db: Session, policy_id: int, policy_in: AbacPolicyUpdate):
    db_obj = get_policy(db, policy_id)
    if not db_obj:
        return None
    
    update_data = policy_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_obj, field, value)
    
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    # 👉 THÊM DÒNG NÀY
    invalidate_policy_cache(db_obj.target_resource)
    return db_obj

def delete_policy(db: Session, policy_id: int):
    db_obj = get_policy(db, policy_id)
    if db_obj:
        target_res = db_obj.target_resource # Lưu tên resource trước khi xóa
        db.delete(db_obj)
        db.commit()
        # 👉 THÊM DÒNG NÀY
        invalidate_policy_cache(target_res)
    return db_obj