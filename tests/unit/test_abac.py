"""
Unit Tests — app/core/permission/abac.py
TC-ABAC-001 → TC-ABAC-014
"""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def sample_package():
    from app.modules.bidding.package.model import BiddingPackage
    pkg = MagicMock(spec=BiddingPackage)
    pkg.__tablename__ = "bidding_packages"
    pkg.trang_thai = "INTERESTED"
    return pkg


def make_policy(name, actions, role_value, effect="ALLOW"):
    from app.modules.abac_config.model import AbacPolicy, PolicyEffect
    p = MagicMock(spec=AbacPolicy)
    p.name = name
    p.action = actions
    p.effect = PolicyEffect.ALLOW if effect == "ALLOW" else PolicyEffect.DENY
    p.condition_json = {
        "condition": "AND",
        "rules": [{"field": "user.role", "operator": "eq", "value": role_value}]
    }
    p.is_active = True
    p.priority = 10
    return p


class TestCompareValues:
    def setup_method(self):
        from app.core.permission.abac import compare_values
        self.fn = compare_values

    def test_eq_match(self):                      # TC-ABAC-001
        assert self.fn("BID_MANAGER", "eq", "BID_MANAGER") is True

    def test_eq_no_match(self):                   # TC-ABAC-002
        assert self.fn("SPECIALIST", "eq", "BID_MANAGER") is False

    def test_in_list_match(self):                 # TC-ABAC-003
        assert self.fn("MANAGER", "in", ["MANAGER", "ADMIN"]) is True

    def test_in_list_no_match(self):              # TC-ABAC-004
        assert self.fn("SPECIALIST", "in", ["MANAGER", "ADMIN"]) is False

    def test_gte_true(self):                      # TC-ABAC-005
        assert self.fn(100, "gte", 50) is True

    def test_lte_boundary(self):                  # TC-ABAC-006
        assert self.fn(50, "lte", 50) is True

    def test_none_left_returns_false(self):        # TC-ABAC-007
        assert self.fn(None, "eq", "MANAGER") is False

    def test_neq_true(self):                      # TC-ABAC-008
        assert self.fn("SPECIALIST", "neq", "MANAGER") is True


class TestEvaluateLogicBlock:
    def setup_method(self):
        from app.core.permission.abac import evaluate_logic_block
        self.fn = evaluate_logic_block

    def _make_user(self, role):
        u = MagicMock()
        u.role = role
        return u

    def test_and_all_true(self):                  # TC-ABAC-009
        user = self._make_user("BID_MANAGER")
        block = {
            "condition": "AND",
            "rules": [
                {"field": "user.role", "operator": "eq", "value": "BID_MANAGER"},
            ]
        }
        with patch("app.core.permission.abac.ATTRIBUTE_MAPPING_CACHE", {"user.role": "user.role"}):
            assert self.fn(user, {}, block) is True

    def test_and_one_false(self):                 # TC-ABAC-010
        user = self._make_user("SPECIALIST")
        block = {
            "condition": "AND",
            "rules": [
                {"field": "user.role", "operator": "eq", "value": "BID_MANAGER"},
            ]
        }
        with patch("app.core.permission.abac.ATTRIBUTE_MAPPING_CACHE", {"user.role": "user.role"}):
            assert self.fn(user, {}, block) is False

    def test_or_one_true(self):                   # TC-ABAC-011
        user = self._make_user("MANAGER")
        block = {
            "condition": "OR",
            "rules": [
                {"field": "user.role", "operator": "eq", "value": "MANAGER"},
                {"field": "user.role", "operator": "eq", "value": "ADMIN"},
            ]
        }
        with patch("app.core.permission.abac.ATTRIBUTE_MAPPING_CACHE", {"user.role": "user.role"}):
            assert self.fn(user, {}, block) is True


class TestCheckPermission:
    def test_bid_manager_list_allowed(self, mock_db, sample_package):   # TC-ABAC-012
        from app.core.permission.abac import check_permission
        user = MagicMock(); user.role = "BID_MANAGER"
        policy = make_policy("[BID_MANAGER] LIST", ["LIST"], "BID_MANAGER")
        with patch("app.core.permission.abac.get_policies_from_cache", return_value=[policy]), \
             patch("app.core.permission.abac.ATTRIBUTE_MAPPING_CACHE", {"user.role": "user.role"}):
            assert check_permission(mock_db, user, sample_package, "LIST") is True

    def test_no_policy_zero_trust(self, mock_db, sample_package):       # TC-ABAC-013
        from app.core.permission.abac import check_permission
        user = MagicMock(); user.role = "BID_MANAGER"
        with patch("app.core.permission.abac.get_policies_from_cache", return_value=[]), \
             patch("app.core.permission.abac.ATTRIBUTE_MAPPING_CACHE", {}):
            assert check_permission(mock_db, user, sample_package, "LIST") is False

    def test_user_none_returns_false(self, mock_db, sample_package):    # TC-ABAC-014
        from app.core.permission.abac import check_permission
        assert check_permission(mock_db, None, sample_package, "VIEW") is False
