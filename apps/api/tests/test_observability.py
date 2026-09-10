from app.observability import LatencyTracker


def test_latency_tracker_snapshot_computes_percentiles() -> None:
    tracker = LatencyTracker()
    for ms in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
        tracker.record("GET /x", ms)

    snapshot = tracker.snapshot()

    assert snapshot["GET /x"].count == 10
    assert snapshot["GET /x"].max_ms == 100
    # p50 is the median-ish sample from the sorted window, p95 near the top.
    assert 40 <= snapshot["GET /x"].p50_ms <= 60
    assert snapshot["GET /x"].p95_ms >= snapshot["GET /x"].p50_ms


def test_latency_tracker_tracks_separate_keys_independently() -> None:
    tracker = LatencyTracker()
    tracker.record("GET /a", 5)
    tracker.record("POST /b", 500)

    snapshot = tracker.snapshot()

    assert snapshot["GET /a"].max_ms == 5
    assert snapshot["POST /b"].max_ms == 500


def test_latency_tracker_window_drops_oldest_samples() -> None:
    tracker = LatencyTracker(window_size=3)
    for ms in [1, 2, 3, 4, 5]:
        tracker.record("GET /x", ms)

    snapshot = tracker.snapshot()

    assert snapshot["GET /x"].count == 3
    assert snapshot["GET /x"].max_ms == 5  # oldest (1, 2) dropped, not newest


def test_latency_tracker_snapshot_empty_when_no_samples() -> None:
    tracker = LatencyTracker()
    assert tracker.snapshot() == {}


def test_latency_tracker_reset_clears_all_keys() -> None:
    tracker = LatencyTracker()
    tracker.record("GET /x", 10)
    tracker.reset()
    assert tracker.snapshot() == {}
