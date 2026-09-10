"""Conversation history -> a bounded text block for the generation prompt
(Phase 21). The whole conversation is never stuffed into every request:
only the most recent messages, further trimmed until the total is under a
token budget.
"""

from app.ingestion.chunker import count_tokens
from app.models.conversation import Message

DEFAULT_MAX_HISTORY_MESSAGES = 6
DEFAULT_MAX_HISTORY_TOKENS = 800


def build_history_text(
    messages: list[Message],
    *,
    max_messages: int = DEFAULT_MAX_HISTORY_MESSAGES,
    max_tokens: int = DEFAULT_MAX_HISTORY_TOKENS,
) -> str:
    """Most recent `max_messages`, then trimmed from the oldest kept
    message until under `max_tokens` — bounds prompt growth as a
    conversation gets long, rather than growing without limit."""
    recent = messages[-max_messages:]

    def render(msgs: list[Message]) -> str:
        return "\n".join(f"{m.role.value.capitalize()}: {m.content}" for m in msgs)

    while recent and count_tokens(render(recent)) > max_tokens:
        recent = recent[1:]

    return render(recent)
