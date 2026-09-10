"""Extraction output types.

Deliberately plain dataclasses, not ORM models: extraction runs before
chunking/embedding decide what's worth persisting (see app/ingestion/
docstring), so this package has no database dependency at all.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedPage:
    """One page's worth of extracted text.

    Plain-text/Markdown/CSV sources have no real pagination, so they
    extract as a single page numbered 1 — chunking (Phase 10) is what
    actually splits long single-page text, page number just anchors a
    citation back to *which page of the source file* a passage came from.
    """

    page_number: int
    text: str


@dataclass(frozen=True)
class ExtractedDocument:
    source_filename: str
    pages: list[ExtractedPage]

    @property
    def full_text(self) -> str:
        return "\n\n".join(page.text for page in self.pages)

    @property
    def page_count(self) -> int:
        return len(self.pages)
