import io

import pytest
from docx import Document as DocxDocument
from fpdf import FPDF

from app.errors import ValidationError
from app.ingestion.extractors import get_extractor
from app.ingestion.extractors.docx import DocxExtractor
from app.ingestion.extractors.pdf import PdfExtractor
from app.ingestion.extractors.text import PlainTextExtractor


def _make_pdf_bytes(pages: list[str]) -> bytes:
    pdf = FPDF()
    for page_text in pages:
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.multi_cell(0, 10, page_text)
    return bytes(pdf.output())


def _make_docx_bytes(paragraphs: list[str]) -> bytes:
    document = DocxDocument()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_plain_text_extractor_single_page() -> None:
    result = PlainTextExtractor().extract(b"hello world", filename="notes.txt")
    assert result.page_count == 1
    assert result.pages[0].page_number == 1
    assert result.pages[0].text == "hello world"


def test_plain_text_extractor_replaces_invalid_utf8() -> None:
    result = PlainTextExtractor().extract(b"valid \xff\xfe invalid", filename="notes.txt")
    assert "valid" in result.pages[0].text
    assert "�" in result.pages[0].text  # replacement character, no exception


def test_pdf_extractor_reads_pages_in_order() -> None:
    data = _make_pdf_bytes(["First page text", "Second page text"])
    result = PdfExtractor().extract(data, filename="doc.pdf")
    assert result.page_count == 2
    assert result.pages[0].page_number == 1
    assert result.pages[1].page_number == 2
    assert "First page" in result.pages[0].text
    assert "Second page" in result.pages[1].text


def test_pdf_extractor_rejects_corrupt_file() -> None:
    with pytest.raises(ValidationError):
        PdfExtractor().extract(b"not a real pdf", filename="broken.pdf")


def test_docx_extractor_joins_paragraphs_single_page() -> None:
    data = _make_docx_bytes(["Paragraph one.", "Paragraph two."])
    result = DocxExtractor().extract(data, filename="doc.docx")
    assert result.page_count == 1
    assert "Paragraph one." in result.pages[0].text
    assert "Paragraph two." in result.pages[0].text


def test_docx_extractor_rejects_corrupt_file() -> None:
    with pytest.raises(ValidationError):
        DocxExtractor().extract(b"not a real docx", filename="broken.docx")


def test_get_extractor_unknown_content_type_raises() -> None:
    with pytest.raises(ValidationError):
        get_extractor("application/x-nonsense")


@pytest.mark.parametrize(
    "content_type",
    [
        "text/plain",
        "text/markdown",
        "text/csv",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ],
)
def test_get_extractor_resolves_every_allowed_content_type(content_type: str) -> None:
    assert get_extractor(content_type) is not None
