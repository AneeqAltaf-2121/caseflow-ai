"""Embedding provider abstraction.

The ingestion pipeline (and later, query embedding for search) depends on
`EmbeddingProvider`, never a specific vendor SDK — `get_embedding_provider`
is the one place that decides which implementation a process gets, driven
by `settings.embedding_provider`. See docs/decisions/007-embedding-provider.md.
"""

import hashlib
import math
import re
from typing import Protocol

import httpx

from app.config import Settings
from app.models.chunk import EMBEDDING_DIMENSIONS

_WORD_PATTERN = re.compile(r"[A-Za-z0-9]+")


class EmbeddingProvider(Protocol):
    dimensions: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        return vector
    return [v / norm for v in vector]


class MockEmbeddingProvider:
    """Deterministic but not semantically meaningful: the same text always
    produces the same vector (useful for asserting exact equality / cache
    behavior in tests), but nothing about the vector reflects the text's
    actual meaning or wording — don't use this to test retrieval quality
    (see LocalEmbeddingProvider for that). Needs no dependency, no
    network, no model download; the default so the app runs end-to-end
    with zero provider credentials.
    """

    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        self.dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vector = [(digest[i % len(digest)] / 255.0) * 2 - 1 for i in range(self.dimensions)]
        return _l2_normalize(vector)


class LocalEmbeddingProvider:
    """A real (lexical, not deep-semantic) local embedding using the
    hashing trick: each word hashes into one of `dimensions` buckets,
    weighted by term frequency, L2-normalized. No model download, no
    network access, no GPU/torch dependency — captures literal word
    overlap well enough to be genuinely useful for keyword-heavy
    documents, and is a real drop-in target to replace with a deep model
    (sentence-transformers, etc.) behind this same interface later.
    """

    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        self.dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for word in _WORD_PATTERN.findall(text.lower()):
            bucket = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16) % self.dimensions
            vector[bucket] += 1.0
        return _l2_normalize(vector)


class OpenAIEmbeddingProvider:
    """Real OpenAI embeddings API. Requires OPENAI_API_KEY; not exercised
    in CI (needs network + a real key) by design — MockEmbeddingProvider
    is what actually runs in tests."""

    _MODEL = "text-embedding-3-small"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.dimensions = settings.embedding_dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self._settings.openai_api_key}"},
                json={"model": self._MODEL, "input": texts, "dimensions": self.dimensions},
            )
            response.raise_for_status()
            body = response.json()
        return [item["embedding"] for item in body["data"]]


def get_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "openai":
        return OpenAIEmbeddingProvider(settings)
    if settings.embedding_provider == "local":
        return LocalEmbeddingProvider(settings.embedding_dimensions)
    return MockEmbeddingProvider(settings.embedding_dimensions)
