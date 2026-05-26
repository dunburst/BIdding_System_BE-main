"""
Unit Tests — app/infrastructure/storage/minio_client.py
TC-MINIO-001 → TC-MINIO-007
"""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def handler():
    """MinIOHandler với Minio client được mock — không cần server thật."""
    with patch("app.infrastructure.storage.minio_client.Minio") as MockMinio:
        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = True
        MockMinio.return_value = mock_client

        from app.infrastructure.storage.minio_client import MinIOHandler
        h = MinIOHandler()
        h.client = mock_client
        return h


@pytest.fixture
def handler_no_client():
    """MinIOHandler với client=None — giả lập kết nối thất bại."""
    with patch("app.infrastructure.storage.minio_client.Minio") as MockMinio:
        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = True
        MockMinio.return_value = mock_client

        from app.infrastructure.storage.minio_client import MinIOHandler
        h = MinIOHandler()
        h.client = None
        return h


class TestExtractObjectName:
    def test_standard_url(self, handler):         # TC-MINIO-001
        url = "http://10.31.1.85:9000/files/hsmt/doc.pdf"
        result = handler.extract_object_name_from_url(url)
        assert result == "hsmt/doc.pdf"

    def test_url_without_bucket_returns_none(self, handler):  # TC-MINIO-002
        url = "http://10.31.1.85:9000/other/doc.pdf"
        result = handler.extract_object_name_from_url(url, bucket_name="files")
        assert result is None

    def test_url_encoded_space(self, handler):    # TC-MINIO-003
        url = "http://host:9000/files/ho%20so/doc.pdf"
        result = handler.extract_object_name_from_url(url)
        assert result == "ho so/doc.pdf"

    def test_custom_bucket(self, handler):        # TC-MINIO-004
        url = "http://host:9000/jkancon/task_1/report.docx"
        result = handler.extract_object_name_from_url(url, bucket_name="jkancon")
        assert result == "task_1/report.docx"


class TestClientNone:
    def test_upload_file_no_client(self, handler_no_client):      # TC-MINIO-005
        result = handler_no_client.upload_file("any/path.pdf", "object_name")
        assert result is None

    def test_get_object_stream_no_client(self, handler_no_client): # TC-MINIO-006
        response, stat = handler_no_client.get_object_stream("object_name")
        assert response is None
        assert stat is None

    def test_delete_file_no_client(self, handler_no_client):      # TC-MINIO-007
        result = handler_no_client.delete_file("object_name")
        assert result is False
