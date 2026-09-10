import pytest

from app.evals.dataset_paths import DatasetNotFoundError, resolve_dataset_path


def test_resolve_dataset_path_finds_the_sample_dataset() -> None:
    path = resolve_dataset_path("sample_contract_qa")
    assert path.is_file()
    assert path.name == "sample_contract_qa.json"


def test_resolve_dataset_path_missing_dataset_raises() -> None:
    with pytest.raises(DatasetNotFoundError):
        resolve_dataset_path("this_dataset_does_not_exist")


@pytest.mark.parametrize(
    "dataset_name",
    ["../secrets", "..\\secrets", "a/b", "a\\b", ""],
)
def test_resolve_dataset_path_rejects_path_traversal(dataset_name: str) -> None:
    with pytest.raises(DatasetNotFoundError):
        resolve_dataset_path(dataset_name)


def test_resolve_dataset_path_dotdot_without_separator_is_just_a_missing_file() -> None:
    # No "/" or "\" in the name, so it's not traversal — just a filename
    # ("...json") that happens not to exist inside the datasets directory.
    with pytest.raises(DatasetNotFoundError):
        resolve_dataset_path("..")
