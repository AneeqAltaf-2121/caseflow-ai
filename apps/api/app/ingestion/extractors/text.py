from app.ingestion.models import ExtractedDocument, ExtractedPage


class PlainTextExtractor:
    """text/plain, text/markdown, text/csv — decoded as UTF-8, replacing
    (rather than raising on) any byte that isn't valid UTF-8, since a
    user's file being mis-encoded shouldn't hard-fail ingestion."""

    def extract(self, data: bytes, *, filename: str) -> ExtractedDocument:
        text = data.decode("utf-8", errors="replace")
        return ExtractedDocument(
            source_filename=filename, pages=[ExtractedPage(page_number=1, text=text)]
        )
