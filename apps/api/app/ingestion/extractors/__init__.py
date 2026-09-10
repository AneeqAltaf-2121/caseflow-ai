from app.errors import ValidationError
from app.ingestion.extractors.base import Extractor
from app.ingestion.extractors.docx import DocxExtractor
from app.ingestion.extractors.pdf import PdfExtractor
from app.ingestion.extractors.text import PlainTextExtractor

# Kept in sync with DocumentService.ALLOWED_CONTENT_TYPES — every allowed
# upload content type must have an extractor here, and vice versa.
_EXTRACTORS: dict[str, Extractor] = {
    "text/plain": PlainTextExtractor(),
    "text/markdown": PlainTextExtractor(),
    "text/csv": PlainTextExtractor(),
    "application/pdf": PdfExtractor(),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DocxExtractor(),
}


def get_extractor(content_type: str) -> Extractor:
    extractor = _EXTRACTORS.get(content_type)
    if extractor is None:
        raise ValidationError(f"No extractor registered for content type {content_type!r}.")
    return extractor


__all__ = ["Extractor", "get_extractor"]
