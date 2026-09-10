import pytest

from app.errors import ValidationError
from app.ingestion.pipeline import extract_document


def test_extract_document_normalizes_plain_text() -> None:
    result = extract_document(
        content_type="text/plain", data=b"line one   \r\nline two", filename="notes.txt"
    )
    assert result.pages[0].text == "line one\nline two"


def test_extract_document_rejects_unsupported_content_type() -> None:
    with pytest.raises(ValidationError):
        extract_document(content_type="application/zip", data=b"PK\x03\x04", filename="a.zip")
