from app.models.chunk import DocumentChunk


def build_context(chunks: list[DocumentChunk]) -> str:
    """Numbered source list matching the [n] markers the model is asked
    to cite (see prompts.py) — number `i` (1-indexed) is `chunks[i-1]`."""
    parts = [
        f"[{i}] (from {chunk.document.filename}, page {chunk.page_number})\n{chunk.text}"
        for i, chunk in enumerate(chunks, 1)
    ]
    return "\n\n".join(parts)
