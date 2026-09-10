"""Static per-model pricing for cost estimation (Phase 23's
ModelRun.estimated_cost_usd; Phase 32 builds aggregation on top of this).

Prices are USD per 1,000 tokens, approximate published rates as of this
writing — not fetched live, so they drift over time. Good enough for
relative cost comparison between runs/models, which is what this project
uses it for; a real billing reconciliation would need the provider's
actual invoiced rates.
"""

from app.integrations.generation import GenerationProvider

# (input $/1K tokens, output $/1K tokens)
_PRICING_PER_1K_TOKENS: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.00015, 0.0006),
    "claude-3-5-haiku-20241022": (0.0008, 0.004),
}


def estimate_cost_usd(*, model: str, input_tokens: int, output_tokens: int) -> float:
    """0.0 for any model without a known price (the mock provider,
    chiefly) — never raises on an unrecognized model name."""
    prices = _PRICING_PER_1K_TOKENS.get(model)
    if prices is None:
        return 0.0
    input_price, output_price = prices
    return (input_tokens / 1000) * input_price + (output_tokens / 1000) * output_price


def provider_name(generation_provider: GenerationProvider) -> str:
    return type(generation_provider).__name__
