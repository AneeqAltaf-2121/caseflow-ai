import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.embeddings import LocalEmbeddingProvider
from app.integrations.generation import MockGenerationProvider
from app.models.chunk import DocumentChunk
from app.rag.grounding import INSUFFICIENT_EVIDENCE_MESSAGE
from app.rag.service import RagService
from app.repositories.chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.retrieval.reranker import MockReranker
from app.services.hybrid_search_service import HybridSearchService
from app.services.project_service import ProjectService
from app.services.retrieval_service import RetrievalService

pytestmark = pytest.mark.asyncio


async def _seed_project_with_chunk(db_session: AsyncSession):
    owner = await UserRepository(db_session).create(email="rag@x.com", display_name="Rag")
    org = await OrganizationRepository(db_session).create(name="Co", slug="co")
    project = await ProjectService(ProjectRepository(db_session)).create_project(
        organization_id=org.id, name="Legal", description=None, created_by=owner.id
    )
    document_repository = DocumentRepository(db_session)
    document = await document_repository.create(
        project_id=project.id,
        filename="contract.txt",
        content_type="text/plain",
        size_bytes=1,
        checksum_sha256="x",
        storage_key="contract.txt",
        uploaded_by=owner.id,
    )
    await db_session.commit()
    document = await document_repository.get_by_id(document.id)

    embedder = LocalEmbeddingProvider(dimensions=64)
    text = "This agreement terminates after 90 days notice."
    [embedding] = await embedder.embed([text])
    await DocumentChunkRepository(db_session).bulk_create(
        [
            DocumentChunk(
                document_id=document.id,
                document_version_id=document.versions[0].id,
                page_number=1,
                section=None,
                text=text,
                token_count=7,
                start_offset=0,
                end_offset=len(text),
                embedding=embedding,
                chunk_metadata={},
            )
        ]
    )
    await db_session.commit()
    return owner, project, embedder


def _build_rag_service(db_session: AsyncSession, embedder, canned_response: str) -> RagService:
    hybrid_service = HybridSearchService(
        DocumentChunkRepository(db_session), ProjectService(ProjectRepository(db_session)), embedder
    )
    retrieval_service = RetrievalService(hybrid_service, MockReranker())
    return RagService(retrieval_service, MockGenerationProvider(canned_response=canned_response))


async def test_answer_question_returns_valid_citation(db_session: AsyncSession) -> None:
    owner, project, embedder = await _seed_project_with_chunk(db_session)
    service = _build_rag_service(
        db_session, embedder, canned_response="The agreement terminates after 90 days [1]."
    )

    answer = await service.answer_question(
        project_id=project.id, user_id=owner.id, query="agreement terminates"
    )

    assert answer.sources_considered == 1
    assert len(answer.citations) == 1
    assert answer.citations[0].source_number == 1
    assert answer.citations[0].document_filename == "contract.txt"
    assert answer.citations[0].page_number == 1
    assert answer.insufficient_evidence is False
    # Phase 23: everything ConversationService needs to record a ModelRun.
    assert answer.provider == "MockGenerationProvider"
    assert answer.input_tokens > 0
    assert answer.output_tokens > 0
    assert answer.latency_ms >= 0
    assert answer.temperature == 0.0
    assert answer.retrieval_config["top_k"] == 6
    assert answer.retrieval_config["retriever_version"] == "hybrid_rrf_v1"
    assert answer.retrieval_config["reranker"] == "MockReranker"
    assert answer.retrieval_config["embedding_provider"] == "LocalEmbeddingProvider"


async def test_answer_with_no_citations_in_model_output_is_flagged_insufficient(
    db_session: AsyncSession,
) -> None:
    owner, project, embedder = await _seed_project_with_chunk(db_session)
    service = _build_rag_service(db_session, embedder, canned_response="I don't know.")

    answer = await service.answer_question(
        project_id=project.id, user_id=owner.id, query="agreement terminates"
    )

    assert answer.citations == []
    assert answer.sources_considered == 1
    assert answer.insufficient_evidence is True
    # The model's real text is preserved — insufficient_evidence is a
    # warning flag, not a silent rewrite of what the model said.
    assert answer.answer == "I don't know."


async def test_answer_question_with_no_matching_documents(db_session: AsyncSession) -> None:
    owner = await UserRepository(db_session).create(email="empty@x.com", display_name="Empty")
    org = await OrganizationRepository(db_session).create(name="Empty", slug="empty")
    project = await ProjectService(ProjectRepository(db_session)).create_project(
        organization_id=org.id, name="Empty project", description=None, created_by=owner.id
    )
    await db_session.commit()

    hybrid_service = HybridSearchService(
        DocumentChunkRepository(db_session),
        ProjectService(ProjectRepository(db_session)),
        LocalEmbeddingProvider(dimensions=32),
    )
    retrieval_service = RetrievalService(hybrid_service, MockReranker())
    service = RagService(
        retrieval_service, MockGenerationProvider(canned_response="No evidence available.")
    )

    answer = await service.answer_question(
        project_id=project.id, user_id=owner.id, query="anything"
    )

    assert answer.sources_considered == 0
    assert answer.citations == []
    assert answer.insufficient_evidence is True
    # No chunks at all -> no generation call is made; the canned message
    # is returned directly rather than the mock's configured response.
    assert answer.answer == INSUFFICIENT_EVIDENCE_MESSAGE
    assert answer.model == "none"
    assert answer.provider == "none"
    assert answer.input_tokens == 0
    assert answer.output_tokens == 0
    assert answer.latency_ms == 0
    # Retrieval config is still recorded even when nothing was found —
    # useful for diagnosing why a query came up empty.
    assert answer.retrieval_config["top_k"] == 6
