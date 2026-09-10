"""Token-aware chunking (Phase 10).

Document -> pages (app/ingestion/models.py) -> paragraphs -> token-aware
chunks. Chunks never span a page boundary (so a citation's page number is
always unambiguous) and never split a paragraph unless that single
paragraph alone exceeds the token budget. Consecutive chunks within a page
overlap by up to `overlap_tokens` of trailing paragraphs, so a passage
sitting near a chunk boundary is still fully retrievable from whichever
chunk a retriever ranks higher.
"""

import re
import uuid
from dataclasses import dataclass

from app.ingestion.models import ExtractedDocument, ExtractedPage

_WORD_PATTERN = re.compile(r"\S+")

DEFAULT_MAX_TOKENS = 400
DEFAULT_OVERLAP_TOKENS = 50


def count_tokens(text: str) -> int:
    """Approximate, deterministic, dependency-free token count
    (whitespace-delimited words), used purely for chunk-size budgeting.
    This is not the tokenizer any specific LLM/embedding provider uses —
    swap it out behind this same signature if exact provider-token parity
    is ever needed; nothing else in this module depends on the exact
    counting scheme, only that it's consistent with itself.
    """
    return len(_WORD_PATTERN.findall(text))


@dataclass(frozen=True)
class Chunk:
    id: str
    page_number: int
    text: str
    token_count: int
    start_offset: int
    end_offset: int


def _paragraph_spans(text: str) -> list[tuple[int, int, str]]:
    """Split on blank lines into (start, end, text) spans with offsets into
    `text` itself, skipping empty paragraphs. Offsets are found by
    searching forward from the previous match end, so repeated paragraph
    text resolves to its actual (not first) occurrence."""
    spans = []
    cursor = 0
    for part in text.split("\n\n"):
        start = text.index(part, cursor)
        end = start + len(part)
        if part.strip():
            spans.append((start, end, part))
        cursor = end
    return spans


def _split_long_paragraph(
    text: str, *, page_number: int, base_offset: int, max_tokens: int, overlap_tokens: int
) -> list[Chunk]:
    """Fallback for a single paragraph that alone exceeds max_tokens: slide
    a word-count window across it. Offsets come from regex match spans
    (not string search), so they're exact even when the paragraph contains
    internal newlines or repeated words."""
    words = list(_WORD_PATTERN.finditer(text))
    pieces: list[Chunk] = []
    step = max(max_tokens - overlap_tokens, 1)
    index = 0
    while index < len(words):
        window = words[index : index + max_tokens]
        start = base_offset + window[0].start()
        end = base_offset + window[-1].end()
        piece_text = text[window[0].start() : window[-1].end()]
        pieces.append(
            Chunk(
                id=str(uuid.uuid4()),
                page_number=page_number,
                text=piece_text,
                token_count=len(window),
                start_offset=start,
                end_offset=end,
            )
        )
        if index + max_tokens >= len(words):
            break
        index += step
    return pieces


def chunk_page(
    page: ExtractedPage,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[Chunk]:
    spans = _paragraph_spans(page.text)
    chunks: list[Chunk] = []

    # Paragraphs accumulated for the chunk currently being built.
    current: list[tuple[int, int, str, int]] = []
    current_tokens = 0

    def flush() -> None:
        if not current:
            return
        start, end = current[0][0], current[-1][1]
        text = page.text[start:end]
        chunks.append(
            Chunk(
                id=str(uuid.uuid4()),
                page_number=page.page_number,
                text=text,
                token_count=count_tokens(text),
                start_offset=start,
                end_offset=end,
            )
        )

    def carry_overlap() -> list[tuple[int, int, str, int]]:
        """Seed the next chunk with trailing paragraphs from the one just
        flushed, up to overlap_tokens worth."""
        overlap: list[tuple[int, int, str, int]] = []
        tokens = 0
        for item in reversed(current):
            if overlap and tokens + item[3] > overlap_tokens:
                break
            overlap.insert(0, item)
            tokens += item[3]
        return overlap

    for start, end, text in spans:
        tokens = count_tokens(text)

        if tokens > max_tokens:
            # This single paragraph alone busts the budget: flush whatever
            # was pending (no overlap carried across a fallback split —
            # the paragraph itself already provides internal overlap),
            # emit it as its own bounded sub-chunks, and continue clean.
            flush()
            current, current_tokens = [], 0
            chunks.extend(
                _split_long_paragraph(
                    text,
                    page_number=page.page_number,
                    base_offset=start,
                    max_tokens=max_tokens,
                    overlap_tokens=overlap_tokens,
                )
            )
            continue

        if current and current_tokens + tokens > max_tokens:
            flush()
            current = carry_overlap()
            current_tokens = sum(item[3] for item in current)

        current.append((start, end, text, tokens))
        current_tokens += tokens

    flush()
    return chunks


def chunk_document(
    document: ExtractedDocument,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[Chunk]:
    """Chunk every page independently — see module docstring for why
    chunks never span a page boundary."""
    chunks: list[Chunk] = []
    for page in document.pages:
        chunks.extend(chunk_page(page, max_tokens=max_tokens, overlap_tokens=overlap_tokens))
    return chunks
