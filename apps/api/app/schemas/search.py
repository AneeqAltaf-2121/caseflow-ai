import uuid

from pydantic import BaseModel, Field


class SearchQuery(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=10, ge=1, le=50)


class SearchResultRead(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_filename: str
    page_number: int
    text: str
    score: float


class HybridSearchResultRead(BaseModel):
    """Same shape as SearchResultRead plus the per-retriever diagnostics
    reciprocal rank fusion combined (see app/retrieval/fusion.py) — a rank/
    score is null when that retriever didn't surface this chunk at all."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_filename: str
    page_number: int
    text: str
    fused_score: float
    vector_rank: int | None
    vector_score: float | None
    keyword_rank: int | None
    keyword_score: float | None
