"""
Unit Tests — MAP constants & app/core/utils/enum.py
TC-ENUM-001 → TC-ENUM-006
"""
import pytest


class TestMapInvestField:
    def setup_method(self):
        from app.integrations.crawlers.crawler_bot import MAP_INVEST_FIELD
        self.MAP = MAP_INVEST_FIELD

    def test_xl_maps_to_xay_lap(self):             # TC-ENUM-001
        assert self.MAP.get("XL") == "Xây lắp"

    def test_hon_hop_maps_to_hon_hop(self):        # TC-ENUM-002
        assert self.MAP.get("HON_HOP") == "Hỗn hợp"

    def test_unknown_code_returns_none(self):       # TC-ENUM-005 (partial)
        assert self.MAP.get("UNKNOWN_CODE") is None

    def test_get_with_fallback(self):               # TC-ENUM-005
        result = self.MAP.get("UNKNOWN_CODE", "UNKNOWN_CODE")
        assert result == "UNKNOWN_CODE"


class TestMapBidForm:
    def test_dtrr_maps_correctly(self):            # TC-ENUM-003
        from app.integrations.crawlers.crawler_bot import MAP_BID_FORM
        assert MAP_BID_FORM.get("DTRR") == "Đấu thầu rộng rãi"


class TestMapContract:
    def test_tg_maps_correctly(self):              # TC-ENUM-004
        from app.integrations.crawlers.crawler_bot import MAP_CONTRACT
        assert MAP_CONTRACT.get("TG") == "Trọn gói"


class TestPackageStatusEnum:
    def test_interested_value(self):               # TC-ENUM-006
        from app.core.utils.enum import PackageStatus
        assert PackageStatus.INTERESTED.value == "INTERESTED"

    def test_bidding_value(self):
        from app.core.utils.enum import PackageStatus
        assert PackageStatus.BIDDING.value == "BIDDING"

    def test_pending_review_value(self):
        from app.core.utils.enum import PackageStatus
        assert PackageStatus.PENDING_REVIEW.value == "PENDING_REVIEW"
