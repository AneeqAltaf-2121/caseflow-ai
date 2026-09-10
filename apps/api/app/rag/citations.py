import re

_CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def extract_cited_source_numbers(answer_text: str, *, source_count: int) -> list[int]:
    """Unique source numbers cited in `answer_text`, in first-appearance
    order. A number outside 1..source_count (the model citing a source
    that was never offered — a real failure mode, not hypothetical) is
    silently dropped here rather than raising; Phase 20 is what decides
    whether that failure mode should downgrade or reject the answer.
    """
    seen: list[int] = []
    for match in _CITATION_PATTERN.finditer(answer_text):
        n = int(match.group(1))
        if 1 <= n <= source_count and n not in seen:
            seen.append(n)
    return seen
