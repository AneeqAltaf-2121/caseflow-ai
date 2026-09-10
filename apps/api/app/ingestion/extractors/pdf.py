import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.errors import ValidationError
from app.ingestion.models import ExtractedDocument, ExtractedPage


class PdfExtractor:
    """One ExtractedPage per PDF page, 1-indexed to match how a human
    (and therefore a citation) refers to "page 3" of the source file."""

    def extract(self, data: bytes, *, filename: str) -> ExtractedDocument:
        try:
            reader = PdfReader(io.BytesIO(data))
            pages = [
                ExtractedPage(page_number=index + 1, text=page.extract_text() or "")
                for index, page in enumerate(reader.pages)
            ]
        except PdfReadError as exc:
            raise ValidationError(f"Could not read PDF {filename!r}: {exc}") from exc
        return ExtractedDocument(source_filename=filename, pages=pages)
