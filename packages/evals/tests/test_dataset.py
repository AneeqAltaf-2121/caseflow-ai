from pathlib import Path

import pytest
from pydantic import ValidationError

from caseflow_evals import DatasetValidationError, EvaluationDataset, EvaluationExample
from caseflow_evals.dataset import load_dataset, save_dataset, validate_dataset

SAMPLE_DATASET_PATH = Path(__file__).resolve().parents[1] / "datasets" / "sample_contract_qa.json"


def _dataset(**overrides) -> EvaluationDataset:
    defaults = {
        "name": "test_dataset",
        "version": 1,
        "examples": [EvaluationExample(id="ex-1", question="What is the term?")],
    }
    defaults.update(overrides)
    return EvaluationDataset(**defaults)


def test_sample_dataset_loads_and_validates() -> None:
    dataset = load_dataset(SAMPLE_DATASET_PATH)
    assert dataset.name == "sample_contract_qa"
    assert dataset.version == 1
    assert len(dataset.examples) == 3
    assert dataset.examples[0].id == "ex-001"
    assert dataset.examples[0].expected_answer is not None


def test_example_defaults_relevant_chunk_ids_to_empty_list() -> None:
    example = EvaluationExample(id="ex-1", question="What is the term?")
    assert example.relevant_chunk_ids == []
    assert example.expected_answer is None


def test_dataset_requires_at_least_one_example() -> None:
    with pytest.raises(ValidationError):
        EvaluationDataset(name="empty", version=1, examples=[])


def test_dataset_rejects_version_below_one() -> None:
    with pytest.raises(ValidationError):
        _dataset(version=0)


def test_validate_dataset_rejects_duplicate_example_ids() -> None:
    dataset = _dataset(
        examples=[
            EvaluationExample(id="dup", question="Q1"),
            EvaluationExample(id="dup", question="Q2"),
        ]
    )
    with pytest.raises(DatasetValidationError):
        validate_dataset(dataset)


def test_load_dataset_rejects_duplicate_example_ids(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(
        '{"name": "bad", "version": 1, "examples": '
        '[{"id": "x", "question": "a"}, {"id": "x", "question": "b"}]}',
        encoding="utf-8",
    )
    with pytest.raises(DatasetValidationError):
        load_dataset(path)


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    original = _dataset(
        description="round trip test",
        examples=[
            EvaluationExample(
                id="ex-1",
                question="What is the term?",
                expected_answer="90 days",
                relevant_chunk_ids=["chunk-a", "chunk-b"],
            )
        ],
    )
    path = tmp_path / "roundtrip.json"

    save_dataset(original, path)
    reloaded = load_dataset(path)

    assert reloaded == original


def test_save_dataset_rejects_duplicate_ids_before_writing(tmp_path: Path) -> None:
    dataset = _dataset(
        examples=[
            EvaluationExample(id="dup", question="Q1"),
            EvaluationExample(id="dup", question="Q2"),
        ]
    )
    path = tmp_path / "should_not_exist.json"

    with pytest.raises(DatasetValidationError):
        save_dataset(dataset, path)
    assert not path.exists()
