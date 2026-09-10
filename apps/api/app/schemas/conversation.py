import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.conversation import MessageRole


class ConversationCreate(BaseModel):
    title: str = Field(default="Untitled", max_length=300)


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=300)


class ConversationRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class CitationRead(BaseModel):
    id: uuid.UUID
    source_number: int
    document_id: uuid.UUID
    document_chunk_id: uuid.UUID
    document_filename: str
    page_number: int
    quote: str


class MessageRead(BaseModel):
    id: uuid.UUID
    role: MessageRole
    content: str
    created_at: datetime
    citations: list[CitationRead] = Field(default_factory=list)


class ConversationDetailRead(ConversationRead):
    messages: list[MessageRead]


class PostMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=6, ge=1, le=20)


class PostMessageResponse(BaseModel):
    user_message: MessageRead
    assistant_message: MessageRead
    insufficient_evidence: bool
    sources_considered: int
    model: str
