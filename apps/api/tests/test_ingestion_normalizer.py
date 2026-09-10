from app.ingestion.normalizer import normalize_text


def test_normalizes_line_endings() -> None:
    assert normalize_text("a\r\nb\rc") == "a\nb\nc"


def test_collapses_horizontal_whitespace_but_not_newlines() -> None:
    assert normalize_text("a    b\tc") == "a b c"


def test_collapses_excess_blank_lines_but_keeps_paragraphs() -> None:
    assert normalize_text("a\n\n\n\n\nb") == "a\n\nb"


def test_strips_trailing_whitespace_per_line() -> None:
    assert normalize_text("line one   \nline two\t\n") == "line one\nline two"


def test_no_text_silently_disappears_for_simple_input() -> None:
    original_words = ["The", "quick", "brown", "fox", "jumps", "over", "the", "lazy", "dog"]
    normalized = normalize_text("  The   quick brown \t fox jumps over the lazy dog  ")
    assert normalized.split() == original_words
