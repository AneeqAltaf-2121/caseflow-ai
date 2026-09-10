"""Citation-grounded question answering (Phase 19): retrieve -> build
context -> generate -> extract + validate citations. Grounding
(Phase 20): refuse to guess when there's no evidence to answer from.

Doesn't persist anything itself — ConversationService (Phase 21) is what
calls this per turn and stores the result as Message/Citation rows,
passing in a bounded slice of prior turns as `history` (see
app/rag/history.py) so a long conversation doesn't grow every prompt
without bound.
"""

import uuid
from dataclasses import dataclass

from app.integrations.generation import GenerationProvider
from app.rag.citations import extract_cited_source_numbers
from app.rag.context_builder import build_context
from app.rag.grounding import INSUFFICIENT_EVIDENCE_MESSAGE
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
    # True when the answer shouldn't be trusted as evidence-backed: either
    # nothing was retrieved at all, or the model produced zero citations
    # despite having sources to work with (see app/rag/grounding.py for
    # why citation presence, not a similarity threshold, is the signal).
    # `answer` is still the model's real text in the latter case — this is
    # a warning flag for the caller/UI, not a silent rewrite of what the
    # model said.
    insufficient_evidence: bool


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
        history: str = "",
        system_prompt: str | None = None,
    ) -> RagAnswer:
        results = await self._retrieval_service.retrieve(
            project_id=project_id, user_id=user_id, query=query, top_k=top_k
        )
        chunks = [result.chunk for result in results]

        if not chunks:
            # Nothing to answer from — don't spend a generation call
            # producing a guess with no grounding at all.
            return RagAnswer(
                answer=INSUFFICIENT_EVIDENCE_MESSAGE,
                citations=[],
                sources_considered=0,
                model="none",
                insufficient_evidence=True,
            )

        context = build_context(chunks)
        generation = await self._generation_provider.generate(
            # A caller (ConversationService, Phase 22) may supply the
            # project's active PromptVersion.template here instead of the
            # hardcoded default — see app/services/prompt_version_service.py.
            system_prompt=system_prompt or SYSTEM_PROMPT,
            user_prompt=build_user_prompt(question=query, context=context, history=history),
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
            insufficient_evidence=len(citations) == 0,
        )
