"""
Unit Tests — app/modules/users/crud.py
TC-USER-001 → TC-USER-011
"""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def sample_user():
    from app.modules.users.model import User
    u = MagicMock(spec=User)
    u.user_id = 1
    u.email = "user@pc1.vn"
    u.full_name = "Nguyễn Văn A"
    u.status = True
    return u


class TestGetUser:
    def test_get_by_email_found(self, mock_db, sample_user):       # TC-USER-001
        from app.modules.users.crud import get_user_by_email
        mock_db.query.return_value.filter.return_value.first.return_value = sample_user
        result = get_user_by_email(mock_db, "user@pc1.vn")
        assert result is not None
        assert result.email == "user@pc1.vn"

    def test_get_by_email_not_found(self, mock_db):                # TC-USER-002
        from app.modules.users.crud import get_user_by_email
        mock_db.query.return_value.filter.return_value.first.return_value = None
        result = get_user_by_email(mock_db, "ghost@pc1.vn")
        assert result is None

    def test_get_by_id_found(self, mock_db, sample_user):          # TC-USER-003
        # get_user dùng db.execute().scalar_one_or_none()
        from app.modules.users.crud import get_user
        mock_db.execute.return_value.scalar_one_or_none.return_value = sample_user
        result = get_user(mock_db, 1)
        assert result is not None

    def test_get_by_id_not_found(self, mock_db):                   # TC-USER-004
        from app.modules.users.crud import get_user
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        result = get_user(mock_db, 9999)
        assert result is None


class TestCreateUser:
    def test_create_success(self, mock_db):                        # TC-USER-005
        from app.modules.users.crud import create_user
        from app.modules.users.schema import UserCreate
        schema = MagicMock(spec=UserCreate)
        schema.password = "matkhau123"
        schema.model_dump.return_value = {
            "email": "new@pc1.vn",
            "full_name": "Nguyễn Mới",
        }

        with patch("app.modules.users.crud.get_password_hash", return_value="hashed_pw"):
            result = create_user(mock_db, schema)

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_create_does_not_check_duplicate(self, mock_db):       # TC-USER-006
        # create_user thực tế không check duplicate (DB constraint lo),
        # test đảm bảo hàm luôn gọi add+commit khi input hợp lệ
        from app.modules.users.crud import create_user
        schema = MagicMock()
        schema.password = "pw"
        schema.model_dump.return_value = {"email": "a@b.com", "full_name": "Test"}
        with patch("app.modules.users.crud.get_password_hash", return_value="hashed"):
            create_user(mock_db, schema)
        mock_db.add.assert_called_once()


class TestUpdateUser:
    def test_update_found(self, mock_db, sample_user):             # TC-USER-007
        from app.modules.users.crud import update_user
        # update_user gọi get_user(db, id) dùng db.execute
        mock_db.execute.return_value.scalar_one_or_none.return_value = sample_user
        update_data = MagicMock()
        update_data.model_dump.return_value = {"full_name": "Tên Mới"}

        result = update_user(mock_db, 1, update_data)

        mock_db.commit.assert_called_once()
        assert sample_user.full_name == "Tên Mới"

    def test_update_not_found(self, mock_db):                      # TC-USER-008
        from app.modules.users.crud import update_user
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        result = update_user(mock_db, 9999, MagicMock())
        assert result is None


class TestDeleteUser:
    def test_soft_delete_found(self, mock_db, sample_user):        # TC-USER-009
        # delete_user_soft: vô hiệu hóa tài khoản thay vì xóa vật lý
        from app.modules.users.crud import delete_user_soft
        mock_db.query.return_value.filter.return_value.first.return_value = sample_user
        result = delete_user_soft(mock_db, 1)
        assert result is not False  # Trả về user object hoặc True

    def test_soft_delete_not_found(self, mock_db):                 # TC-USER-010
        from app.modules.users.crud import delete_user_soft
        mock_db.query.return_value.filter.return_value.first.return_value = None
        result = delete_user_soft(mock_db, 9999)
        assert result is False


class TestGetAllUsers:
    def test_pagination_params(self, mock_db):                     # TC-USER-011
        # get_users dùng db.execute().scalars().all()
        from app.modules.users.crud import get_users
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [MagicMock()] * 5
        mock_db.execute.return_value.scalars.return_value = mock_scalars

        result = get_users(mock_db, skip=10, limit=5)

        assert len(result) == 5
