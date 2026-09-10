"""CaseFlow AI's evaluation framework: reproducible dataset format now
(Phase 25), deterministic + LLM-as-a-judge graders and evaluation-run
orchestration in later phases (26-29). Deliberately a separate installable
package from apps/api — usable standalone (a notebook, a CI regression
script, a one-off analysis) without pulling in the whole FastAPI app.
"""

from caseflow_evals.dataset import (
    DatasetValidationError,
    EvaluationDataset,
    EvaluationExample,
    load_dataset,
    save_dataset,
)

__all__ = [
    "DatasetValidationError",
    "EvaluationDataset",
    "EvaluationExample",
    "load_dataset",
    "save_dataset",
]
