from __future__ import annotations

import threading

from web.progress import ProgressTracker


def test_pause_blocks_until_resume() -> None:
    tracker = ProgressTracker(ticker="600370", trade_date="2026-06-05")
    tracker.is_running = True
    assert tracker.pause()

    released = threading.Event()

    def wait_for_resume() -> None:
        tracker.wait_if_paused()
        released.set()

    waiter = threading.Thread(target=wait_for_resume)
    waiter.start()

    assert not released.wait(0.05)
    assert tracker.is_paused

    assert tracker.resume()
    assert released.wait(1)
    waiter.join(timeout=1)
    assert not tracker.is_paused


def test_completion_unblocks_paused_waiter() -> None:
    tracker = ProgressTracker(ticker="600370", trade_date="2026-06-05")
    tracker.is_running = True
    assert tracker.pause()

    released = threading.Event()

    def wait_for_completion() -> None:
        tracker.wait_if_paused()
        released.set()

    waiter = threading.Thread(target=wait_for_completion)
    waiter.start()

    assert not released.wait(0.05)
    tracker.mark_complete({"final_trade_decision": "HOLD"}, "Hold")

    assert released.wait(1)
    waiter.join(timeout=1)
    assert not tracker.is_paused
    assert not tracker.is_running
    assert tracker.is_complete


def test_stop_request_clears_progress_and_unblocks_waiter() -> None:
    tracker = ProgressTracker(ticker="600370", trade_date="2026-06-05")
    tracker.is_running = True
    tracker.mark_stage_active("market")
    tracker.mark_stage_done("market", "report")
    tracker.update_stats(1, 2, 300, 40)
    assert tracker.pause()

    released = threading.Event()

    def wait_for_stop() -> None:
        tracker.wait_if_paused()
        released.set()

    waiter = threading.Thread(target=wait_for_stop)
    waiter.start()

    assert not released.wait(0.05)
    assert tracker.request_stop()

    assert released.wait(1)
    waiter.join(timeout=1)
    assert tracker.stop_requested
    assert not tracker.is_paused
    assert tracker.completed_stages == []
    assert tracker.stage_reports == {}
    assert tracker.current_stage == ""
    assert tracker.llm_calls == 0
    assert tracker.tool_calls == 0
    assert tracker.tokens_in == 0
    assert tracker.tokens_out == 0


def test_mark_stopped_returns_tracker_to_idle() -> None:
    tracker = ProgressTracker(ticker="600370", trade_date="2026-06-05")
    tracker.is_running = True
    assert tracker.request_stop()

    tracker.mark_stopped()

    assert not tracker.is_running
    assert not tracker.is_complete
    assert not tracker.is_paused
    assert not tracker.stop_requested
    assert tracker.completed_stages == []
    assert tracker.stage_reports == {}
