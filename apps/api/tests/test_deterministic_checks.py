import dataclasses
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.evals.deterministic_checks import run_deterministic_checks
from app.integrations.embeddings import LocalEmbeddingProvider
from app.integrations.generation import MockGenerationProvider
from app.models.chunk import DocumentChunk
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
    owner = await UserRepository(db_session).create(
        email="deterministic-checks@x.com", display_name="Checker"
    )
    org = await OrganizationRepository(db_session).create(name="Co", slug="co-det-checks")
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


async def test_grounded_answer_with_valid_citation_passes_all_checks(
    db_session: AsyncSession,
) -> None:
    owner, project, embedder = await _seed_project_with_chunk(db_session)
    service = _build_rag_service(
        db_session, embedder, canned_response="The agreement terminates after 90 days [1]."
    )
    answer = await service.answer_question(
        project_id=project.id, user_id=owner.id, query="agreement terminates"
    )

    result = await run_deterministic_checks(
        answer=answer,
        project_id=project.id,
        chunk_repository=DocumentChunkRepository(db_session),
    )

    assert result.json_schema_valid is True
    assert result.has_required_citations is True
    assert result.within_latency_threshold is True
    assert len(result.citation_results) == 1
    assert result.citation_results[0].passed is True
    assert result.passed is True
    assert result.failures == []


async def test_zero_evidence_answer_is_not_penalized_for_missing_citations(
    db_session: AsyncSession,
) -> None:
    owner, project, embedder = await _seed_project_with_chunk(db_session)
    service = _build_rag_service(db_session, embedder, canned_response="No citation here.")
    answer = await service.answer_question(
        project_id=project.id, user_id=owner.id, query="something totally unrelated xyz"
    )

    result = await run_deterministic_checks(
        answer=answer,
        project_id=project.id,
        chunk_repository=DocumentChunkRepository(db_session),
    )

    assert answer.insufficient_evidence is True
    assert result.has_required_citations is True
    assert result.passed is True


async def test_answer_with_citation_pointing_to_another_project_fails(
    db_session: AsyncSession,
) -> None:
    owner, project, embedder = await _seed_project_with_chunk(db_session)
    # A second, unrelated project with its own chunk.
    other_org = await OrganizationRepository(db_session).create(name="Other", slug="co-other")
    other_project = await ProjectService(ProjectRepository(db_session)).create_project(
        organization_id=other_org.id, name="Other", description=None, created_by=owner.id
    )
    other_document = await DocumentRepository(db_session).create(
        project_id=other_project.id,
        filename="other.txt",
        content_type="text/plain",
        size_bytes=1,
        checksum_sha256="y",
        storage_key="other.txt",
        uploaded_by=owner.id,
    )
    await db_session.commit()
    other_document = await DocumentRepository(db_session).get_by_id(other_document.id)
    [other_embedding] = await embedder.embed(["Unrelated text."])
    other_chunks = await DocumentChunkRepository(db_session).bulk_create(
        [
            DocumentChunk(
                document_id=other_document.id,
                document_version_id=other_document.versions[0].id,
                page_number=1,
                section=None,
                text="Unrelated text.",
                token_count=2,
                start_offset=0,
                end_offset=15,
                embedding=other_embedding,
                chunk_metadata={},
            )
        ]
    )
    await db_session.commit()
    foreign_chunk_id = other_chunks[0].id

    service = _build_rag_service(
        db_session, embedder, canned_response="The agreement terminates after 90 days [1]."
    )
    answer = await service.answer_question(
        project_id=project.id, user_id=owner.id, query="agreement terminates"
    )
    # Tamper with the citation to point at a chunk from a different project,
    # simulating corrupted/mis-recorded stored data being re-evaluated.
    tampered_citation = dataclasses.replace(answer.citations[0], document_chunk_id=foreign_chunk_id)
    tampered = dataclasses.replace(answer, citations=[tampered_citation])

    result = await run_deterministic_checks(
        answer=tampered,
        project_id=project.id,
        chunk_repository=DocumentChunkRepository(db_session),
    )

    assert result.citation_results[0].references_real_chunk is True
    assert result.citation_results[0].belongs_to_project is False
    assert result.passed is False
    assert any("citation_belongs_to_project" in f for f in result.failures)


async def test_citation_referencing_nonexistent_chunk_fails(db_session: AsyncSession) -> None:
    owner, project, embedder = await _seed_project_with_chunk(db_session)
    service = _build_rag_service(
        db_session, embedder, canned_response="The agreement terminates after 90 days [1]."
    )
    answer = await service.answer_question(
        project_id=project.id, user_id=owner.id, query="agreement terminates"
    )
    tampered_citation = dataclasses.replace(answer.citations[0], document_chunk_id=uuid.uuid4())
    tampered = dataclasses.replace(answer, citations=[tampered_citation])

    result = await run_deterministic_checks(
        answer=tampered,
        project_id=project.id,
        chunk_repository=DocumentChunkRepository(db_session),
    )

    assert result.citation_results[0].references_real_chunk is False
    assert result.citation_results[0].belongs_to_project is False
    assert result.passed is False
    assert any("citation_references_real_chunk" in f for f in result.failures)


async def test_latency_threshold_can_be_exceeded(db_session: AsyncSession) -> None:
    owner, project, embedder = await _seed_project_with_chunk(db_session)
    service = _build_rag_service(
        db_session, embedder, canned_response="The agreement terminates after 90 days [1]."
    )
    answer = await service.answer_question(
        project_id=project.id, user_id=owner.id, query="agreement terminates"
    )

    result = await run_deterministic_checks(
        answer=answer,
        project_id=project.id,
        chunk_repository=DocumentChunkRepository(db_session),
        latency_threshold_ms=-1,
    )

    assert result.within_latency_threshold is False
    assert result.passed is False
    assert any("within_latency_threshold" in f for f in result.failures)
