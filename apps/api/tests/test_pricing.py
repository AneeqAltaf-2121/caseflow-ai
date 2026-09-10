from app.integrations.pricing import estimate_cost_usd


def test_known_model_computes_nonzero_cost() -> None:
    cost = estimate_cost_usd(model="gpt-4o-mini", input_tokens=1000, output_tokens=1000)
    assert cost > 0


def test_unknown_model_is_free_not_an_error() -> None:
    assert estimate_cost_usd(model="mock-echo-v1", input_tokens=1000, output_tokens=1000) == 0.0


def test_zero_tokens_is_zero_cost() -> None:
    assert estimate_cost_usd(model="gpt-4o-mini", input_tokens=0, output_tokens=0) == 0.0


def test_cost_scales_with_token_count() -> None:
    model = "claude-3-5-haiku-20241022"
    small = estimate_cost_usd(model=model, input_tokens=100, output_tokens=100)
    large = estimate_cost_usd(model=model, input_tokens=1000, output_tokens=1000)
    assert large > small
