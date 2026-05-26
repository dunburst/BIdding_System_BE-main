"""
Unit Tests — Bước 1: Tự động thu thập (Crawler)
Coverage:
  - build_tbmt_data(): MAP fields, parse date, trạng thái ban đầu
  - _parse_iso_date(): các dạng chuỗi ngày hợp lệ / không hợp lệ
  - save_package_to_db(): INSERT mới, UPDATE nếu đã tồn tại, rollback khi lỗi
  - update_file_path(): upsert file — không tạo bản ghi trùng lặp
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock


# ==============================================================================
# FIXTURE — Mock toàn bộ dependencies của MuasamcongDBBot.__init__
# ==============================================================================
@pytest.fixture
def bot():
    """Tạo instance MuasamcongDBBot với DB và MinIO được mock hoàn toàn."""
    with patch("app.integrations.crawlers.crawler_bot.SessionLocal") as mock_session, \
         patch("app.integrations.crawlers.crawler_bot.MinIOHandler"):
        mock_db = MagicMock()
        mock_session.return_value = mock_db
        mock_db.execute.return_value = None  # SELECT 1 thành công

        from app.integrations.crawlers.crawler_bot import MuasamcongDBBot
        instance = MuasamcongDBBot()
        instance.db = mock_db
        return instance


# ==============================================================================
# SAMPLE DATA
# ==============================================================================
SAMPLE_API_JSON = {
    "bidoNotifyContractorM": {
        "notifyNo": "20250512-001",
        "notifyVersion": "1",
        "publicDate": "2025-05-12T08:00:00",
        "bidName": "Gói thầu xây lắp nhà máy điện",
        "investorName": "Tập đoàn PC1",
        "investField": "XL",
        "bidForm": "DTRR",
        "contractType": "TG",
        "bidMode": "1_MTHS",
        "planType": "DTPT",
        "bidCloseDate": "2025-06-01T17:00:00",
        "bidOpenDate": "2025-06-02T09:00:00",
        "isDomestic": "1",
        "isInternet": "1",
        "isMultiLot": "0",
        "guaranteeValue": 50000000,
        "contractPeriod": 180,
        "contractPeriodUnit": "D",
        "bidValidityPeriod": 90,
        "bidValidityPeriodUnit": "D",
        "receiveFee": None,
        "ebidFee": 500000,
    }
}


# ==============================================================================
# TEST _parse_iso_date
# ==============================================================================
class TestParseIsoDate:
    def test_valid_full_datetime(self, bot):
        result = bot._parse_iso_date("2025-05-12T10:30:00")
        assert isinstance(result, datetime)
        assert result.year == 2025
        assert result.month == 5
        assert result.day == 12
        assert result.hour == 10
        assert result.minute == 30

    def test_valid_date_only(self, bot):
        result = bot._parse_iso_date("2025-06-01T00:00:00")
        assert result is not None
        assert result.day == 1

    def test_none_input(self, bot):
        assert bot._parse_iso_date(None) is None

    def test_na_string(self, bot):
        assert bot._parse_iso_date("N/A") is None

    def test_empty_string(self, bot):
        assert bot._parse_iso_date("") is None

    def test_malformed_string(self, bot):
        assert bot._parse_iso_date("không-phải-ngày") is None


# ==============================================================================
# TEST build_tbmt_data — MAP fields
# ==============================================================================
class TestBuildTbmtData:
    def test_returns_dict_with_ma_tbmt(self, bot):
        result = bot.build_tbmt_data(SAMPLE_API_JSON, "https://muasamcong.mpi.gov.vn/package/1")
        assert result is not None
        assert result["ma_tbmt"] == "20250512-001"

    def test_map_invest_field_xay_lap(self, bot):
        result = bot.build_tbmt_data(SAMPLE_API_JSON, "http://example.com")
        assert result["linh_vuc"] == "Xây lắp"

    def test_map_invest_field_hon_hop(self, bot):
        json_hon_hop = {
            "bidoNotifyContractorM": {
                **SAMPLE_API_JSON["bidoNotifyContractorM"],
                "investField": "HON_HOP",
            }
        }
        result = bot.build_tbmt_data(json_hon_hop, "http://example.com")
        assert result["linh_vuc"] == "Hỗn hợp"

    def test_map_invest_field_unknown_code_passthrough(self, bot):
        """Mã không có trong MAP thì giữ nguyên code gốc."""
        json_unknown = {
            "bidoNotifyContractorM": {
                **SAMPLE_API_JSON["bidoNotifyContractorM"],
                "investField": "UNKNOWN_CODE",
            }
        }
        result = bot.build_tbmt_data(json_unknown, "http://example.com")
        assert result["linh_vuc"] == "UNKNOWN_CODE"

    def test_map_bid_form(self, bot):
        result = bot.build_tbmt_data(SAMPLE_API_JSON, "http://example.com")
        assert result["hinh_thuc_lua_chon_nha_thau"] == "Đấu thầu rộng rãi"

    def test_map_contract_type(self, bot):
        result = bot.build_tbmt_data(SAMPLE_API_JSON, "http://example.com")
        assert result["loai_hop_dong"] == "Trọn gói"

    def test_domestic_flag(self, bot):
        result = bot.build_tbmt_data(SAMPLE_API_JSON, "http://example.com")
        assert result["trong_nuoc_hoac_quoc_te"] == "Trong nước"

    def test_international_flag(self, bot):
        json_intl = {
            "bidoNotifyContractorM": {
                **SAMPLE_API_JSON["bidoNotifyContractorM"],
                "isDomestic": "0",
            }
        }
        result = bot.build_tbmt_data(json_intl, "http://example.com")
        assert result["trong_nuoc_hoac_quoc_te"] == "Quốc tế"

    def test_internet_bid_sets_msc_url(self, bot):
        result = bot.build_tbmt_data(SAMPLE_API_JSON, "http://example.com")
        assert result["dia_diem_phat_hanh_e_hsmt"] == "https://muasamcong.mpi.gov.vn"

    def test_fee_falls_back_to_ebid_fee(self, bot):
        """receiveFee=None nên fallback sang ebidFee=500000."""
        result = bot.build_tbmt_data(SAMPLE_API_JSON, "http://example.com")
        assert result["chi_phi_nop"] == 500000.0

    def test_status_always_interested(self, bot):
        from app.core.utils.enum import PackageStatus
        result = bot.build_tbmt_data(SAMPLE_API_JSON, "http://example.com")
        assert result["trang_thai"] == PackageStatus.INTERESTED

    def test_contract_period_formatted(self, bot):
        result = bot.build_tbmt_data(SAMPLE_API_JSON, "http://example.com")
        assert result["thoi_gian_thuc_hien_goi_thau"] == "180 ngày"

    def test_missing_notify_no_returns_none(self, bot):
        """Nếu không có notifyNo thì trả về None, không crash."""
        result = bot.build_tbmt_data({"bidoNotifyContractorM": {}}, "http://example.com")
        assert result is None

    def test_empty_json_returns_none(self, bot):
        assert bot.build_tbmt_data({}, "http://example.com") is None


# ==============================================================================
# TEST save_package_to_db — INSERT vs UPDATE
# ==============================================================================
class TestSavePackageToDB:
    def test_insert_new_package(self, bot):
        """Gói thầu chưa có trong DB → INSERT."""
        bot.db.query.return_value.filter.return_value.first.return_value = None

        from app.modules.bidding.package.model import BiddingPackage
        mock_pkg = MagicMock(spec=BiddingPackage)
        mock_pkg.hsmt_id = 99

        with patch("app.integrations.crawlers.crawler_bot.BiddingPackage", return_value=mock_pkg):
            result = bot.save_package_to_db({"ma_tbmt": "NEW-001", "ten_goi_thau": "Test"})

        bot.db.add.assert_called_once()
        bot.db.commit.assert_called_once()

    def test_update_existing_package(self, bot):
        """Gói thầu đã có trong DB → UPDATE các trường, không INSERT thêm."""
        from app.modules.bidding.package.model import BiddingPackage
        existing = MagicMock(spec=BiddingPackage)
        existing.hsmt_id = 5
        bot.db.query.return_value.filter.return_value.first.return_value = existing

        result = bot.save_package_to_db({
            "ma_tbmt": "EXIST-001",
            "ten_goi_thau": "Tên mới",
            "chu_dau_tu": "PC1",
        })

        bot.db.add.assert_not_called()
        bot.db.commit.assert_called_once()
        assert existing.ten_goi_thau == "Tên mới"

    def test_rollback_on_exception(self, bot):
        """Nếu lỗi xảy ra → rollback, trả về None, không raise."""
        bot.db.query.side_effect = Exception("DB timeout")

        result = bot.save_package_to_db({"ma_tbmt": "ERR-001"})

        assert result is None
        bot.db.rollback.assert_called_once()


# ==============================================================================
# TEST update_file_path — upsert, không tạo bản ghi trùng
# ==============================================================================
class TestUpdateFilePath:
    def _setup_package(self, bot, hsmt_id=10):
        from app.modules.bidding.package.model import BiddingPackage
        mock_pkg = MagicMock(spec=BiddingPackage)
        mock_pkg.hsmt_id = hsmt_id
        return mock_pkg

    def test_insert_when_file_not_exists(self, bot):
        """File chưa có → INSERT bản ghi mới."""
        mock_pkg = self._setup_package(bot)
        # query 1: tìm package → trả về mock_pkg
        # query 2: tìm file → trả về None
        bot.db.query.return_value.filter_by.return_value.first.side_effect = [mock_pkg, None]

        bot.update_file_path("MA-001", "http://minio/files/doc.pdf", "doc.pdf")

        bot.db.add.assert_called_once()
        bot.db.commit.assert_called_once()

    def test_skip_when_file_path_unchanged(self, bot):
        """File đã có + path giống → không commit, không add."""
        mock_pkg = self._setup_package(bot)
        mock_file = MagicMock()
        mock_file.file_path = "http://minio/files/doc.pdf"

        bot.db.query.return_value.filter_by.return_value.first.side_effect = [mock_pkg, mock_file]

        bot.update_file_path("MA-001", "http://minio/files/doc.pdf", "doc.pdf")

        bot.db.add.assert_not_called()
        bot.db.commit.assert_not_called()

    def test_update_when_file_path_changed(self, bot):
        """File đã có + path khác → UPDATE path, commit."""
        mock_pkg = self._setup_package(bot)
        mock_file = MagicMock()
        mock_file.file_path = "http://minio/files/old.pdf"

        bot.db.query.return_value.filter_by.return_value.first.side_effect = [mock_pkg, mock_file]

        bot.update_file_path("MA-001", "http://minio/files/new.pdf", "doc.pdf")

        assert mock_file.file_path == "http://minio/files/new.pdf"
        bot.db.commit.assert_called_once()

    def test_skip_when_package_not_found(self, bot):
        """Package không tồn tại → bỏ qua, không crash."""
        bot.db.query.return_value.filter_by.return_value.first.return_value = None

        bot.update_file_path("GHOST-999", "http://minio/files/doc.pdf", "doc.pdf")

        bot.db.add.assert_not_called()
        bot.db.commit.assert_not_called()
