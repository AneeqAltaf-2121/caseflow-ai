"""CaseFlow AI's evaluation framework: reproducible dataset format
(Phase 25), retrieval quality metrics (Phase 26), deterministic +
LLM-as-a-judge answer graders and evaluation-run orchestration in later
phases (27-29). Deliberately a separate installable package from
apps/api — usable standalone (a notebook, a CI regression script, a
one-off analysis) without pulling in the whole FastAPI app.
"""

from caseflow_evals.dataset import (
    DatasetValidationError,
    EvaluationDataset,
    EvaluationExample,
    load_dataset,
    save_dataset,
)
from caseflow_evals.retrieval_metrics import (
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

__all__ = [
    "DatasetValidationError",
    "EvaluationDataset",
    "EvaluationExample",
    "load_dataset",
    "save_dataset",
    "ndcg_at_k",
    "precision_at_k",
    "recall_at_k",
    "reciprocal_rank",
]
