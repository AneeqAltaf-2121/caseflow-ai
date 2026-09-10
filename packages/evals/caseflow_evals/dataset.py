"""Evaluation dataset format (Phase 25).

A dataset is a named, versioned, immutable JSON file — a reproducible
snapshot referenced by name+version (matching EvaluationRun.dataset_name,
see docs/domain-model.md), not a live foreign key, so a past evaluation
run stays meaningful even after the dataset it used is later edited: an
edit is a new version, never a mutation in place (mirrors PromptVersion's
immutability, Phase 22).
"""

import json
from pathlib import Path

from pydantic import BaseModel, Field


class DatasetValidationError(ValueError):
    """Raised for a dataset that's structurally valid JSON/schema but
    violates a reproducibility invariant (currently: duplicate example
    ids). Kept distinct from pydantic.ValidationError (which covers
    schema-shape problems) so callers can catch dataset-specific
    integrity issues without depending on pydantic's exception type.
    """


class EvaluationExample(BaseModel):
    """One question a project's documents should be able to answer,
    graded later (Phase 27-28) by comparing a generated answer against
    `expected_answer` and the chunks it actually cited against
    `relevant_chunk_ids`.
    """

    id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1)
    expected_answer: str | None = None
    relevant_chunk_ids: list[str] = Field(default_factory=list)


class EvaluationDataset(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    version: int = Field(ge=1)
    description: str | None = None
    examples: list[EvaluationExample] = Field(min_length=1)


def validate_dataset(dataset: EvaluationDataset) -> None:
    """Integrity checks beyond per-field schema validation. Called
    automatically by load_dataset(); call directly too for a dataset
    built in memory rather than loaded from a file."""
    ids = [example.id for example in dataset.examples]
    if len(ids) != len(set(ids)):
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        raise DatasetValidationError(
            f"Duplicate example id(s) in dataset {dataset.name!r} v{dataset.version}: {duplicates}"
        )


def load_dataset(path: str | Path) -> EvaluationDataset:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    dataset = EvaluationDataset.model_validate(data)
    validate_dataset(dataset)
    return dataset


def save_dataset(dataset: EvaluationDataset, path: str | Path) -> None:
    """Pretty-printed (indent=2) so a dataset diffs cleanly in version
    control — datasets are meant to be checked in and reviewed like code."""
    validate_dataset(dataset)
    Path(path).write_text(dataset.model_dump_json(indent=2) + "\n", encoding="utf-8")
