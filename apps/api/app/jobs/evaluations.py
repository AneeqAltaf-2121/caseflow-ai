"""Evaluation run job (Phase 29): runs every example in a dataset through
a real RagService, scores it with Phase 27's deterministic checks and
Phase 28's LLM-as-a-judge graders, and — for examples with ground-truth
relevant_chunk_ids — Phase 26's retrieval metrics, persisting one
EvaluationResult per example.

Same retry/backoff and durable Job record pattern as report generation
(app/jobs/reports.py): any failure here is treated as transient and
retried, since there's no evaluation equivalent of "this file will never
parse" once the dataset itself has already loaded successfully at
creation time (app/services/evaluation_service.py). A failure to even
load the dataset (deleted from disk between creation and the job
running, say) is the one permanent failure this job recognizes.

`run_evaluation` is a plain async function so tests can call it directly
against a test session factory and injected providers, without a running
broker/worker — same split as `generate_report`/`generate_report_job`.
"""

import asyncio
import uuid

import dramatiq
import structlog
from caseflow_evals import EvaluationDataset, load_dataset
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.database import create_engine, create_session_factory
from app.evals.dataset_paths import DatasetNotFoundError, resolve_dataset_path
from app.evals.deterministic_checks import run_deterministic_checks
from app.evals.graders import (
    CitationSupportGrader,
    CompletenessGrader,
    FaithfulnessGrader,
    GradeResult,
    RelevanceGrader,
)
from app.evals.retrieval_evaluation import evaluate_retrieval
from app.integrations.embeddings import EmbeddingProvider, get_embedding_provider
from app.integrations.generation import GenerationProvider, get_generation_provider
from app.integrations.pricing import estimate_cost_usd
from app.models.model_run import ModelRunStatus
from app.rag.service import RagService
from app.repositories.chunk_repository import DocumentChunkRepository
from app.repositories.evaluation_repository import EvaluationRunRepository
from app.repositories.job_repository import JobRepository
from app.repositories.model_run_repository import ModelRunRepository
from app.repositories.project_repository import ProjectRepository
from app.retrieval.reranker import CrossEncoderReranker, Reranker
from app.services.hybrid_search_service import HybridSearchService
from app.services.project_service import ProjectService
from app.services.retrieval_service import RetrievalService

logger = structlog.get_logger("caseflow.jobs.evaluations")


def _grade_result_to_dict(result: GradeResult) -> dict:
    return {
        "grader": result.grader,
        "score": result.score,
        "reason": result.reason,
        "failures": result.failures,
        "judge_model": result.judge_model,
        "prompt_version": result.prompt_version,
        "temperature": result.temperature,
    }


