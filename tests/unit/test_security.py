"""
Unit Tests — app/core/security.py
TC-SEC-001 → TC-SEC-012
"""
import pytest
from datetime import timedelta
from unittest.mock import patch


@pytest.fixture
def secret_key():
    return "test_secret_key_for_unit_testing_only"


@pytest.fixture(autouse=True)
def patch_env(secret_key):
    with patch("app.core.security.SECRET_KEY", secret_key), \
         patch("app.core.security.ALGORITHM", "HS256"), \
         patch("app.core.security.ACCESS_TOKEN_EXPIRE_MINUTES", 60), \
         patch("app.core.security.REFRESH_TOKEN_EXPIRE_DAYS", 7):
        yield


class TestPasswordHash:
    def test_hash_returns_bcrypt_string(self):
        # TC-SEC-001
        from app.core.security import get_password_hash
        result = get_password_hash("matkhau123")
        assert result.startswith("$2b$")

    def test_hash_same_input_different_output(self):
        # TC-SEC-002 — salt random nên hai lần hash khác nhau
        from app.core.security import get_password_hash
        hash1 = get_password_hash("matkhau123")
        hash2 = get_password_hash("matkhau123")
        assert hash1 != hash2

    def test_verify_correct_password(self):
        # TC-SEC-003
        from app.core.security import get_password_hash, verify_password
        hashed = get_password_hash("matkhau123")
        assert verify_password("matkhau123", hashed) is True

    def test_verify_wrong_password(self):
        # TC-SEC-004
        from app.core.security import get_password_hash, verify_password
        hashed = get_password_hash("matkhau123")
        assert verify_password("saimatkhau", hashed) is False

    def test_verify_empty_password(self):
        # TC-SEC-005
        from app.core.security import get_password_hash, verify_password
        hashed = get_password_hash("matkhau123")
        assert verify_password("", hashed) is False


class TestJWT:
    def test_create_access_token_returns_jwt(self):
        # TC-SEC-006
        from app.core.security import create_access_token
        token = create_access_token({"sub": "user@test.com"})
        assert len(token.split(".")) == 3

    def test_decode_access_token_contains_sub(self):
        # TC-SEC-007
        from app.core.security import create_access_token, decode_token
        token = create_access_token({"sub": "user@test.com"})
        payload = decode_token(token)
        assert payload["sub"] == "user@test.com"

    def test_refresh_token_contains_type_refresh(self):
        # TC-SEC-008
        from app.core.security import create_refresh_token, decode_token
        token = create_refresh_token({"sub": "user@test.com"})
        payload = decode_token(token)
        assert payload["type"] == "refresh"

    def test_expired_token_returns_none(self):
        # TC-SEC-009
        from app.core.security import create_access_token, decode_token
        token = create_access_token({"sub": "user@test.com"}, expires_delta=timedelta(seconds=-1))
        result = decode_token(token)
        assert result is None

    def test_wrong_secret_key_returns_none(self):
        # TC-SEC-010
        from app.core.security import create_access_token
        token = create_access_token({"sub": "user@test.com"})
        with patch("app.core.security.SECRET_KEY", "wrong_key"):
            from app.core.security import decode_token
            result = decode_token(token)
        assert result is None

    def test_random_string_returns_none(self):
        # TC-SEC-011
        from app.core.security import decode_token
        result = decode_token("không.phải.jwt")
        assert result is None

    def test_bearer_prefix_stripped(self):
        # TC-SEC-012
        from app.core.security import create_access_token, decode_token
        token = create_access_token({"sub": "user@test.com"})
        result = decode_token(f"Bearer {token}")
        assert result is not None
        assert result["sub"] == "user@test.com"
