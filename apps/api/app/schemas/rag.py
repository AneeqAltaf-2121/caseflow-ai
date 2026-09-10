import uuid

from pydantic import BaseModel, Field


class AskQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=6, ge=1, le=20)


class CitationRead(BaseModel):
    source_number: int
    document_id: uuid.UUID
    document_chunk_id: uuid.UUID
    document_filename: str
    page_number: int
    quote: str


class AskAnswerRead(BaseModel):
    answer: str
    citations: list[CitationRead]
    sources_considered: int
    model: str