async def run_evaluation(
    *,
    job_id: uuid.UUID,
    evaluation_run_id: uuid.UUID,
    session_factory: async_sessionmaker[AsyncSession],
    embedding_provider: EmbeddingProvider,
    reranker: Reranker,
    generation_provider: GenerationProvider,
    judge_provider: GenerationProvider,
) -> None:
    async with session_factory() as session:
        job_repo = JobRepository(session)
        run_repo = EvaluationRunRepository(session)

        job = await job_repo.get_by_id(job_id)
        if job is None:
            logger.warning("evaluation_job_missing", job_id=str(job_id))
            return

        run = await run_repo.get_by_id(evaluation_run_id)
        if run is None:
            await job_repo.record_failure(job, "Evaluation run no longer exists.")
            await job_repo.mark_failed(job)
            await session.commit()
            return

        # Dataset resolution failing here (deleted from disk after the run
        # was created) is permanent — retrying won't make the file
        # reappear — unlike every other failure in this job.
        try:
            dataset_path = resolve_dataset_path(run.dataset_name)
            dataset: EvaluationDataset = load_dataset(dataset_path)
        except DatasetNotFoundError as exc:
            await job_repo.record_failure(job, str(exc))
            await job_repo.mark_failed(job)
            await run_repo.mark_failed(run, str(exc))
            await session.commit()
            logger.error("evaluation_job_dataset_missing", job_id=str(job_id), error=str(exc))
            return

        await job_repo.mark_running(job)
        await run_repo.mark_running(run)
        await session.commit()

        chunk_repository = DocumentChunkRepository(session)
        hybrid_service = HybridSearchService(
            chunk_repository, ProjectService(ProjectRepository(session)), embedding_provider
        )
        retrieval_service = RetrievalService(hybrid_service, reranker)
        rag_service = RagService(retrieval_service, generation_provider)
        model_run_repository = ModelRunRepository(session)

        faithfulness_grader = FaithfulnessGrader(judge_provider)
        relevance_grader = RelevanceGrader(judge_provider)
        completeness_grader = CompletenessGrader(judge_provider)
        citation_support_grader = CitationSupportGrader(judge_provider)

        system_prompt = run.prompt_version.template if run.prompt_version else None

        try:
            # One retrieval-only pass over the whole dataset (Phase 26),
            # scored against ground-truth relevant_chunk_ids where present.
            # A second retrieval happens per-example inside
            # rag_service.answer_question() below — an accepted duplicate
            # retrieval cost in exchange for reusing both already-tested
            # functions unchanged rather than threading a shared result
            # through RagService's API. Fine for offline batch evaluation.
            retrieval_result = await evaluate_retrieval(
                retrieval_service=retrieval_service,
                dataset=dataset,
                project_id=run.project_id,
                user_id=run.created_by,
            )
            retrieval_by_example = {r.example_id: r for r in retrieval_result.example_results}

            # Idempotent under retry: drop any results a previous,
            # partially failed attempt already wrote.
            await run_repo.clear_results(run)

            for example in dataset.examples:
                answer = await rag_service.answer_question(
                    project_id=run.project_id,
                    user_id=run.created_by,
                    query=example.question,
                    system_prompt=system_prompt,
                )

                deterministic = await run_deterministic_checks(
                    answer=answer,
                    project_id=run.project_id,
                    chunk_repository=chunk_repository,
                )
                faithfulness = await faithfulness_grader.grade(
                    question=example.question, answer=answer
                )
                relevance = await relevance_grader.grade(question=example.question, answer=answer)
                completeness = None
                if example.expected_answer:
                    completeness = await completeness_grader.grade(
                        question=example.question,
                        answer=answer,
                        expected_answer=example.expected_answer,
                    )
                citation_support = await citation_support_grader.grade(
                    question=example.question, answer=answer
                )

                cost_usd = estimate_cost_usd(
                    model=answer.model,
                    input_tokens=answer.input_tokens,
                    output_tokens=answer.output_tokens,
                )
                model_run_id = None
                if answer.model != "none":
                    model_run = await model_run_repository.create(
                        provider=answer.provider,
                        model=answer.model,
                        prompt_version_id=run.prompt_version_id,
                        temperature=answer.temperature,
                        latency_ms=answer.latency_ms,
                        input_tokens=answer.input_tokens,
                        output_tokens=answer.output_tokens,
                        estimated_cost_usd=cost_usd,
                        status=ModelRunStatus.SUCCEEDED,
                        retrieval_config=answer.retrieval_config,
                    )
                    model_run_id = model_run.id

                retrieval_scores = retrieval_by_example.get(example.id)

                await run_repo.add_result(
                    evaluation_run_id=run.id,
                    example_id=example.id,
                    question=example.question,
                    generated_answer=answer.answer,
                    expected_answer=example.expected_answer,
                    faithfulness_score=faithfulness.score,
                    relevance_score=relevance.score,
                    completeness_score=completeness.score if completeness else None,
                    citation_support_score=citation_support.score,
                    citation_correct=deterministic.passed,
                    judge_reason=faithfulness.reason,
                    recall_at_k=retrieval_scores.recall_at_k if retrieval_scores else None,
                    precision_at_k=retrieval_scores.precision_at_k if retrieval_scores else None,
                    mrr=retrieval_scores.reciprocal_rank if retrieval_scores else None,
                    ndcg_at_k=retrieval_scores.ndcg_at_k if retrieval_scores else None,
                    latency_ms=answer.latency_ms,
                    cost_usd=cost_usd,
                    model_run_id=model_run_id,
                    grader_details={
                        "faithfulness": _grade_result_to_dict(faithfulness),
                        "relevance": _grade_result_to_dict(relevance),
                        "completeness": (
                            _grade_result_to_dict(completeness) if completeness else None
                        ),
                        "citation_support": _grade_result_to_dict(citation_support),
                        "deterministic_failures": deterministic.failures,
                    },
                )
        except Exception as exc:  # noqa: BLE001 - any failure here is treated as transient
            await job_repo.record_failure(job, str(exc))
            exhausted = job.attempt >= job.max_attempts
            if exhausted:
                await job_repo.mark_failed(job)
                await run_repo.mark_failed(run, str(exc))
            await session.commit()
            if exhausted:
                logger.error(
                    "evaluation_job_failed_permanently",
                    job_id=str(job_id),
                    evaluation_run_id=str(evaluation_run_id),
                    error=str(exc),
                )
                return
            logger.warning(
                "evaluation_job_attempt_failed",
                job_id=str(job_id),
                evaluation_run_id=str(evaluation_run_id),
                attempt=job.attempt,
                max_attempts=job.max_attempts,
                error=str(exc),
            )
            raise  # let Dramatiq's Retries middleware redeliver with backoff

        await run_repo.mark_succeeded(run)
        await job_repo.mark_succeeded(job)
        await session.commit()
        logger.info(
            "evaluation_job_succeeded",
            job_id=str(job_id),
            evaluation_run_id=str(evaluation_run_id),
            example_count=len(dataset.examples),
        )


@dramatiq.actor(max_retries=3, min_backoff=2_000, max_backoff=60_000, queue_name="evaluations")
def run_evaluation_job(job_id: str, evaluation_run_id: str) -> None:
    """The actual Dramatiq entrypoint — not exercised in CI (needs a real
    Postgres + Redis + LLM provider), kept intentionally thin so all the
    logic worth testing lives in `run_evaluation` above. The judge and the
    answering model are the same configured GenerationProvider — nothing
    stops passing a different one as `judge_provider` for a stronger
    judge, but that's a Phase 31+ concern."""
    settings = get_settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    embedding_provider = get_embedding_provider(settings)
    generation_provider = get_generation_provider(settings)
    reranker = CrossEncoderReranker()
    try:
        asyncio.run(
            run_evaluation(
                job_id=uuid.UUID(job_id),
                evaluation_run_id=uuid.UUID(evaluation_run_id),
                session_factory=session_factory,
                embedding_provider=embedding_provider,
                reranker=reranker,
                generation_provider=generation_provider,
                judge_provider=generation_provider,
            )
        )
    finally:
        asyncio.run(engine.dispose())
