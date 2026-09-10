import pytest
from caseflow_evals import EvaluationDataset, EvaluationExample
from sqlalchemy.ext.asyncio import AsyncSession

from app.evals.retrieval_evaluation import evaluate_retrieval
from app.integrations.embeddings import LocalEmbeddingProvider
from app.models.chunk import DocumentChunk
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


async def _seed_project_with_chunks(db_session: AsyncSession):
    owner = await UserRepository(db_session).create(
        email="retrieval-eval@x.com", display_name="Eval"
    )
    org = await OrganizationRepository(db_session).create(name="Co", slug="co-retrieval-eval")
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
    texts = [
        "This agreement terminates after 90 days notice.",
        "The governing law of this contract is the State of Delaware.",
    ]
    embeddings = await embedder.embed(texts)
    chunks = [
        DocumentChunk(
            document_id=document.id,
            document_version_id=document.versions[0].id,
            page_number=1,
            section=None,
            text=text,
            token_count=7,
            start_offset=index,
            end_offset=index + len(text),
            embedding=embedding,
            chunk_metadata={},
        )
        for index, (text, embedding) in enumerate(zip(texts, embeddings, strict=True))
    ]
    await DocumentChunkRepository(db_session).bulk_create(chunks)
    await db_session.commit()

    stored_chunks = await DocumentChunkRepository(db_session).list_for_document(document.id)
    termination_chunk = next(c for c in stored_chunks if "terminates" in c.text)
    governing_law_chunk = next(c for c in stored_chunks if "governing law" in c.text)
    return owner, project, embedder, termination_chunk, governing_law_chunk


def _build_retrieval_service(db_session: AsyncSession, embedder) -> RetrievalService:
    hybrid_service = HybridSearchService(
        DocumentChunkRepository(db_session), ProjectService(ProjectRepository(db_session)), embedder
    )
    return RetrievalService(hybrid_service, MockReranker())


async def test_evaluate_retrieval_scores_examples_with_ground_truth(
    db_session: AsyncSession,
) -> None:
    owner, project, embedder, termination_chunk, _ = await _seed_project_with_chunks(db_session)
    retrieval_service = _build_retrieval_service(db_session, embedder)
    dataset = EvaluationDataset(
        name="retrieval_eval_test",
        version=1,
        examples=[
            EvaluationExample(
                id="ex-1",
                question="agreement terminates notice",
                relevant_chunk_ids=[str(termination_chunk.id)],
            )
        ],
    )

    result = await evaluate_retrieval(
        retrieval_service=retrieval_service,
        dataset=dataset,
        project_id=project.id,
        user_id=owner.id,
        k=5,
    )

    assert result.dataset_name == "retrieval_eval_test"
    assert result.dataset_version == 1
    assert result.k == 5
    assert result.skipped_example_ids == []
    assert len(result.example_results) == 1
    assert result.example_results[0].example_id == "ex-1"
    assert result.mean_recall_at_k == 1.0
    assert result.mean_reciprocal_rank == 1.0
    assert result.mean_ndcg_at_k == 1.0
    assert "retriever_version" in result.retriever_config


async def test_evaluate_retrieval_skips_examples_without_ground_truth(
    db_session: AsyncSession,
) -> None:
    owner, project, embedder, _, _ = await _seed_project_with_chunks(db_session)
    retrieval_service = _build_retrieval_service(db_session, embedder)
    dataset = EvaluationDataset(
        name="retrieval_eval_test",
        version=1,
        examples=[EvaluationExample(id="no-ground-truth", question="anything")],
    )

    result = await evaluate_retrieval(
        retrieval_service=retrieval_service,
        dataset=dataset,
        project_id=project.id,
        user_id=owner.id,
    )

    assert result.example_results == []
    assert result.skipped_example_ids == ["no-ground-truth"]
    # Mean of an empty list is reported as 0.0, not NaN/error.
    assert result.mean_recall_at_k == 0.0


async def test_evaluate_retrieval_low_score_when_relevant_chunk_never_retrieved(
    db_session: AsyncSession,
) -> None:
    owner, project, embedder, _, _ = await _seed_project_with_chunks(db_session)
    retrieval_service = _build_retrieval_service(db_session, embedder)
    dataset = EvaluationDataset(
        name="retrieval_eval_test",
        version=1,
        examples=[
            EvaluationExample(
                id="ex-miss",
                question="agreement terminates notice",
                relevant_chunk_ids=["00000000-0000-0000-0000-000000000000"],
            )
        ],
    )

    result = await evaluate_retrieval(
        retrieval_service=retrieval_service,
        dataset=dataset,
        project_id=project.id,
        user_id=owner.id,
    )

    assert result.mean_recall_at_k == 0.0
    assert result.mean_reciprocal_rank == 0.0
