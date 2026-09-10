import uuid
from datetime import UTC, datetime

from app.models.conversation import Message, MessageRole
from app.rag.history import build_history_text


def _message(role: MessageRole, content: str) -> Message:
    return Message(
        id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        role=role,
        content=content,
        created_at=datetime.now(UTC),
    )


def test_empty_history_is_empty_string() -> None:
    assert build_history_text([]) == ""


def test_renders_role_and_content() -> None:
    messages = [_message(MessageRole.USER, "Hello"), _message(MessageRole.ASSISTANT, "Hi there")]
    text = build_history_text(messages)
    assert text == "User: Hello\nAssistant: Hi there"


def test_keeps_only_the_most_recent_max_messages() -> None:
    messages = [_message(MessageRole.USER, f"msg {i}") for i in range(10)]
    text = build_history_text(messages, max_messages=3, max_tokens=10_000)
    assert "msg 7" in text
    assert "msg 8" in text
    assert "msg 9" in text
    assert "msg 0" not in text


def test_trims_from_the_oldest_until_under_token_budget() -> None:
    long_message = _message(MessageRole.USER, " ".join(["word"] * 50))
    short_message = _message(MessageRole.ASSISTANT, "short reply")
    text = build_history_text([long_message, short_message], max_messages=10, max_tokens=10)
    assert "short reply" in text
    assert "word" not in text


def test_never_exceeds_message_count_even_with_huge_token_budget() -> None:
    messages = [_message(MessageRole.USER, f"msg {i}") for i in range(5)]
    text = build_history_text(messages, max_messages=2, max_tokens=1_000_000)
    assert text.count("msg") == 2
