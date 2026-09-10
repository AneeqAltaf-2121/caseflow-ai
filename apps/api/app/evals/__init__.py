"""API-side hooks into the evaluation framework in packages/evals
(installed separately — see the root README's backend setup: `pip install
-e packages/evals[dev]` alongside apps/api's own install).

Dataset format (Phase 25) re-exported here for convenience; deterministic
+ LLM-as-a-judge graders and evaluation-run persistence/orchestration
land in later phases (26-29), at which point this package grows routes/
services/repositories the same as every other app/ subpackage.
"""

from caseflow_evals import (
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
