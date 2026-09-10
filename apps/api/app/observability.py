"""Observability (Phase 34): P50/P95 request latency tracking, on top of
the structured JSON logging + per-request request_id already in place
(app/logging.py, app/api/middleware.py — Phase 2/3).

No external metrics backend (Prometheus, Datadog, ...) for a project
with no live production traffic to send them to — see docs/decisions
on IaC-only deployment. A bounded in-process rolling window per route is
enough to answer "how slow is this endpoint actually running" during
local development or a demo session, and is honest about not claiming
more than it can measure (this resets on every process restart and
isn't shared across workers).
"""

import threading
from collections import defaultdict, deque
from dataclasses import dataclass

DEFAULT_WINDOW_SIZE = 500


@dataclass(frozen=True)
class LatencySnapshot:
    count: int
    p50_ms: float
    p95_ms: float
    max_ms: float


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, int(p * len(sorted_values)))
    return sorted_values[index]


class LatencyTracker:
    """Thread-safe (the ASGI server may run sync middleware across
    threads even though the app itself is async) bounded rolling window
    of durations per key (typically "METHOD /path"). Old samples are
    dropped automatically once a key's window fills, so this stays O(1)
    memory per key regardless of how long the process runs."""

    def __init__(self, window_size: int = DEFAULT_WINDOW_SIZE) -> None:
        self._window_size = window_size
        self._samples: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=window_size))
        self._lock = threading.Lock()

    def record(self, key: str, duration_ms: float) -> None:
        with self._lock:
            self._samples[key].append(duration_ms)

    def snapshot(self) -> dict[str, LatencySnapshot]:
        with self._lock:
            items = [(key, list(values)) for key, values in self._samples.items()]

        result: dict[str, LatencySnapshot] = {}
        for key, values in items:
            if not values:
                continue
            sorted_values = sorted(values)
            result[key] = LatencySnapshot(
                count=len(sorted_values),
                p50_ms=_percentile(sorted_values, 0.50),
                p95_ms=_percentile(sorted_values, 0.95),
                max_ms=sorted_values[-1],
            )
        return result

    def reset(self) -> None:
        with self._lock:
            self._samples.clear()


# One process-wide tracker, same singleton pattern as app.cache.get_cache
# and app.jobs's broker — not per-request, so samples actually accumulate.
_tracker = LatencyTracker()


def get_latency_tracker() -> LatencyTracker:
    return _tracker
