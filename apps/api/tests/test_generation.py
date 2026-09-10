import pytest

from app.config import Settings
from app.integrations.generation import (
    AnthropicGenerationProvider,
    MockGenerationProvider,
    OpenAIGenerationProvider,
    UnknownModelError,
    get_generation_provider,
    get_generation_provider_by_model,
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


@pytest.mark.parametrize(
    ("model", "expected_type"),
    [
        ("mock-echo-v1", MockGenerationProvider),
        ("gpt-4o-mini", OpenAIGenerationProvider),
        ("claude-3-5-haiku-20241022", AnthropicGenerationProvider),
    ],
)
def test_get_generation_provider_by_model_resolves_known_models(model, expected_type) -> None:
    # Independent of settings.llm_provider — Phase 31 model comparison
    # needs to pick a specific model regardless of the global default.
    settings = Settings(llm_provider="mock")
    provider = get_generation_provider_by_model(model, settings)
    assert isinstance(provider, expected_type)
    assert provider.model == model


def test_get_generation_provider_by_model_rejects_unknown_model() -> None:
    settings = Settings()
    with pytest.raises(UnknownModelError):
        get_generation_provider_by_model("gpt-5-turbo-ultra", settings)
