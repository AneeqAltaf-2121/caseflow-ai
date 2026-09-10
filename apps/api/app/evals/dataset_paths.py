"""Resolves an evaluation dataset name (Phase 29) to a file on disk.

Datasets live in packages/evals/datasets as `<name>.json` (see Phase 25's
dataset format and packages/evals/datasets/sample_contract_qa.json).
Resolving strictly by name — never accepting a raw path from an API
request — is what keeps this safe: a client can only ever ask for a file
already inside the datasets directory, never traverse out of it.
"""

from pathlib import Path

DEFAULT_DATASETS_DIR = Path(__file__).resolve().parents[4] / "packages" / "evals" / "datasets"


class DatasetNotFoundError(ValueError):
    pass


def resolve_dataset_path(dataset_name: str, *, datasets_dir: Path = DEFAULT_DATASETS_DIR) -> Path:
    if not dataset_name or any(sep in dataset_name for sep in ("/", "\\")):
        raise DatasetNotFoundError(f"Invalid dataset name: {dataset_name!r}")

    datasets_dir_resolved = datasets_dir.resolve()
    candidate = (datasets_dir_resolved / f"{dataset_name}.json").resolve()
    if datasets_dir_resolved not in candidate.parents:
        raise DatasetNotFoundError(f"Invalid dataset name: {dataset_name!r}")
    if not candidate.is_file():
        raise DatasetNotFoundError(f"Dataset {dataset_name!r} not found.")
    return candidate
