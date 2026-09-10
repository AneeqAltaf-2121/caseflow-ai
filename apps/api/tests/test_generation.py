import pytest

from app.config import Settings
from app.integrations.generation import (
    AnthropicGenerationProvider,
    MockGenerationProvider,
    OpenAIGenerationProvider,
    get_generation_provider,
)


async def test_mock_generation_returns_canned_response_verbatim() -> None:
    provider = MockGenerationProvider(canned_response="The answer is 42.")
    result = await provider.generate(system_prompt="sys", user_prompt="what is the answer?")
    assert result.text == "The answer is 42."
    assert result.model == "mock-echo-v1"
    assert result.input_tokens > 0
    assert result.output_tokens > 0


async def test_mock_generation_echoes_prompt_without_canned_response() -> None:
    provider = MockGenerationProvider()
    result = await provider.generate(system_prompt="sys", user_prompt="hello world")
    assert "hello world" in result.text


@pytest.mark.parametrize(
    ("provider_name", "expected_type"),
    [
        ("mock", MockGenerationProvider),
        ("openai", OpenAIGenerationProvider),
        ("anthropic", AnthropicGenerationProvider),
    ],
)
def test_get_generation_provider_dispatches_by_setting(provider_name, expected_type) -> None:
    settings = Settings(llm_provider=provider_name)
    assert isinstance(get_generation_provider(settings), expected_type)
