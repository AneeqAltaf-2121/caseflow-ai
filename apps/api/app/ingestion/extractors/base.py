from typing import Protocol

from app.ingestion.models import ExtractedDocument


class Extractor(Protocol):
    """Turns raw file bytes into page-aware text. Implementations must not
    normalize (see app/ingestion/normalizer.py) — that's applied uniformly
    afterward by app/ingestion/pipeline.py, once, regardless of source."""

    def extract(self, data: bytes, *, filename: str) -> ExtractedDocument: ...
