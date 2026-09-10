import math

from caseflow_evals.retrieval_metrics import (
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


def test_recall_at_k_counts_all_relevant_hits_within_k() -> None:
    retrieved = ["c1", "c2", "c3", "c4", "c5"]
    relevant = {"c2", "c4", "c9"}  # c9 never retrieved
    assert recall_at_k(retrieved, relevant, k=5) == 2 / 3


def test_recall_at_k_respects_k_cutoff() -> None:
    retrieved = ["c1", "c2", "c3"]
    relevant = {"c3"}
    assert recall_at_k(retrieved, relevant, k=2) == 0.0
    assert recall_at_k(retrieved, relevant, k=3) == 1.0


def test_recall_at_k_with_no_relevant_ids_is_zero_not_error() -> None:
    assert recall_at_k(["c1", "c2"], [], k=5) == 0.0


def test_precision_at_k_fraction_of_top_k_that_are_relevant() -> None:
    retrieved = ["c1", "c2", "c3", "c4"]
    relevant = {"c1", "c3"}
    assert precision_at_k(retrieved, relevant, k=4) == 0.5


def test_precision_at_k_with_fewer_results_than_k_uses_actual_count() -> None:
    retrieved = ["c1"]
    relevant = {"c1"}
    assert precision_at_k(retrieved, relevant, k=5) == 1.0


def test_precision_at_k_empty_retrieved_is_zero() -> None:
    assert precision_at_k([], {"c1"}, k=5) == 0.0


def test_reciprocal_rank_first_relevant_position() -> None:
    retrieved = ["c1", "c2", "c3"]
    assert reciprocal_rank(retrieved, {"c2"}) == 0.5
    assert reciprocal_rank(retrieved, {"c1"}) == 1.0
    assert reciprocal_rank(retrieved, {"c3"}) == 1 / 3


def test_reciprocal_rank_no_hit_is_zero() -> None:
    assert reciprocal_rank(["c1", "c2"], {"c9"}) == 0.0


def test_ndcg_at_k_perfect_ranking_is_one() -> None:
    retrieved = ["c1", "c2", "c3"]
    relevant = {"c1", "c2"}
    assert math.isclose(ndcg_at_k(retrieved, relevant, k=3), 1.0)


def test_ndcg_at_k_penalizes_relevant_results_ranked_lower() -> None:
    ideal = ndcg_at_k(["c1", "c2", "c3"], {"c1", "c2"}, k=3)
    worse = ndcg_at_k(["c3", "c1", "c2"], {"c1", "c2"}, k=3)
    assert worse < ideal


def test_ndcg_at_k_no_relevant_hits_is_zero() -> None:
    assert ndcg_at_k(["c1", "c2"], {"c9"}, k=2) == 0.0


def test_ndcg_at_k_no_relevant_ids_is_zero() -> None:
    assert ndcg_at_k(["c1", "c2"], [], k=2) == 0.0
