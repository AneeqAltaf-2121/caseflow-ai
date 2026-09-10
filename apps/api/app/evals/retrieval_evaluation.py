"""Retrieval evaluation (Phase 26): runs an EvaluationDataset's questions
through a real, live RetrievalService and scores the ranked chunk ids
against each example's ground-truth `relevant_chunk_ids`, using
packages/evals's pure retrieval metrics.

Deliberately kept API-side (not in packages/evals) because it needs a
live RetrievalService/DB session for a real project; packages/evals
itself stays DB-free and installable standalone. Persisting these results
as an EvaluationRun (so runs are comparable over time, e.g. "Retriever v1
Recall@5: 0.78, Retriever v2 Recall@5: 0.91") lands in Phase 29.
"""

import uuid
from dataclasses import dataclass, field

from caseflow_evals import (
    EvaluationDataset,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

from app.services.retrieval_service import RetrievalService

DEFAULT_K = 5


@dataclass(frozen=True)
class RetrievalExampleResult:
    example_id: str
    recall_at_k: float
    precision_at_k: float
    reciprocal_rank: float
    ndcg_at_k: float


@dataclass(frozen=True)
class RetrievalEvaluationResult:
    dataset_name: str
    dataset_version: int
    k: int
    retriever_config: dict
    example_results: list[RetrievalExampleResult] = field(default_factory=list)
    skipped_example_ids: list[str] = field(default_factory=list)

    @property
    def mean_recall_at_k(self) -> float:
        return _mean([r.recall_at_k for r in self.example_results])

    @property
    def mean_precision_at_k(self) -> float:
        return _mean([r.precision_at_k for r in self.example_results])

    @property
    def mean_reciprocal_rank(self) -> float:
        return _mean([r.reciprocal_rank for r in self.example_results])

    @property
    def mean_ndcg_at_k(self) -> float:
        return _mean([r.ndcg_at_k for r in self.example_results])


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


async def evaluate_retrieval(
    *,
    retrieval_service: RetrievalService,
    dataset: EvaluationDataset,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    k: int = DEFAULT_K,
) -> RetrievalEvaluationResult:
    """Scores every dataset example that has ground-truth relevant chunk
    ids; examples with none are skipped (there's nothing to measure
    against) and reported separately so a caller can tell "scored 0" from
    "had no ground truth"."""
    example_results: list[RetrievalExampleResult] = []
    skipped_example_ids: list[str] = []

    for example in dataset.examples:
        if not example.relevant_chunk_ids:
            skipped_example_ids.append(example.id)
            continue

        results = await retrieval_service.retrieve(
            project_id=project_id, user_id=user_id, query=example.question, top_k=k
        )
        retrieved_ids = [str(result.chunk.id) for result in results]

        example_results.append(
            RetrievalExampleResult(
                example_id=example.id,
                recall_at_k=recall_at_k(retrieved_ids, example.relevant_chunk_ids, k),
                precision_at_k=precision_at_k(retrieved_ids, example.relevant_chunk_ids, k),
                reciprocal_rank=reciprocal_rank(retrieved_ids, example.relevant_chunk_ids),
                ndcg_at_k=ndcg_at_k(retrieved_ids, example.relevant_chunk_ids, k),
            )
        )

    return RetrievalEvaluationResult(
        dataset_name=dataset.name,
        dataset_version=dataset.version,
        k=k,
        retriever_config=retrieval_service.describe_config(),
        example_results=example_results,
        skipped_example_ids=skipped_example_ids,
    )
