"""
Seeder khởi tạo dữ liệu ban đầu:
  1. OrganizationalUnits  (cây tổ chức mẫu)
  2. Users                (1 user mỗi role)
  3. AbacAttributes       (ánh xạ field → path)
  4. AbacPolicies         (phân quyền theo role cho từng resource)

Chạy: python seed.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

# Phải import all_models để SQLAlchemy đăng ký đầy đủ các bảng
import app.infrastructure.database.all_models  # noqa: F401

from app.infrastructure.database.database import SessionLocal, engine, Base
from app.modules.users.model import User
from app.modules.organization.model import OrganizationalUnit
from app.modules.abac_config.model import AbacAttribute, AbacPolicy
from app.core.utils.enum import (
    UserRole, SecurityLevel, UnitType,
    AttributeType, PolicyEffect,
)
from app.core.security import get_password_hash

Base.metadata.create_all(bind=engine)

# ==============================================================================
# HẰNG SỐ
# ==============================================================================
DEFAULT_PASSWORD = "123456"

# Tất cả actions có trong hệ thống
ALL_ACTIONS = [
    "VIEW", "LIST", "CREATE", "UPDATE", "DELETE",
    "APPROVE_BID", "REJECT_BID", "SUBMIT_BID", "EVALUATE_BID", "OPEN_BID",
    "SUBMIT_REVIEW", "LIST_PENDING",
    "CREATE_PROJECT", "ASSIGN_TASK", "EXPORT_EXCEL",
]

# ==============================================================================
# DỮ LIỆU MẪU
# ==============================================================================

ORG_UNITS = [
    {
        "unit_code": "PC1_Group",
        "unit_name": "Tập đoàn PC1",
        "unit_type": UnitType.GROUP,
        "description": "Tập đoàn PC1 - Đơn vị gốc",
        "parent_unit_code": None,
    },
    {
        "unit_code": "QTVH",
        "unit_name": "Khối Quản trị vận hàng",
        "unit_type": UnitType.BLOCK,
        "description": "Khối quản trị trực thuộc Tập đoàn",
        "parent_unit_code": "PC1_Group ",
    },
    {
        "unit_code": "BAN_CDS",
        "unit_name": "Ban Chuyển đổi số",
        "unit_type": UnitType.BOARD,
        "description": "Ban chuyển đổi số",
        "parent_unit_code": "QTVH",
    },
    {
        "unit_code": "PHONG_UDS",
        "unit_name": "Phòng Ứng dụng số",
        "unit_type": UnitType.DEPARTMENT,
        "description": "Phòng Kỹ thuật số",
        "parent_unit_code": "BAN_CDS",
    },
    {
        "unit_code": "PC1_TL",
        "unit_name": "PC1 Thăng Long",
        "unit_type": UnitType.SUBSIDIARY,
        "description": "Công ty đơn vị thành viên",
        "parent_unit_code": "PC1_Group",
    },
]

# user_data: (email, full_name, role, job_title, security_clearance, org_unit_code)
USERS = [
    {
        "email": "admin@pc1group.vn",
        "full_name": "Quản trị viên Hệ thống",
        "role": UserRole.ADMIN,
        "job_title": "System Administrator",
        "security_clearance": SecurityLevel.SECRET,
        "org_unit_code": "PC1_Group",
    },
    {
        "email": "manager@pc1group.vn",
        "full_name": "Nguyễn Văn Lãnh Đạo",
        "role": UserRole.MANAGER,
        "job_title": "Lãnh đạo Tập đoàn",
        "security_clearance": SecurityLevel.SECRET,
        "org_unit_code": "PC1_Group",
    },
    {
        "email": "bid_manager@pc1group.vn",
        "full_name": "Trần Thị Trưởng Phòng",
        "role": UserRole.BID_MANAGER,
        "job_title": "Trưởng Ban Đấu thầu",
        "security_clearance": SecurityLevel.CONFIDENTIAL,
        "org_unit_code": "BAN_CDS",
    },
    {
        "email": "specialist@pc1group.vn",
        "full_name": "Lê Văn Chuyên Viên",
        "role": UserRole.SPECIALIST,
        "job_title": "Chuyên viên Đấu thầu",
        "security_clearance": SecurityLevel.INTERNAL,
        "org_unit_code": "PHONG_UDS",
    },
    {
        "email": "engineer@pc1group.vn",
        "full_name": "Phạm Thị Kỹ Sư",
        "role": UserRole.ENGINEER,
        "job_title": "Kỹ sư Xây dựng",
        "security_clearance": SecurityLevel.PUBLIC,
        "org_unit_code": "PHONG_UDS",
    },
    {
        "email": "jkan@pc1group.vn",
        "full_name": "Hoàng Văn Thành Viên",
        "role": UserRole.JKAN,
        "job_title": "Thành viên Dự án",
        "security_clearance": SecurityLevel.PUBLIC,
        "org_unit_code": "PC1_TL",
    },
]

# ==============================================================================
# ABAC ATTRIBUTES
# attr_key: tên field dùng trong policy condition_json
# mapping_path: đường dẫn thực tế tới attribute trên object
# ==============================================================================
ATTRIBUTES = [
    {
        "attr_key": "user.role",
        "attr_type": AttributeType.STRING,
        "source_table": "users",
        "mapping_path": "role",
        "description": "Role của người dùng (ADMIN, MANAGER, BID_MANAGER, SPECIALIST, ENGINEER, JKAN)",
    },
    {
        "attr_key": "user.security_clearance",
        "attr_type": AttributeType.INTEGER,
        "source_table": "users",
        "mapping_path": "security_clearance",
        "description": "Cấp độ bảo mật của người dùng (1-PUBLIC → 4-SECRET)",
    },
    {
        "attr_key": "user.org_unit_type",
        "attr_type": AttributeType.STRING,
        "source_table": "organizational_units",
        "mapping_path": "org_unit.unit_type",
        "description": "Loại đơn vị mà user thuộc về (GROUP, BLOCK, BOARD, DEPARTMENT, SUBSIDIARY)",
    },
    {
        "attr_key": "resource.trang_thai",
        "attr_type": AttributeType.STRING,
        "source_table": "bidding_packages",
        "mapping_path": "trang_thai",
        "description": "Trạng thái gói thầu (NEW, INTERESTED, BIDDING, SUBMITTED, CLOSED, PENDING_REVIEW)",
    },
    {
        "attr_key": "resource.nguoi_duyet_id",
        "attr_type": AttributeType.INTEGER,
        "source_table": "bidding_packages",
        "mapping_path": "nguoi_duyet_id",
        "description": "ID người được phân công duyệt gói thầu",
    },
]

# ==============================================================================
# ABAC POLICIES
# Định nghĩa quyền cho từng role trên từng resource
# ==============================================================================
def _role_condition(roles: list[str]) -> dict:
    """Tạo condition kiểm tra user.role nằm trong danh sách roles"""
    return {
        "condition": "AND",
        "rules": [
            {"field": "user.role", "operator": "in", "value": roles}
        ],
    }

POLICIES = [
    # ==================== BIDDING_PACKAGES ====================
    # NOTE: CREATE_PROJECT cũng nằm ở đây vì router kiểm tra quyền trên BiddingPackage object
    # (resource.__tablename__ = "bidding_packages"), không phải "bidding_project"
    {
        "name": "[ADMIN] Toàn quyền gói thầu",
        "description": "Admin có tất cả quyền trên bảng bidding_packages",
        "target_resource": "bidding_packages",
        "action": ALL_ACTIONS,
        "effect": PolicyEffect.ALLOW,
        "priority": 100,
        "condition_json": _role_condition(["ADMIN"]),
    },
    {
        "name": "[MANAGER] Xem, phê duyệt, export gói thầu",
        "description": "Lãnh đạo xem danh sách, phê duyệt/từ chối, xem danh sách trình duyệt và xuất báo cáo",
        "target_resource": "bidding_packages",
        "action": ["VIEW", "LIST", "APPROVE_BID", "REJECT_BID", "LIST_PENDING", "EXPORT_EXCEL", "CREATE_PROJECT"],
        "effect": PolicyEffect.ALLOW,
        "priority": 90,
        "condition_json": _role_condition(["MANAGER"]),
    },
    {
        "name": "[BID_MANAGER] Tạo/sửa/trình lãnh đạo gói thầu",
        "description": "Trưởng phòng tạo mới, cập nhật, trình lãnh đạo, tạo dự án từ gói thầu đã duyệt",
        "target_resource": "bidding_packages",
        "action": ["VIEW", "LIST", "CREATE", "UPDATE", "SUBMIT_REVIEW", "LIST_PENDING", "EXPORT_EXCEL", "CREATE_PROJECT"],
        "effect": PolicyEffect.ALLOW,
        "priority": 80,
        "condition_json": _role_condition(["BID_MANAGER"]),
    },
    {
        "name": "[SPECIALIST] Soạn thảo và nộp thầu",
        "description": "Chuyên viên cập nhật hồ sơ, nộp thầu và xuất báo cáo",
        "target_resource": "bidding_packages",
        "action": ["VIEW", "LIST", "UPDATE", "SUBMIT_BID", "EXPORT_EXCEL"],
        "effect": PolicyEffect.ALLOW,
        "priority": 70,
        "condition_json": _role_condition(["SPECIALIST"]),
    },
    {
        "name": "[ENGINEER] Xem gói thầu",
        "description": "Kỹ sư chỉ được xem danh sách và chi tiết gói thầu",
        "target_resource": "bidding_packages",
        "action": ["VIEW", "LIST"],
        "effect": PolicyEffect.ALLOW,
        "priority": 60,
        "condition_json": _role_condition(["ENGINEER"]),
    },
    {
        "name": "[JKAN] Xem gói thầu hạn chế",
        "description": "Thành viên dự án chỉ được xem danh sách và chi tiết gói thầu",
        "target_resource": "bidding_packages",
        "action": ["VIEW", "LIST"],
        "effect": PolicyEffect.ALLOW,
        "priority": 50,
        "condition_json": _role_condition(["JKAN"]),
    },

    # ==================== BIDDING_PROJECTS ====================
    {
        "name": "[ADMIN] Toàn quyền dự án",
        "description": "Admin có tất cả quyền trên dự án đấu thầu",
        "target_resource": "bidding_project",
        "action": ALL_ACTIONS,
        "effect": PolicyEffect.ALLOW,
        "priority": 100,
        "condition_json": _role_condition(["ADMIN"]),
    },
    {
        "name": "[MANAGER] Xem và export dự án",
        "description": "Lãnh đạo xem danh sách, chi tiết và xuất báo cáo dự án",
        "target_resource": "bidding_project",
        "action": ["VIEW", "LIST", "EXPORT_EXCEL"],
        "effect": PolicyEffect.ALLOW,
        "priority": 90,
        "condition_json": _role_condition(["MANAGER"]),
    },
    {
        "name": "[BID_MANAGER] Quản lý dự án",
        "description": "Trưởng phòng tạo mới và cập nhật dự án",
        "target_resource": "bidding_project",
        "action": ["VIEW", "LIST", "CREATE_PROJECT", "UPDATE", "EXPORT_EXCEL"],
        "effect": PolicyEffect.ALLOW,
        "priority": 80,
        "condition_json": _role_condition(["BID_MANAGER"]),
    },
    {
        "name": "[SPECIALIST/ENGINEER/JKAN] Xem dự án",
        "description": "Các role còn lại chỉ được xem danh sách và chi tiết dự án",
        "target_resource": "bidding_project",
        "action": ["VIEW", "LIST"],
        "effect": PolicyEffect.ALLOW,
        "priority": 60,
        "condition_json": _role_condition(["SPECIALIST", "ENGINEER", "JKAN"]),
    },

    # ==================== USERS ====================
    {
        "name": "[ADMIN] Toàn quyền người dùng",
        "description": "Admin quản lý toàn bộ tài khoản người dùng",
        "target_resource": "users",
        "action": ["VIEW", "LIST", "CREATE", "UPDATE", "DELETE"],
        "effect": PolicyEffect.ALLOW,
        "priority": 100,
        "condition_json": _role_condition(["ADMIN"]),
    },
    {
        "name": "[MANAGER/BID_MANAGER] Xem danh sách người dùng",
        "description": "Lãnh đạo và Trưởng phòng xem được danh sách nhân sự",
        "target_resource": "users",
        "action": ["VIEW", "LIST"],
        "effect": PolicyEffect.ALLOW,
        "priority": 80,
        "condition_json": _role_condition(["MANAGER", "BID_MANAGER"]),
    },
    {
        "name": "[SPECIALIST/ENGINEER/JKAN] Xem thông tin người dùng",
        "description": "Các role thấp hơn chỉ được xem thông tin (không xem danh sách)",
        "target_resource": "users",
        "action": ["VIEW"],
        "effect": PolicyEffect.ALLOW,
        "priority": 60,
        "condition_json": _role_condition(["SPECIALIST", "ENGINEER", "JKAN"]),
    },

    # ==================== ORGANIZATIONAL_UNITS ====================
    {
        "name": "[ADMIN] Toàn quyền tổ chức",
        "description": "Admin quản lý toàn bộ cơ cấu tổ chức",
        "target_resource": "organizational_units",
        "action": ["VIEW", "LIST", "CREATE", "UPDATE", "DELETE"],
        "effect": PolicyEffect.ALLOW,
        "priority": 100,
        "condition_json": _role_condition(["ADMIN"]),
    },
    {
        "name": "[MANAGER/BID_MANAGER] Xem tổ chức",
        "description": "Lãnh đạo và Trưởng phòng xem cơ cấu tổ chức",
        "target_resource": "organizational_units",
        "action": ["VIEW", "LIST"],
        "effect": PolicyEffect.ALLOW,
        "priority": 80,
        "condition_json": _role_condition(["MANAGER", "BID_MANAGER"]),
    },
    {
        "name": "[SPECIALIST/ENGINEER/JKAN] Xem tổ chức",
        "description": "Các nhân viên thường xem được cơ cấu tổ chức",
        "target_resource": "organizational_units",
        "action": ["VIEW", "LIST"],
        "effect": PolicyEffect.ALLOW,
        "priority": 60,
        "condition_json": _role_condition(["SPECIALIST", "ENGINEER", "JKAN"]),
    },

    # ==================== BIDDING_TASKS ====================
    {
        "name": "[ADMIN] Toàn quyền task",
        "description": "Admin toàn quyền quản lý công việc",
        "target_resource": "bidding_task",
        "action": ALL_ACTIONS,
        "effect": PolicyEffect.ALLOW,
        "priority": 100,
        "condition_json": _role_condition(["ADMIN"]),
    },
    {
        "name": "[MANAGER] Xem và giao việc",
        "description": "Lãnh đạo xem tất cả công việc và có thể giao việc",
        "target_resource": "bidding_task",
        "action": ["VIEW", "LIST", "ASSIGN_TASK"],
        "effect": PolicyEffect.ALLOW,
        "priority": 90,
        "condition_json": _role_condition(["MANAGER"]),
    },
    {
        "name": "[BID_MANAGER] Quản lý và giao task",
        "description": "Trưởng phòng tạo, cập nhật, giao việc và xem tất cả task",
        "target_resource": "bidding_task",
        "action": ["VIEW", "LIST", "CREATE", "UPDATE", "ASSIGN_TASK"],
        "effect": PolicyEffect.ALLOW,
        "priority": 80,
        "condition_json": _role_condition(["BID_MANAGER"]),
    },
    {
        "name": "[SPECIALIST/ENGINEER] Xem và cập nhật task",
        "description": "Chuyên viên và Kỹ sư xem danh sách và cập nhật task được giao",
        "target_resource": "bidding_task",
        "action": ["VIEW", "LIST", "UPDATE"],
        "effect": PolicyEffect.ALLOW,
        "priority": 60,
        "condition_json": _role_condition(["SPECIALIST", "ENGINEER"]),
    },
    {
        "name": "[JKAN] Xem task",
        "description": "Thành viên dự án chỉ xem task",
        "target_resource": "bidding_task",
        "action": ["VIEW", "LIST"],
        "effect": PolicyEffect.ALLOW,
        "priority": 50,
        "condition_json": _role_condition(["JKAN"]),
    },

    # ==================== CRAWLER CONFIG ====================
    {
        "name": "[ADMIN/BID_MANAGER] Quản lý cấu hình crawler",
        "description": "Chỉ Admin và Trưởng phòng được cấu hình rule crawler",
        "target_resource": "crawl_rules",
        "action": ["VIEW", "LIST", "CREATE", "UPDATE", "DELETE"],
        "effect": PolicyEffect.ALLOW,
        "priority": 90,
        "condition_json": _role_condition(["ADMIN", "BID_MANAGER"]),
    },
    {
        "name": "[MANAGER/SPECIALIST] Xem cấu hình crawler",
        "description": "Lãnh đạo và Chuyên viên xem được lịch crawler",
        "target_resource": "crawl_rules",
        "action": ["VIEW", "LIST"],
        "effect": PolicyEffect.ALLOW,
        "priority": 70,
        "condition_json": _role_condition(["MANAGER", "SPECIALIST"]),
    },
]


# ==============================================================================
# SEED FUNCTIONS
# ==============================================================================
def seed_org_units(db) -> dict[str, int]:
    """Tạo cây tổ chức, trả về dict {unit_code: unit_id}"""
    print("\n📁 Seeding Organizational Units...")
    code_to_id: dict[str, int] = {}

    for data in ORG_UNITS:
        existing = db.query(OrganizationalUnit).filter_by(unit_code=data["unit_code"]).first()
        if existing:
            print(f"   ⚠️  Đã tồn tại: {data['unit_code']}")
            code_to_id[data["unit_code"]] = existing.unit_id
            continue

        parent_id = code_to_id.get(data["parent_unit_code"]) if data["parent_unit_code"] else None
        unit = OrganizationalUnit(
            unit_code=data["unit_code"],
            unit_name=data["unit_name"],
            unit_type=data["unit_type"],
            description=data.get("description"),
            parent_unit_id=parent_id,
        )
        db.add(unit)
        db.flush()
        code_to_id[data["unit_code"]] = unit.unit_id
        print(f"   ✅ Tạo: [{data['unit_type'].value}] {data['unit_name']} (ID={unit.unit_id})")

    db.commit()
    return code_to_id


def seed_users(db, code_to_unit_id: dict[str, int]) -> dict[str, int]:
    """Tạo 1 user mỗi role, trả về dict {email: user_id}"""
    print("\n👤 Seeding Users...")
    email_to_id: dict[str, int] = {}
    hashed_pw = get_password_hash(DEFAULT_PASSWORD)

    for data in USERS:
        existing = db.query(User).filter_by(email=data["email"]).first()
        if existing:
            print(f"   ⚠️  Đã tồn tại: {data['email']}")
            email_to_id[data["email"]] = existing.user_id
            continue

        org_id = code_to_unit_id.get(data["org_unit_code"])
        user = User(
            email=data["email"],
            full_name=data["full_name"],
            hashed_password=hashed_pw,
            role=data["role"],
            job_title=data["job_title"],
            security_clearance=data["security_clearance"],
            org_unit_id=org_id,
            status=True,
            auth_provider="local",
        )
        db.add(user)
        db.flush()
        email_to_id[data["email"]] = user.user_id
        print(f"   ✅ Tạo: [{data['role'].value}] {data['full_name']} — {data['email']} (ID={user.user_id})")

    db.commit()
    return email_to_id


def seed_attributes(db):
    """Tạo ABAC Attributes"""
    print("\n🔑 Seeding ABAC Attributes...")
    for data in ATTRIBUTES:
        existing = db.query(AbacAttribute).filter_by(attr_key=data["attr_key"]).first()
        if existing:
            print(f"   ⚠️  Đã tồn tại: {data['attr_key']}")
            continue

        attr = AbacAttribute(
            attr_key=data["attr_key"],
            attr_type=data["attr_type"],
            source_table=data.get("source_table"),
            description=data.get("description"),
            mapping_path=data.get("mapping_path"),
        )
        db.add(attr)
        print(f"   ✅ Tạo attribute: {data['attr_key']} → {data.get('mapping_path')}")

    db.commit()


def seed_policies(db):
    """Upsert ABAC Policies — cập nhật nếu đã tồn tại để fix sai lệch cũ."""
    print("\n🛡️  Seeding ABAC Policies (upsert)...")
    for data in POLICIES:
        existing = db.query(AbacPolicy).filter_by(name=data["name"]).first()
        if existing:
            # Cập nhật lại để fix các giá trị sai (VD: target_resource cũ bị sai)
            existing.target_resource = data["target_resource"]
            existing.action = data["action"]
            existing.effect = data["effect"]
            existing.priority = data["priority"]
            existing.condition_json = data["condition_json"]
            existing.description = data.get("description")
            existing.is_active = True
            print(f"   🔄 Cập nhật: {data['name']}")
            continue

        policy = AbacPolicy(
            name=data["name"],
            description=data.get("description"),
            target_resource=data["target_resource"],
            action=data["action"],
            effect=data["effect"],
            priority=data["priority"],
            condition_json=data["condition_json"],
            is_active=True,
        )
        db.add(policy)
        print(f"   ✅ Tạo mới: {data['name']}")

    db.commit()


def print_summary(email_to_id: dict[str, int]):
    print("\n" + "=" * 65)
    print("  SEED HOÀN TẤT — THÔNG TIN ĐĂNG NHẬP")
    print("=" * 65)
    print(f"  Mật khẩu chung: {DEFAULT_PASSWORD}")
    print("-" * 65)

    role_map = {u["email"]: u for u in USERS}
    print(f"  {'Email':<30} {'Role':<15} {'Họ tên'}")
    print("-" * 65)
    for email, uid in email_to_id.items():
        u = role_map.get(email, {})
        role = u.get("role", UserRole.ENGINEER).value if u else "?"
        name = u.get("full_name", "?")
        print(f"  {email:<30} {role:<15} {name}")
    print("=" * 65)

    print("\n📋 Phân quyền theo role:")
    role_perms = {
        "ADMIN":       "Toàn quyền mọi resource",
        "MANAGER":     "View/Approve/Reject/Export gói thầu | View dự án | Giao việc",
        "BID_MANAGER": "Create/Update/Submit gói thầu, dự án | Giao việc | Quản lý crawler",
        "SPECIALIST":  "Update/Submit gói thầu | View dự án | Update task",
        "ENGINEER":    "View gói thầu, dự án | View/Update task",
        "JKAN":        "View gói thầu, dự án, task (hạn chế)",
    }
    for role, perms in role_perms.items():
        print(f"  [{role:<12}] {perms}")
    print()


# ==============================================================================
# MAIN
# ==============================================================================
def main():
    print("🚀 Bắt đầu Seeder PC1 Bidding System...")
    db = SessionLocal()
    try:
        code_to_unit_id = seed_org_units(db)
        email_to_id     = seed_users(db, code_to_unit_id)
        seed_attributes(db)
        seed_policies(db)
        print_summary(email_to_id)
    except Exception as e:
        db.rollback()
        print(f"\n❌ LỖI: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()
