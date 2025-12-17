from sqlalchemy.orm import Session
import models
import schemas.organization as schemas

# 1. Lấy danh sách (Phân trang phẳng)
def get_units(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.OrganizationalUnit).order_by(models.OrganizationalUnit.unit_id).offset(skip).limit(limit).all()

# 2. Lấy chi tiết 1 đơn vị
def get_unit(db: Session, unit_id: int):
    return db.query(models.OrganizationalUnit).filter(models.OrganizationalUnit.unit_id == unit_id).first()

# 3. Tạo mới đơn vị
def create_unit(db: Session, unit: schemas.OrganizationalUnitCreate):
    db_unit = models.OrganizationalUnit(**unit.model_dump())
    db.add(db_unit)
    db.commit()
    db.refresh(db_unit)
    return db_unit

# 4. Cập nhật đơn vị
def update_unit(db: Session, unit_id: int, unit_update: schemas.OrganizationalUnitUpdate):
    db_unit = get_unit(db, unit_id)
    if not db_unit:
        return None
    
    update_data = unit_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_unit, key, value)

    db.add(db_unit)
    db.commit()
    db.refresh(db_unit)
    return db_unit

# 5. Xóa đơn vị
def delete_unit(db: Session, unit_id: int):
    db_unit = get_unit(db, unit_id)
    if db_unit:
        db.delete(db_unit)
        db.commit()
        return True
    return False

# 6. [SPECIAL] Lấy toàn bộ cây tổ chức (Bắt đầu từ các nút gốc - không có cha)
def get_organization_tree(db: Session):
    # Lấy tất cả unit có parent_unit_id là NULL (Cấp cao nhất)
    # SQLAlchemy relationship 'children' sẽ tự động load các cấp con khi Pydantic serialize
    root_units = db.query(models.OrganizationalUnit).filter(models.OrganizationalUnit.parent_unit_id == None).all()
    return root_units