"""LLM generation provider abstraction.

Everything downstream (RAG generation Phase 19, LLM-as-a-judge Phase 28)
depends on `GenerationProvider`, never a specific vendor SDK —
`get_generation_provider` is the one place that decides which
implementation a process gets, driven by `settings.llm_provider`. Same
pattern as app/integrations/embeddings.py and storage.py.
"""

from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import Settings
from app.ingestion.chunker import count_tokens


@dataclass(frozen=True)
class GenerationResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int


class GenerationProvider(Protocol):
    model: str

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> GenerationResult: ...


class MockGenerationProvider:
    """Deterministic, no network, no API key. Returns `canned_response`
    verbatim when given one (what RAG/eval tests use to control exactly
    what "the model said" without depending on a real LLM's phrasing), or
    a clearly-marked echo of the prompt otherwise. Default provider so the
    app runs end-to-end with zero LLM credentials.
    """

    model = "mock-echo-v1"

    def __init__(self, *, canned_response: str | None = None) -> None:
        self._canned_response = canned_response

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> GenerationResult:
        text = self._canned_response
        if text is None:
            text = f"[mock response to: {user_prompt[:200]}]"
        return GenerationResult(
            text=text,
            model=self.model,
            input_tokens=count_tokens(system_prompt) + count_tokens(user_prompt),
            output_tokens=count_tokens(text),
        )


class OpenAIGenerationProvider:
    """Real OpenAI chat completions API. Requires OPENAI_API_KEY; not
    exercised in CI by design — MockGenerationProvider is what runs in
    tests."""

    model = "gpt-4o-mini"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> GenerationResult:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._settings.openai_api_key}"},
                json={
                    "model": self.model,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
            )
            response.raise_for_status()
            body = response.json()
        return GenerationResult(
            text=body["choices"][0]["message"]["content"],
            model=self.model,
            input_tokens=body["usage"]["prompt_tokens"],
            output_tokens=body["usage"]["completion_tokens"],
        )


class AnthropicGenerationProvider:
    """Real Anthropic Messages API. Requires ANTHROPIC_API_KEY; not
    exercised in CI by design — MockGenerationProvider is what runs in
    tests."""

    model = "claude-3-5-haiku-20241022"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> GenerationResult:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self._settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "system": system_prompt,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
            )
            response.raise_for_status()
            body = response.json()
        return GenerationResult(
            text="".join(block["text"] for block in body["content"] if block["type"] == "text"),
            model=self.model,
            input_tokens=body["usage"]["input_tokens"],
            output_tokens=body["usage"]["output_tokens"],
        )


def get_generation_provider(settings: Settings) -> GenerationProvider:
    if settings.llm_provider == "openai":
        return OpenAIGenerationProvider(settings)
    if settings.llm_provider == "anthropic":
        return AnthropicGenerationProvider(settings)
    return MockGenerationProvider()


class UnknownModelError(ValueError):
    pass


def get_generation_provider_by_model(model: str, settings: Settings) -> GenerationProvider:
    """Resolves a specific model name to its provider, independent of
    `settings.llm_provider` — Phase 31's model comparison needs to run the
    *same* dataset through several models in separate EvaluationRuns, not
    just whichever one is globally configured. Instantiating a real
    provider here doesn't spend anything (no network call happens until
    `.generate()` is actually awaited), so this is safe to call just to
    validate a requested model name exists.
    """
    providers: dict[str, GenerationProvider] = {
        MockGenerationProvider.model: MockGenerationProvider(),
        OpenAIGenerationProvider.model: OpenAIGenerationProvider(settings),
        AnthropicGenerationProvider.model: AnthropicGenerationProvider(settings),
    }
    try:
        return providers[model]
    except KeyError:
        raise UnknownModelError(
            f"Unknown model {model!r}. Known models: {sorted(providers)}."
        ) from None
