"""Confirms app.evals re-exports packages/evals cleanly — this is the one
place apps/api touches that package (see app/evals/__init__.py)."""

from pathlib import Path

from app.evals import EvaluationDataset, EvaluationExample, load_dataset


def test_bridge_reexports_dataset_types() -> None:
    example = EvaluationExample(id="ex-1", question="What is the term?")
    dataset = EvaluationDataset(name="bridge_test", version=1, examples=[example])
    assert dataset.examples[0].question == "What is the term?"


def test_bridge_can_load_the_sample_dataset() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    sample_path = repo_root / "packages" / "evals" / "datasets" / "sample_contract_qa.json"
    dataset = load_dataset(sample_path)
    assert dataset.name == "sample_contract_qa"
    assert len(dataset.examples) == 3
