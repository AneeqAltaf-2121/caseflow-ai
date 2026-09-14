"""Phase 57: performance benchmarking. scripts/benchmark.py builds its
own in-memory SQLite database and corpus, so it can be exercised
directly in pytest (at a tiny scale, for speed) rather than only
smoke-tested by hand — proving the harness itself works, not asserting
on absolute timing numbers, which vary by machine and would make this
test flaky by construction.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "benchmark.py"


def _load_benchmark():
    spec = importlib.util.spec_from_file_location("caseflow_benchmark", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["caseflow_benchmark"] = module
    spec.loader.exec_module(module)
    return module


benchmark = _load_benchmark()


async def test_run_benchmark_produces_a_summary_for_every_operation() -> None:
    report = await benchmark.run_benchmark(num_chunks=10, num_queries=2, iterations=1)

    assert report["corpus"] == {"chunks": 10, "queries": 2, "iterations": 1}
    expected_operations = {
        "semantic_search",
        "keyword_search",
        "hybrid_search_uncached",
        "hybrid_search_cached",
        "reranked_retrieve",
    }
    assert set(report["results"]) == expected_operations
    for summary in report["results"].values():
        assert summary["n"] == 2  # num_queries x iterations
        for key in ("mean_ms", "median_ms", "p95_ms", "max_ms"):
            assert summary[key] >= 0


def test_timing_summary_computes_sane_percentiles() -> None:
    timing = benchmark.Timing("example")
    for seconds in (0.001, 0.002, 0.003, 0.004, 0.100):
        timing.record(seconds)

    summary = timing.summary()

    assert summary["n"] == 5
    assert summary["max_ms"] == pytest.approx(100.0, abs=0.01)
    assert summary["median_ms"] == pytest.approx(3.0, abs=0.01)
    assert summary["mean_ms"] < summary["max_ms"]


def test_readme_or_docs_mention_the_benchmark_script() -> None:
    docs = (REPO_ROOT / "docs" / "benchmarks.md").read_text(encoding="utf-8")
    assert "scripts/benchmark.py" in docs
