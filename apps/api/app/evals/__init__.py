"""API-side hooks into the evaluation framework in packages/evals
(installed separately — see the root README's backend setup: `pip install
-e packages/evals[dev]` alongside apps/api's own install).

Dataset format (Phase 25) and retrieval metrics (Phase 26) re-exported
here for convenience. `retrieval_evaluation.evaluate_retrieval` (Phase
26) and `deterministic_checks.run_deterministic_checks` (Phase 27) live
in this package rather than packages/evals because both need a live
DB session for a real project. LLM-as-a-judge answer graders and
evaluation-run persistence/orchestration land in later phases (28-29),
at which point this package grows routes/services/repositories the same
as every other app/ subpackage.
"""

from caseflow_evals import (
    DatasetValidationError,
    EvaluationDataset,
    EvaluationExample,
    load_dataset,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    save_dataset,
)

from app.evals.deterministic_checks import (
    CitationCheckResult,
    DeterministicCheckResult,
    run_deterministic_checks,
)
from app.evals.retrieval_evaluation import (
    RetrievalEvaluationResult,
    RetrievalExampleResult,
    evaluate_retrieval,
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
    "RetrievalEvaluationResult",
    "RetrievalExampleResult",
    "evaluate_retrieval",
    "CitationCheckResult",
    "DeterministicCheckResult",
    "run_deterministic_checks",
]
