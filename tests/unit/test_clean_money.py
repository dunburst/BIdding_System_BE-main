"""
Unit Tests — clean_money() helper
TC-CLEAN-001 → TC-CLEAN-010

Hàm clean_money nhận chuỗi/số tiền, trả về float hoặc None.
Vì hàm này nằm inline trong nhiều file, ta định nghĩa lại ở đây để test độc lập.
"""
import pytest
import re


def clean_money(value):
    """Hàm làm sạch chuỗi tiền tệ → float. Trả về None nếu không parse được."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    s = str(value).strip()
    if not s:
        return None
    # Bỏ đơn vị tiền tệ
    s = s.upper().replace("VND", "").replace("VNĐ", "").replace("ĐỒNG", "").strip()
    # Xóa dấu phẩy và dấu chấm ngăn cách hàng nghìn
    s = re.sub(r"[.,](?=\d{3})", "", s)
    # Giữ lại số và dấu trừ
    s = re.sub(r"[^\d\-]", "", s)
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


class TestCleanMoney:
    def test_vnd_dot_separator(self):       # TC-CLEAN-001
        assert clean_money("160.000.000 VND") == 160000000.0

    def test_comma_separator(self):          # TC-CLEAN-002
        assert clean_money("1,500,000") == 1500000.0

    def test_integer_input(self):            # TC-CLEAN-003
        assert clean_money(50000) == 50000

    def test_none_input(self):               # TC-CLEAN-004
        assert clean_money(None) is None

    def test_empty_string(self):             # TC-CLEAN-005
        assert clean_money("") is None

    def test_non_numeric_string(self):       # TC-CLEAN-006
        assert clean_money("abc xyz") is None

    def test_9_digit_dot_format(self):       # TC-CLEAN-007
        assert clean_money("94.000.000") == 94000000.0

    def test_zero_string(self):              # TC-CLEAN-008
        assert clean_money("0") == 0.0

    def test_negative_value(self):           # TC-CLEAN-009
        assert clean_money("-50.000") == -50000.0

    def test_no_unit_suffix(self):           # TC-CLEAN-010
        assert clean_money("330000 VND") == 330000.0
