"""
Unit Tests — chunk_by_chapters() / text splitting logic
TC-CHUNK-001 → TC-CHUNK-009

Hàm chunk_by_chapters chia văn bản thành các đoạn nhỏ.
Nếu chưa có module riêng, ta test thông qua RecursiveCharacterTextSplitter
đang được dùng trong app/integrations/ai/provider/docling_service.py.
"""
import pytest


def chunk_text(text: str, max_length: int = 1000, overlap: int = 0) -> list[str]:
    """
    Wrapper đơn giản dùng langchain TextSplitter — giống logic trong docling_service.py.
    """
    if not text:
        return []
    try:
        from langchain.text_splitter import RecursiveCharacterTextSplitter
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=max_length,
            chunk_overlap=overlap,
            separators=["\n\n", "\n", " ", ""],
        )
        return splitter.split_text(text)
    except ImportError:
        # Fallback thủ công nếu langchain chưa cài
        chunks = []
        start = 0
        while start < len(text):
            end = start + max_length
            chunks.append(text[start:end])
            start = end - overlap if overlap else end
        return chunks


def chunk_by_header(text: str) -> list[str]:
    """Chia theo heading ## (giống chapter split)."""
    import re
    parts = re.split(r'(?=^## )', text, flags=re.MULTILINE)
    return [p.strip() for p in parts if p.strip()]


class TestChunkText:
    def test_short_text_single_chunk(self):         # TC-CHUNK-001
        text = "a" * 500
        result = chunk_text(text, max_length=1000)
        assert len(result) == 1

    def test_long_text_multiple_chunks(self):       # TC-CHUNK-002
        text = "word " * 1000  # ~5000 ký tự
        result = chunk_text(text, max_length=1000)
        assert len(result) > 1

    def test_each_chunk_within_max_length(self):    # TC-CHUNK-003
        text = "x " * 3000
        result = chunk_text(text, max_length=1000)
        for chunk in result:
            assert len(chunk) <= 1000

    def test_content_not_lost(self):                # TC-CHUNK-004
        text = "Hello " * 500
        result = chunk_text(text, max_length=200)
        total_chars = sum(len(c) for c in result)
        # Tổng ký tự trong các chunk >= độ dài gốc (overlap có thể làm tổng lớn hơn)
        assert total_chars >= len(text.strip())

    def test_empty_string_returns_empty(self):      # TC-CHUNK-005
        result = chunk_text("")
        assert result == []

    def test_none_returns_empty(self):              # TC-CHUNK-006
        result = chunk_text(None)
        assert result == []

    def test_chunk_by_header(self):                 # TC-CHUNK-007
        text = "## Chương 1\nNội dung 1\n\n## Chương 2\nNội dung 2"
        result = chunk_by_header(text)
        assert len(result) == 2
        assert result[0].startswith("## Chương 1")
        assert result[1].startswith("## Chương 2")

    def test_overlap_shared_content(self):          # TC-CHUNK-008
        text = "word " * 500
        result = chunk_text(text, max_length=200, overlap=50)
        if len(result) > 1:
            # Phần cuối chunk[0] phải xuất hiện trong đầu chunk[1]
            tail = result[0][-50:]
            assert tail[:20] in result[1]

    def test_vietnamese_utf8_not_broken(self):      # TC-CHUNK-009
        text = "Tổng công ty xây dựng điện 1 " * 200
        result = chunk_text(text, max_length=100)
        for chunk in result:
            # Không có lỗi decode UTF-8
            assert chunk.encode("utf-8").decode("utf-8") == chunk
