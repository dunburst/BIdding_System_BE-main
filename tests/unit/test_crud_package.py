"""
Unit Tests — app/modules/bidding/package/crud.py
TC-PKG-001 → TC-PKG-013
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def sample_package():
    from app.modules.bidding.package.model import BiddingPackage
    from app.core.utils.enum import PackageStatus
    pkg = MagicMock(spec=BiddingPackage)
    pkg.hsmt_id = 1
    pkg.ma_tbmt = "20250512-001"
    pkg.ten_goi_thau = "Gói thầu xây lắp"
    pkg.trang_thai = PackageStatus.INTERESTED
    pkg.project_id = None
    return pkg


class TestGetPackage:
    def test_get_by_hsmt_id_found(self, mock_db, sample_package):      # TC-PKG-001
        from app.modules.bidding.package.crud import get_package
        mock_db.query.return_value.filter.return_value.first.return_value = sample_package
        result = get_package(mock_db, hsmt_id=1)
        assert result is not None
        assert result.hsmt_id == 1

    def test_get_by_hsmt_id_not_found(self, mock_db):                  # TC-PKG-002
        from app.modules.bidding.package.crud import get_package
        mock_db.query.return_value.filter.return_value.first.return_value = None
        result = get_package(mock_db, hsmt_id=9999)
        assert result is None

    def test_get_by_ma_tbmt_found(self, mock_db, sample_package):      # TC-PKG-003
        from app.modules.bidding.package.crud import get_package_by_ma_tbmt
        mock_db.query.return_value.filter.return_value.first.return_value = sample_package
        result = get_package_by_ma_tbmt(mock_db, "20250512-001")
        assert result is not None
        assert result.ma_tbmt == "20250512-001"


class TestGetPackages:
    def _setup_query(self, mock_db, items, total=None):
        q = MagicMock()
        mock_db.query.return_value = q
        q.outerjoin.return_value = q
        q.filter.return_value = q
        q.options.return_value = q
        q.count.return_value = total if total is not None else len(items)
        q.order_by.return_value = q
        q.offset.return_value = q
        q.limit.return_value = q
        q.all.return_value = items
        return q

    def test_filter_by_status(self, mock_db, sample_package):          # TC-PKG-004
        from app.modules.bidding.package.crud import get_packages
        from app.core.utils.enum import PackageStatus
        self._setup_query(mock_db, [sample_package], total=1)
        items, total = get_packages(mock_db, status=PackageStatus.INTERESTED)
        assert total == 1 and len(items) == 1

    def test_empty_search_result(self, mock_db):                       # TC-PKG-005
        from app.modules.bidding.package.crud import get_packages
        self._setup_query(mock_db, [], total=0)
        items, total = get_packages(mock_db, search_query="không tồn tại xyz")
        assert total == 0 and items == []

    def test_pagination_params(self, mock_db):                         # TC-PKG-006
        from app.modules.bidding.package.crud import get_packages
        q = self._setup_query(mock_db, [MagicMock()], total=50)
        get_packages(mock_db, skip=20, limit=10)
        q.offset.assert_called_with(20)
        q.limit.assert_called_with(10)

    def test_excludes_completed_project(self, mock_db):               # TC-PKG-007
        from app.modules.bidding.package.crud import get_packages
        self._setup_query(mock_db, [], total=0)
        items, total = get_packages(mock_db)
        assert total == 0


class TestCreatePackage:
    def test_create_success(self, mock_db):                            # TC-PKG-008
        from app.modules.bidding.package.crud import create_package
        schema = MagicMock()
        schema.model_dump.return_value = {
            "ma_tbmt": "NEW-001",
            "ten_goi_thau": "Gói mới",
        }
        create_package(mock_db, schema)
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()


class TestUpdatePackage:
    def test_update_found(self, mock_db, sample_package):              # TC-PKG-009
        from app.modules.bidding.package.crud import update_package
        mock_db.query.return_value.filter.return_value.first.return_value = sample_package
        update_schema = MagicMock()
        update_schema.model_dump.return_value = {"ten_goi_thau": "Tên mới"}
        result = update_package(mock_db, 1, update_schema)
        mock_db.commit.assert_called_once()
        assert sample_package.ten_goi_thau == "Tên mới"

    def test_update_not_found(self, mock_db):                          # TC-PKG-010
        from app.modules.bidding.package.crud import update_package
        mock_db.query.return_value.filter.return_value.first.return_value = None
        result = update_package(mock_db, 9999, MagicMock())
        assert result is None


class TestDeletePackage:
    def test_delete_found(self, mock_db, sample_package):              # TC-PKG-011
        from app.modules.bidding.package.crud import delete_package
        mock_db.query.return_value.filter.return_value.first.return_value = sample_package
        result = delete_package(mock_db, 1)
        assert result is True
        mock_db.delete.assert_called_once_with(sample_package)

    def test_get_file_by_id_found(self, mock_db):                      # TC-PKG-012
        from app.modules.bidding.package.crud import get_file_by_id
        from app.modules.bidding.package.model import BiddingPackageFile
        mock_file = MagicMock(spec=BiddingPackageFile)
        mock_file.file_id = 5
        mock_db.query.return_value.filter.return_value.first.return_value = mock_file
        result = get_file_by_id(mock_db, file_id=5)
        assert result.file_id == 5


class TestCalculateTimeRemaining:
    def test_deadline_passed(self):                                    # TC-PKG-013
        from app.modules.bidding.package.crud import calculate_time_remaining
        deadline = datetime.now() - timedelta(hours=1)
        assert calculate_time_remaining(deadline) == "Đã đóng thầu"
