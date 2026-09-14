#!/usr/bin/env python
"""Phase 57: performance benchmarking.

Measures latency of the app's retrieval pipeline — semantic, keyword,
hybrid, and reranked search — against a synthetic in-process corpus,
without needing a live deployment.

IMPORTANT — what this does and doesn't tell you:

  This runs against an in-memory SQLite database and
  LocalEmbeddingProvider (see ADR 007), the same dev/test stand-ins
  apps/api/tests/ uses — not the real PostgreSQL+pgvector path a
  production deployment takes. app/repositories/chunk_repository.py's
  semantic search falls back to a pure-Python cosine-distance scan on
  any non-PostgreSQL dialect, which is *slower* than pgvector's native
  operator for large corpora and *faster* to set up here than standing
  up real Postgres. These numbers are useful for one thing: catching a
  relative regression between two runs of this same script (e.g.
  before/after a retrieval code change), never as an absolute
  production SLA.

Usage:

    python scripts/benchmark.py
    python scripts/benchmark.py --chunks 1000 --queries 30 --iterations 5
    python scripts/benchmark.py --output results.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Must be set before any app.* import — see tests/_bootstrap.py's own
# comment on why (app/jobs/__init__.py picks a broker at import time).
os.environ.setdefault("ENVIRONMENT", "test")

API_ROOT = Path(__file__).resolve().parent.parent / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.models  # noqa: E402,F401 - populates Base.metadata before create_all
from app.cache import InMemoryCache  # noqa: E402
from app.database import Base  # noqa: E402
from app.integrations.embeddings import LocalEmbeddingProvider  # noqa: E402
from app.models.chunk import DocumentChunk  # noqa: E402
from app.repositories.chunk_repository import DocumentChunkRepository  # noqa: E402
from app.repositories.document_repository import DocumentRepository  # noqa: E402
from app.repositories.organization_repository import OrganizationRepository  # noqa: E402
from app.repositories.project_repository import ProjectRepository  # noqa: E402
from app.repositories.user_repository import UserRepository  # noqa: E402
from app.retrieval.reranker import CrossEncoderReranker  # noqa: E402
from app.services.hybrid_search_service import HybridSearchService  # noqa: E402
from app.services.keyword_search_service import KeywordSearchService  # noqa: E402
from app.services.project_service import ProjectService  # noqa: E402
from app.services.retrieval_service import RetrievalService  # noqa: E402
from app.services.search_service import SearchService  # noqa: E402

EMBEDDING_DIMENSIONS = 64

# A small pool of subject/predicate fragments combined to generate a
# corpus with realistic keyword diversity (so BM25 and phrase-overlap
# reranking have something meaningful to discriminate on) without
# hand-authoring hundreds of sentences.
SUBJECTS = [
    "the vendor",
    "the buyer",
    "the agreement",
    "the indemnification clause",
    "the payment schedule",
    "the confidentiality provision",
    "the termination notice",
    "the service level agreement",
    "the warranty period",
    "the governing law clause",
]
PREDICATES = [
    "must be delivered within thirty days of signing.",
    "terminates ninety days after written notice from either party.",
    "requires payment net thirty from the invoice date.",
    "survives termination of the underlying contract.",
    "is subject to review on an annual basis.",
    "applies only to disputes arising in this jurisdiction.",
    "may be amended only in writing signed by both parties.",
    "excludes liability for indirect or consequential damages.",
    "is renewed automatically unless either party objects in writing.",
    "was negotiated over several rounds between both parties' counsel.",
]

QUERIES = [
    "When does the agreement terminate?",
    "What is the payment schedule?",
    "Is there an indemnification clause?",
    "What does the warranty period cover?",
    "How is the contract amended?",
    "What law governs this agreement?",
]


@dataclass
class Timing:
    label: str
    samples_ms: list[float] = field(default_factory=list)

    def record(self, seconds: float) -> None:
        self.samples_ms.append(seconds * 1000)

    def summary(self) -> dict[str, float]:
        s = sorted(self.samples_ms)
        n = len(s)
        p95_index = min(n - 1, int(round(0.95 * (n - 1))))
        return {
            "n": n,
            "mean_ms": round(statistics.mean(s), 3),
            "median_ms": round(statistics.median(s), 3),
            "p95_ms": round(s[p95_index], 3),
            "max_ms": round(max(s), 3),
        }


async def _timed(timing: Timing, coro):
    start = time.perf_counter()
    result = await coro
    timing.record(time.perf_counter() - start)
    return result


async def _seed_corpus(
    session: AsyncSession, *, num_chunks: int, provider: LocalEmbeddingProvider
) -> tuple[uuid.UUID, uuid.UUID]:
    """Returns (project_id, user_id). One document, `num_chunks` chunks
    with embeddings, text generated by combining SUBJECTS x PREDICATES
    (repeating/cycling once the pool is exhausted)."""
    user = await UserRepository(session).create(email="bench@example.com", display_name="Bench")
    org = await OrganizationRepository(session).create(name="Bench Org", slug="bench-org")
    project = await ProjectService(ProjectRepository(session)).create_project(
        organization_id=org.id, name="Benchmark Project", description=None, created_by=user.id
    )
    document_repository = DocumentRepository(session)
    document = await document_repository.create(
        project_id=project.id,
        filename="benchmark-corpus.txt",
        content_type="text/plain",
        size_bytes=1,
        checksum_sha256="bench",
        storage_key="benchmark-corpus.txt",
        uploaded_by=user.id,
    )
    await session.commit()
    document = await document_repository.get_by_id(document.id)
    assert document is not None
    version_id = document.versions[0].id

    texts = [
        f"{SUBJECTS[i % len(SUBJECTS)].capitalize()} {PREDICATES[(i * 7) % len(PREDICATES)]}"
        for i in range(num_chunks)
    ]
    # Embed in batches — mirrors how real ingestion never embeds one
    # chunk per call either (see app/services/document_service.py).
    batch_size = 100
    embeddings: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        embeddings.extend(await provider.embed(texts[start : start + batch_size]))

    chunks = [
        DocumentChunk(
            document_id=document.id,
            document_version_id=version_id,
            page_number=1 + (i // 20),
            section=None,
            text=text,
            token_count=len(text.split()),
            start_offset=i * 100,
            end_offset=i * 100 + len(text),
            embedding=embedding,
            chunk_metadata={},
        )
        for i, (text, embedding) in enumerate(zip(texts, embeddings, strict=True))
    ]
    await DocumentChunkRepository(session).bulk_create(chunks)
    await session.commit()
    return project.id, user.id


async def run_benchmark(
    *, num_chunks: int, num_queries: int, iterations: int
) -> dict[str, Any]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        bind=engine, expire_on_commit=False
    )

    provider = LocalEmbeddingProvider(dimensions=EMBEDDING_DIMENSIONS)
    queries = (QUERIES * ((num_queries // len(QUERIES)) + 1))[:num_queries]

    async with session_factory() as seed_session:
        project_id, user_id = await _seed_corpus(
            seed_session, num_chunks=num_chunks, provider=provider
        )

    timings = {
        "semantic_search": Timing("semantic_search"),
        "keyword_search": Timing("keyword_search"),
        "hybrid_search_uncached": Timing("hybrid_search_uncached"),
        "hybrid_search_cached": Timing("hybrid_search_cached"),
        "reranked_retrieve": Timing("reranked_retrieve"),
    }

    reranker = CrossEncoderReranker()

    async with session_factory() as session:
        project_service = ProjectService(ProjectRepository(session))
        chunk_repository = DocumentChunkRepository(session)

        semantic_service = SearchService(chunk_repository, project_service, provider)
        keyword_service = KeywordSearchService(chunk_repository, project_service)
        hybrid_service_uncached = HybridSearchService(chunk_repository, project_service, provider)
        cache = InMemoryCache()
        hybrid_service_cached = HybridSearchService(
            chunk_repository, project_service, provider, cache
        )
        retrieval_service = RetrievalService(hybrid_service_cached, reranker)

        for _ in range(iterations):
            for query in queries:
                await _timed(
                    timings["semantic_search"],
                    semantic_service.semantic_search(
                        project_id=project_id, user_id=user_id, query=query
                    ),
                )
                await _timed(
                    timings["keyword_search"],
                    keyword_service.keyword_search(
                        project_id=project_id, user_id=user_id, query=query
                    ),
                )
                await _timed(
                    timings["hybrid_search_uncached"],
                    hybrid_service_uncached.hybrid_search(
                        project_id=project_id, user_id=user_id, query=query
                    ),
                )
                await _timed(
                    timings["reranked_retrieve"],
                    retrieval_service.retrieve(project_id=project_id, user_id=user_id, query=query),
                )

        # A second full pass over the *cached* hybrid service, same
        # queries repeated — first pass (above, via retrieval_service)
        # already warmed the cache for every query, so this isolates the
        # cache-hit path Phase 33 added, measured against the uncached
        # numbers collected above.
        for _ in range(iterations):
            for query in queries:
                await _timed(
                    timings["hybrid_search_cached"],
                    hybrid_service_cached.hybrid_search(
                        project_id=project_id, user_id=user_id, query=query
                    ),
                )

    await engine.dispose()

    return {
        "corpus": {"chunks": num_chunks, "queries": num_queries, "iterations": iterations},
        "results": {name: timing.summary() for name, timing in timings.items()},
    }


def _print_report(report: dict[str, Any]) -> None:
    corpus = report["corpus"]
    print(
        f"Corpus: {corpus['chunks']} chunks, {corpus['queries']} distinct queries x "
        f"{corpus['iterations']} iterations each"
    )
    print(
        "Backend: SQLite (in-memory) + LocalEmbeddingProvider - dev/test stand-ins, "
        "NOT production Postgres+pgvector. See this script's module docstring."
    )
    print()
    header = (
        f"{'operation':<24} {'n':>5} {'mean ms':>10} {'median ms':>10} {'p95 ms':>9} {'max ms':>9}"
    )
    print(header)
    print("-" * len(header))
    for name, summary in report["results"].items():
        print(
            f"{name:<24} {summary['n']:>5} {summary['mean_ms']:>10} "
            f"{summary['median_ms']:>10} {summary['p95_ms']:>9} {summary['max_ms']:>9}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--chunks", type=int, default=300, help="synthetic chunks to seed (default: 300)"
    )
    parser.add_argument(
        "--queries", type=int, default=6, help="distinct queries to cycle through (default: 6)"
    )
    parser.add_argument(
        "--iterations", type=int, default=5, help="repetitions per query (default: 5)"
    )
    parser.add_argument(
        "--output", type=Path, default=None, help="also write results as JSON to this path"
    )
    args = parser.parse_args()

    report = asyncio.run(
        run_benchmark(num_chunks=args.chunks, num_queries=args.queries, iterations=args.iterations)
    )
    _print_report(report)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2))
        print(f"\nWrote {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
