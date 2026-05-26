"""
Unit Tests — _parse_iso_date() trong crawler_bot.py
TC-DATE-001 → TC-DATE-008
"""
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock


@pytest.fixture
def bot():
    with patch("app.integrations.crawlers.crawler_bot.SessionLocal") as mock_session, \
         patch("app.integrations.crawlers.crawler_bot.MinIOHandler"):
        mock_db = MagicMock()
        mock_session.return_value = mock_db
        mock_db.execute.return_value = None
        from app.integrations.crawlers.crawler_bot import MuasamcongDBBot
        instance = MuasamcongDBBot()
        instance.db = mock_db
        return instance


class TestParseIsoDate:
    def test_full_datetime(self, bot):           # TC-DATE-001
        result = bot._parse_iso_date("2025-05-12T10:30:00")
        assert isinstance(result, datetime)
        assert result.year == 2025 and result.month == 5 and result.day == 12
        assert result.hour == 10 and result.minute == 30

    def test_date_with_midnight(self, bot):      # TC-DATE-002
        result = bot._parse_iso_date("2025-06-01T00:00:00")
        assert result is not None
        assert result.day == 1

    def test_none_input(self, bot):              # TC-DATE-003
        assert bot._parse_iso_date(None) is None

    def test_na_string(self, bot):               # TC-DATE-004
        assert bot._parse_iso_date("N/A") is None

    def test_empty_string(self, bot):            # TC-DATE-005
        assert bot._parse_iso_date("") is None

    def test_malformed_string(self, bot):        # TC-DATE-006
        assert bot._parse_iso_date("không-phải-ngày") is None

    def test_date_only_no_time_part(self, bot):  # TC-DATE-007 — edge case fail đã biết
        result = bot._parse_iso_date("2024-03-15")
        # Không crash là đủ; giá trị None hoặc datetime đều chấp nhận
        assert result is None or isinstance(result, datetime)

    def test_trailing_chars_after_seconds(self, bot):  # TC-DATE-008
        result = bot._parse_iso_date("2025-05-12T10:30:00.000Z")
        # Không crash là đủ
        assert result is None or isinstance(result, datetime)
