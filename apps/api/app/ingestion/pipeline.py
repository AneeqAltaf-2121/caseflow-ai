from app.ingestion.extractors import get_extractor
from app.ingestion.models import ExtractedDocument, ExtractedPage
from app.ingestion.normalizer import normalize_text


def extract_document(*, content_type: str, data: bytes, filename: str) -> ExtractedDocument:
    """Extract + normalize. The one function app/jobs/ingestion.py calls —
    everything else in this package is an implementation detail behind it."""
    extractor = get_extractor(content_type)
    raw = extractor.extract(data, filename=filename)
    normalized_pages = [
        ExtractedPage(page_number=page.page_number, text=normalize_text(page.text))
        for page in raw.pages
    ]
    return ExtractedDocument(source_filename=raw.source_filename, pages=normalized_pages)
