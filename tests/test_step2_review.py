"""
Unit Tests — Bước 2: Review gói thầu
Coverage:
  - get_packages(): lọc theo status, search, loại trừ COMPLETED project
  - calculate_time_remaining(): deadline tương lai, quá hạn, chưa có lịch
  - get_file_by_id(): tìm thấy, không tìm thấy
  - check_permission(): ABAC — LIST, SUBMIT_REVIEW, APPROVE_BID
  - compare_values() / evaluate_logic_block(): logic engine của ABAC
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch


# ==============================================================================
# FIXTURES
# ==============================================================================
@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def bid_manager_user():
    from app.core.utils.enum import UserRole
    user = MagicMock()
    user.role = UserRole.BID_MANAGER
    user.user_id = 1
    return user


@pytest.fixture
def manager_user():
    from app.core.utils.enum import UserRole
    user = MagicMock()
    user.role = UserRole.MANAGER
    user.user_id = 2
    return user


@pytest.fixture
def specialist_user():
    from app.core.utils.enum import UserRole
    user = MagicMock()
    user.role = UserRole.SPECIALIST
    user.user_id = 3
    return user


@pytest.fixture
def sample_package():
    from app.modules.bidding.package.model import BiddingPackage
    from app.core.utils.enum import PackageStatus
    pkg = MagicMock(spec=BiddingPackage)
    pkg.__tablename__ = "bidding_packages"
    pkg.hsmt_id = 1
    pkg.ma_tbmt = "20250512-001"
    pkg.ten_goi_thau = "Gói thầu xây lắp"
    pkg.trang_thai = PackageStatus.INTERESTED
    pkg.thoi_diem_dong_thau = datetime.now() + timedelta(days=10)
    return pkg


# ==============================================================================
# TEST get_packages — filter, search, pagination
# ==============================================================================
class TestGetPackages:
    def test_filter_by_status_interested(self, mock_db):
        from app.modules.bidding.package.crud import get_packages
        from app.core.utils.enum import PackageStatus

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.outerjoin.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 1
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [MagicMock()]

        items, total = get_packages(mock_db, status=PackageStatus.INTERESTED)

        assert total == 1
        assert len(items) == 1

    def test_returns_empty_when_no_match(self, mock_db):
        from app.modules.bidding.package.crud import get_packages

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.outerjoin.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 0
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        items, total = get_packages(mock_db, search_query="không tồn tại xyz")

        assert total == 0
        assert items == []

    def test_pagination_params_passed(self, mock_db):
        from app.modules.bidding.package.crud import get_packages

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.outerjoin.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 50
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [MagicMock()] * 10

        items, total = get_packages(mock_db, skip=20, limit=10)

        mock_query.offset.assert_called_with(20)
        mock_query.limit.assert_called_with(10)


# ==============================================================================
# TEST calculate_time_remaining — logic đếm ngược
# ==============================================================================
class TestCalculateTimeRemaining:
    def test_deadline_in_future_days(self):
        from app.modules.bidding.package.crud import calculate_time_remaining
        deadline = datetime.now() + timedelta(days=3, hours=5)
        result = calculate_time_remaining(deadline)
        assert "ngày" in result
        assert "3" in result

    def test_deadline_in_future_hours_only(self):
        from app.modules.bidding.package.crud import calculate_time_remaining
        deadline = datetime.now() + timedelta(hours=4, minutes=30)
        result = calculate_time_remaining(deadline)
        assert "giờ" in result
        assert "ngày" not in result

    def test_deadline_in_future_minutes_only(self):
        from app.modules.bidding.package.crud import calculate_time_remaining
        deadline = datetime.now() + timedelta(minutes=45)
        result = calculate_time_remaining(deadline)
        assert "phút" in result

    def test_deadline_passed(self):
        from app.modules.bidding.package.crud import calculate_time_remaining
        deadline = datetime.now() - timedelta(hours=1)
        result = calculate_time_remaining(deadline)
        assert result == "Đã đóng thầu"

    def test_no_deadline(self):
        from app.modules.bidding.package.crud import calculate_time_remaining
        result = calculate_time_remaining(None)
        assert result == "Chưa có lịch"


# ==============================================================================
# TEST get_file_by_id
# ==============================================================================
class TestGetFileById:
    def test_found(self, mock_db):
        from app.modules.bidding.package.crud import get_file_by_id
        from app.modules.bidding.package.model import BiddingPackageFile

        mock_file = MagicMock(spec=BiddingPackageFile)
        mock_file.file_id = 5
        mock_db.query.return_value.filter.return_value.first.return_value = mock_file

        result = get_file_by_id(mock_db, file_id=5)
        assert result is not None
        assert result.file_id == 5

    def test_not_found_returns_none(self, mock_db):
        from app.modules.bidding.package.crud import get_file_by_id

        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = get_file_by_id(mock_db, file_id=999)
        assert result is None


# ==============================================================================
# TEST compare_values — ABAC logic engine
# ==============================================================================
class TestCompareValues:
    def setup_method(self):
        from app.core.permission.abac import compare_values
        self.compare = compare_values

    def test_eq_matching(self):
        assert self.compare("BID_MANAGER", "eq", "BID_MANAGER") is True

    def test_eq_not_matching(self):
        assert self.compare("SPECIALIST", "eq", "BID_MANAGER") is False

    def test_in_list_match(self):
        assert self.compare("MANAGER", "in", ["MANAGER", "ADMIN"]) is True

    def test_in_list_no_match(self):
        assert self.compare("SPECIALIST", "in", ["MANAGER", "ADMIN"]) is False

    def test_gte_numeric(self):
        assert self.compare(100, "gte", 50) is True

    def test_lte_boundary(self):
        assert self.compare(50, "lte", 50) is True

    def test_none_value_returns_false(self):
        assert self.compare(None, "eq", "MANAGER") is False

    def test_neq(self):
        assert self.compare("SPECIALIST", "neq", "MANAGER") is True


# ==============================================================================
# TEST check_permission — ABAC integration
# ==============================================================================
class TestCheckPermission:
    def _make_policy(self, name, resource, actions, role, effect="ALLOW", condition=None):
        from app.modules.abac_config.model import AbacPolicy, PolicyEffect
        policy = MagicMock(spec=AbacPolicy)
        policy.name = name
        policy.target_resource = resource
        policy.action = actions
        policy.effect = PolicyEffect.ALLOW if effect == "ALLOW" else PolicyEffect.DENY
        policy.condition_json = condition
        policy.is_active = True
        policy.priority = 10
        return policy

    def test_bid_manager_can_list_packages(self, mock_db, bid_manager_user, sample_package):
        from app.core.permission.abac import check_permission, _POLICY_STORE, ATTRIBUTE_MAPPING_CACHE
        from app.core.utils.enum import AbacAction

        policy = self._make_policy(
            name="[BID_MANAGER] LIST packages",
            resource="bidding_packages",
            actions=["LIST"],
            role="BID_MANAGER",
            condition={
                "condition": "AND",
                "rules": [{"field": "user.role", "operator": "eq", "value": "BID_MANAGER"}]
            }
        )

        bid_manager_user.role = "BID_MANAGER"

        with patch("app.core.permission.abac.get_policies_from_cache", return_value=[policy]), \
             patch("app.core.permission.abac.ATTRIBUTE_MAPPING_CACHE", {"user.role": "user.role"}):
            result = check_permission(mock_db, bid_manager_user, sample_package, AbacAction.LIST)

        assert result is True

    def test_specialist_cannot_approve(self, mock_db, specialist_user, sample_package):
        from app.core.permission.abac import check_permission

        policy = self._make_policy(
            name="[MANAGER] APPROVE",
            resource="bidding_packages",
            actions=["APPROVE_BID"],
            role="MANAGER",
            condition={
                "condition": "AND",
                "rules": [{"field": "user.role", "operator": "eq", "value": "MANAGER"}]
            }
        )

        specialist_user.role = "SPECIALIST"

        with patch("app.core.permission.abac.get_policies_from_cache", return_value=[policy]), \
             patch("app.core.permission.abac.ATTRIBUTE_MAPPING_CACHE", {"user.role": "user.role"}):
            # APPROVE_BID dùng raw string (không có trong AbacAction enum)
            result = check_permission(mock_db, specialist_user, sample_package, "APPROVE_BID")

        assert result is False

    def test_no_policy_returns_false(self, mock_db, bid_manager_user, sample_package):
        """Zero trust: không có policy nào → từ chối."""
        from app.core.permission.abac import check_permission
        from app.core.utils.enum import AbacAction

        with patch("app.core.permission.abac.get_policies_from_cache", return_value=[]), \
             patch("app.core.permission.abac.ATTRIBUTE_MAPPING_CACHE", {}):
            result = check_permission(mock_db, bid_manager_user, sample_package, AbacAction.LIST)

        assert result is False

    def test_none_user_returns_false(self, mock_db, sample_package):
        """User None → từ chối ngay, không crash."""
        from app.core.permission.abac import check_permission
        from app.core.utils.enum import AbacAction

        result = check_permission(mock_db, None, sample_package, AbacAction.VIEW)
        assert result is False

    def test_submit_review_allowed_for_bid_manager(self, mock_db, bid_manager_user, sample_package):
        from app.core.permission.abac import check_permission
        from app.core.utils.enum import AbacAction

        policy = self._make_policy(
            name="[BID_MANAGER] SUBMIT_REVIEW",
            resource="bidding_packages",
            actions=["SUBMIT_REVIEW"],
            role="BID_MANAGER",
            condition={
                "condition": "AND",
                "rules": [{"field": "user.role", "operator": "eq", "value": "BID_MANAGER"}]
            }
        )

        bid_manager_user.role = "BID_MANAGER"

        with patch("app.core.permission.abac.get_policies_from_cache", return_value=[policy]), \
             patch("app.core.permission.abac.ATTRIBUTE_MAPPING_CACHE", {"user.role": "user.role"}):
            result = check_permission(mock_db, bid_manager_user, sample_package, AbacAction.SUBMIT_REVIEW)

        assert result is True
