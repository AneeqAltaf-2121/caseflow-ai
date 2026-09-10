from app.rag.citations import extract_cited_source_numbers


def test_extracts_unique_citations_in_first_appearance_order() -> None:
    text = "The term is 90 days [2]. This is confirmed elsewhere [1] and again [2]."
    assert extract_cited_source_numbers(text, source_count=3) == [2, 1]


def test_drops_out_of_range_citations() -> None:
    text = "See [1] and also the nonexistent [99]."
    assert extract_cited_source_numbers(text, source_count=1) == [1]


def test_no_citations_returns_empty_list() -> None:
    assert extract_cited_source_numbers("No sources referenced here.", source_count=3) == []


def test_zero_source_count_drops_everything() -> None:
    assert extract_cited_source_numbers("See [1].", source_count=0) == []
