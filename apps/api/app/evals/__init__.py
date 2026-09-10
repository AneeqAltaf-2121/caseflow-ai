"""API-side hooks into the evaluation framework in packages/evals
(installed separately — see the root README's backend setup: `pip install
-e packages/evals[dev]` alongside apps/api's own install).

Dataset format (Phase 25) and retrieval metrics (Phase 26) re-exported
here for convenience. `retrieval_evaluation.evaluate_retrieval` (Phase
26), `deterministic_checks.run_deterministic_checks` (Phase 27), and
`graders` (Phase 28, LLM-as-a-judge) live in this package rather than
packages/evals because they need a live DB session and/or apps/api's
GenerationProvider abstraction. Evaluation-run persistence/orchestration
tying all of this together lands in Phase 29, at which point this
package grows routes/services/repositories the same as every other
app/ subpackage.
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
from app.evals.graders import (
    CitationSupportGrader,
    CompletenessGrader,
    FaithfulnessGrader,
    GradeResult,
    RelevanceGrader,
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
    "GradeResult",
    "FaithfulnessGrader",
    "RelevanceGrader",
    "CompletenessGrader",
    "CitationSupportGrader",
]
