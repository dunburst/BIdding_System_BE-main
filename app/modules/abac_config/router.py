from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional

# Import từ các file trên
from app.modules.abac_config.schema import (
    AbacAttributeCreate, AbacAttributeUpdate, AbacAttributeResponse,
    AbacPolicyCreate, AbacPolicyUpdate, AbacPolicyResponse
)
import app.modules.abac_config.crud as crud
from app.infrastructure.database.database import get_db # Giả định file database.py của bạn có hàm này

router = APIRouter(prefix="/abac", tags=["ABAC Configuration"])

# ==========================================
# ENDPOINTS CHO ATTRIBUTES
# ==========================================

@router.post("/attributes", response_model=AbacAttributeResponse, status_code=status.HTTP_201_CREATED)
def create_attribute(attr_in: AbacAttributeCreate, db: Session = Depends(get_db)):
    # Check trùng attr_key
    existing_attr = crud.get_attribute_by_key(db, attr_key=attr_in.attr_key)
    if existing_attr:
        raise HTTPException(status_code=400, detail="Attribute key already exists")
    return crud.create_attribute(db=db, attribute=attr_in)

@router.get("/attributes", response_model=List[AbacAttributeResponse])
def read_attributes(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_attributes(db, skip=skip, limit=limit)

@router.get("/attributes/{attribute_id}", response_model=AbacAttributeResponse)
def read_attribute(attribute_id: int, db: Session = Depends(get_db)):
    db_attr = crud.get_attribute(db, attribute_id=attribute_id)
    if db_attr is None:
        raise HTTPException(status_code=404, detail="Attribute not found")
    return db_attr

@router.put("/attributes/{attribute_id}", response_model=AbacAttributeResponse)
def update_attribute(attribute_id: int, attr_in: AbacAttributeUpdate, db: Session = Depends(get_db)):
    db_attr = crud.update_attribute(db, attribute_id=attribute_id, attribute_in=attr_in)
    if db_attr is None:
        raise HTTPException(status_code=404, detail="Attribute not found")
    return db_attr

@router.delete("/attributes/{attribute_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attribute(attribute_id: int, db: Session = Depends(get_db)):
    db_attr = crud.delete_attribute(db, attribute_id=attribute_id)
    if db_attr is None:
        raise HTTPException(status_code=404, detail="Attribute not found")
    return None

# ==========================================
# ENDPOINTS CHO POLICIES
# ==========================================

@router.post("/policies", response_model=AbacPolicyResponse, status_code=status.HTTP_201_CREATED)
def create_policy(policy_in: AbacPolicyCreate, db: Session = Depends(get_db)):
    return crud.create_policy(db=db, policy=policy_in)

@router.get("/policies", response_model=List[AbacPolicyResponse])
def read_policies(
    skip: int = 0, 
    limit: int = 100, 
    resource: Optional[str] = Query(None, description="Lọc theo resource (VD: bidding_package)"),
    db: Session = Depends(get_db)
):
    """
    Lấy danh sách Policies. Mặc định sắp xếp theo độ ưu tiên (Priority) giảm dần.
    """
    return crud.get_policies(db, skip=skip, limit=limit, resource=resource)

@router.get("/policies/{policy_id}", response_model=AbacPolicyResponse)
def read_policy(policy_id: int, db: Session = Depends(get_db)):
    db_policy = crud.get_policy(db, policy_id=policy_id)
    if db_policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    return db_policy

@router.put("/policies/{policy_id}", response_model=AbacPolicyResponse)
def update_policy(policy_id: int, policy_in: AbacPolicyUpdate, db: Session = Depends(get_db)):
    db_policy = crud.update_policy(db, policy_id=policy_id, policy_in=policy_in)
    if db_policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    return db_policy

@router.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_policy(policy_id: int, db: Session = Depends(get_db)):
    db_policy = crud.delete_policy(db, policy_id=policy_id)
    if db_policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    return None