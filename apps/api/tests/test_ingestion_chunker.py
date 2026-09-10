from app.ingestion.chunker import chunk_document, chunk_page, count_tokens
from app.ingestion.models import ExtractedDocument, ExtractedPage


def _page(text: str, page_number: int = 1) -> ExtractedPage:
    return ExtractedPage(page_number=page_number, text=text)


def test_count_tokens_counts_whitespace_delimited_words() -> None:
    assert count_tokens("the quick brown fox") == 4
    assert count_tokens("") == 0


def test_single_short_paragraph_is_one_chunk() -> None:
    page = _page("Just one short paragraph.")
    chunks = chunk_page(page, max_tokens=100, overlap_tokens=10)
    assert len(chunks) == 1
    assert chunks[0].text == page.text
    assert chunks[0].page_number == 1


def test_empty_page_produces_no_chunks() -> None:
    assert chunk_page(_page("")) == []
    assert chunk_page(_page("   \n\n   ")) == []


def test_offsets_always_reproduce_chunk_text_exactly() -> None:
    paragraphs = [f"Paragraph number {i} with some extra padding words here." for i in range(12)]
    page = _page("\n\n".join(paragraphs))

    chunks = chunk_page(page, max_tokens=20, overlap_tokens=5)

    assert len(chunks) > 1
    for chunk in chunks:
        assert page.text[chunk.start_offset : chunk.end_offset] == chunk.text
        assert chunk.token_count == count_tokens(chunk.text)


def test_no_text_silently_disappears() -> None:
    paragraphs = [f"UniqueParagraphMarker{i} filler word content padding text." for i in range(10)]
    page = _page("\n\n".join(paragraphs))

    chunks = chunk_page(page, max_tokens=15, overlap_tokens=3)
    combined = " ".join(chunk.text for chunk in chunks)

    for i in range(10):
        assert f"UniqueParagraphMarker{i}" in combined


def test_overlap_carries_trailing_paragraph_into_next_chunk() -> None:
    # Each paragraph is exactly 5 tokens; max_tokens=10 fits two paragraphs
    # per chunk, overlap_tokens=5 carries exactly the last paragraph over.
    paragraphs = [f"para{i} word word word word" for i in range(4)]
    page = _page("\n\n".join(paragraphs))

    chunks = chunk_page(page, max_tokens=10, overlap_tokens=5)

    assert len(chunks) >= 2
    # The paragraph that closes chunk 0 must also open chunk 1.
    last_of_first = paragraphs[1]
    assert last_of_first in chunks[0].text
    assert last_of_first in chunks[1].text


def test_paragraph_boundaries_are_never_split_when_it_fits() -> None:
    paragraphs = ["Short one.", "Short two.", "Short three."]
    page = _page("\n\n".join(paragraphs))

    chunks = chunk_page(page, max_tokens=100, overlap_tokens=0)

    assert len(chunks) == 1
    for paragraph in paragraphs:
        assert paragraph in chunks[0].text


def test_paragraph_exceeding_budget_is_split_but_offsets_still_exact() -> None:
    long_paragraph = " ".join(f"word{i}" for i in range(50))
    page = _page(long_paragraph)

    chunks = chunk_page(page, max_tokens=10, overlap_tokens=2)

    assert len(chunks) > 1
    for chunk in chunks:
        assert page.text[chunk.start_offset : chunk.end_offset] == chunk.text
        assert chunk.token_count <= 10
    # every word must survive somewhere in the union of chunks
    combined_words = set(" ".join(c.text for c in chunks).split())
    assert combined_words == {f"word{i}" for i in range(50)}


def test_chunk_document_preserves_page_numbers_across_pages() -> None:
    document = ExtractedDocument(
        source_filename="doc.pdf",
        pages=[
            _page("First page paragraph one.\n\nFirst page paragraph two.", page_number=1),
            _page("Second page paragraph one.\n\nSecond page paragraph two.", page_number=2),
        ],
    )

    chunks = chunk_document(document, max_tokens=100, overlap_tokens=0)

    assert {c.page_number for c in chunks} == {1, 2}
    page_one_text = " ".join(c.text for c in chunks if c.page_number == 1)
    page_two_text = " ".join(c.text for c in chunks if c.page_number == 2)
    assert "First page" in page_one_text
    assert "Second page" in page_two_text
    assert "Second page" not in page_one_text


def test_chunk_ids_are_unique() -> None:
    paragraphs = [f"Paragraph {i} content padding words here now." for i in range(20)]
    page = _page("\n\n".join(paragraphs))

    chunks = chunk_page(page, max_tokens=15, overlap_tokens=5)

    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))
