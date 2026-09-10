"""Citation-grounded question answering (Phase 19): retrieve -> build
context -> generate -> extract + validate citations.

Stateless for now — nothing here persists a Conversation/Message/Citation
row (those tables/wiring are Phase 21). This is the core RAG mechanism
Phase 21's persistent-conversation endpoints call and store the result of.
"""

import uuid
from dataclasses import dataclass

from app.integrations.generation import GenerationProvider
from app.rag.citations import extract_cited_source_numbers
from app.rag.context_builder import build_context
from app.rag.prompts import SYSTEM_PROMPT, build_user_prompt
from app.services.retrieval_service import RetrievalService

DEFAULT_TOP_K = 6


@dataclass(frozen=True)
class Citation:
    source_number: int
    document_id: uuid.UUID
    document_chunk_id: uuid.UUID
    document_filename: str
    page_number: int
    quote: str


@dataclass(frozen=True)
class RagAnswer:
    answer: str
    citations: list[Citation]
    sources_considered: int
    model: str


class RagService:
    def __init__(
        self, retrieval_service: RetrievalService, generation_provider: GenerationProvider
    ) -> None:
        self._retrieval_service = retrieval_service
        self._generation_provider = generation_provider

    async def answer_question(
        self,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        query: str,
        top_k: int = DEFAULT_TOP_K,
    ) -> RagAnswer:
        results = await self._retrieval_service.retrieve(
            project_id=project_id, user_id=user_id, query=query, top_k=top_k
        )
        chunks = [result.chunk for result in results]

        context = build_context(chunks)
        generation = await self._generation_provider.generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_user_prompt(question=query, context=context),
        )

        cited_numbers = extract_cited_source_numbers(generation.text, source_count=len(chunks))
        citations = [
            Citation(
                source_number=n,
                document_id=chunks[n - 1].document_id,
                document_chunk_id=chunks[n - 1].id,
                document_filename=chunks[n - 1].document.filename,
                page_number=chunks[n - 1].page_number,
                quote=chunks[n - 1].text,
            )
            for n in cited_numbers
        ]

        return RagAnswer(
            answer=generation.text,
            citations=citations,
            sources_considered=len(chunks),
            model=generation.model,
        )
