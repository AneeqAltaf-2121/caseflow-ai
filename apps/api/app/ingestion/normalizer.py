"""Text normalization applied uniformly after extraction, regardless of
source format, so downstream chunking/embedding see consistent input.
"""

import re
import unicodedata

_BLANK_LINE_RUN = re.compile(r"\n{3,}")
_HORIZONTAL_WHITESPACE_RUN = re.compile(r"[ \t]+")


def normalize_text(text: str) -> str:
    """Unicode-normalize, unify line endings, and collapse redundant
    whitespace without collapsing paragraph breaks (a blank line is kept
    as one blank line — that boundary matters for chunking, Phase 10)."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _HORIZONTAL_WHITESPACE_RUN.sub(" ", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = _BLANK_LINE_RUN.sub("\n\n", text)
    return text.strip()
