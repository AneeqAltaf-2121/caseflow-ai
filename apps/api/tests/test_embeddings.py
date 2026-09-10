import pytest

from app.config import Settings
from app.integrations.embeddings import (
    LocalEmbeddingProvider,
    MockEmbeddingProvider,
    OpenAIEmbeddingProvider,
    cosine_similarity,
    get_embedding_provider,
)


async def test_mock_embedding_is_deterministic() -> None:
    provider = MockEmbeddingProvider(dimensions=32)
    first = await provider.embed(["hello world"])
    second = await provider.embed(["hello world"])
    assert first == second
    assert len(first[0]) == 32


async def test_mock_embedding_differs_for_different_text() -> None:
    provider = MockEmbeddingProvider(dimensions=32)
    vectors = await provider.embed(["hello world", "goodbye world"])
    assert vectors[0] != vectors[1]


async def test_mock_embedding_is_unit_normalized() -> None:
    provider = MockEmbeddingProvider(dimensions=32)
    [vector] = await provider.embed(["some text"])
    norm = sum(v * v for v in vector) ** 0.5
    assert norm == pytest.approx(1.0, abs=1e-6)


async def test_local_embedding_reflects_lexical_similarity() -> None:
    provider = LocalEmbeddingProvider(dimensions=256)
    [cat_a, cat_b, unrelated] = await provider.embed(
        [
            "the cat sat on the mat",
            "the cat sat on the rug",
            "quantum physics equations are extremely difficult",
        ]
    )
    similar_score = cosine_similarity(cat_a, cat_b)
    different_score = cosine_similarity(cat_a, unrelated)
    assert similar_score > different_score


async def test_local_embedding_identical_text_has_similarity_one() -> None:
    provider = LocalEmbeddingProvider(dimensions=128)
    [a, b] = await provider.embed(["identical text here", "identical text here"])
    assert cosine_similarity(a, b) == pytest.approx(1.0, abs=1e-9)


def test_cosine_similarity_orthogonal_vectors_is_zero() -> None:
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_zero_vector_is_zero_not_nan() -> None:
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


@pytest.mark.parametrize(
    ("provider_name", "expected_type"),
    [
        ("mock", MockEmbeddingProvider),
        ("local", LocalEmbeddingProvider),
        ("openai", OpenAIEmbeddingProvider),
    ],
)
def test_get_embedding_provider_dispatches_by_setting(provider_name, expected_type) -> None:
    settings = Settings(embedding_provider=provider_name)
    assert isinstance(get_embedding_provider(settings), expected_type)
