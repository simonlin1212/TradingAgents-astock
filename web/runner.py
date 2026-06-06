"""Background thread runner for TradingAgentsGraph pipeline."""

from __future__ import annotations

import re
import threading
import traceback
from typing import Any

from web.history import clear_incomplete_task, record_incomplete_task
from web.progress import PIPELINE_STAGES, ProgressTracker


_REPORT_KEY_TO_STAGE = {s["report_key"]: s["id"] for s in PIPELINE_STAGES}

_ANALYST_REPORT_KEYS = [
    "market_report", "sentiment_report", "news_report",
    "fundamentals_report", "policy_report", "hot_money_report", "lockup_report",
]


def _discard_stopped_run(
    ticker: str,
    trade_date: str,
    config: dict,
    tracker: ProgressTracker,
) -> None:
    """Clear resumable artifacts for a user-stopped run."""
    from tradingagents.graph.checkpointer import clear_checkpoint

    clear_incomplete_task(ticker, trade_date)
    clear_checkpoint(config["data_cache_dir"], ticker, trade_date)
    tracker.mark_stopped()


def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks from LLM output."""
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()


def _detect_completed_stages(
    chunk: dict[str, Any],
    tracker: ProgressTracker,
) -> None:
    """Check the streamed chunk for newly completed stages."""
    for report_key in _ANALYST_REPORT_KEYS:
        stage_id = _REPORT_KEY_TO_STAGE[report_key]
        content = chunk.get(report_key, "")
        if content and tracker.stage_status(stage_id) != "done":
            tracker.mark_stage_done(stage_id, _strip_think_tags(str(content)))

    dqs = chunk.get("data_quality_summary", "")
    if dqs and tracker.stage_status("quality_gate") != "done":
        tracker.mark_stage_done("quality_gate", str(dqs))

    debate = chunk.get("investment_debate_state")
    if debate and isinstance(debate, dict):
        judge = debate.get("judge_decision", "")
        if judge and tracker.stage_status("debate") != "done":
            tracker.mark_stage_done("debate", str(judge))

    trader_plan = chunk.get("trader_investment_plan", "")
    if trader_plan and tracker.stage_status("trader") != "done":
        tracker.mark_stage_done("trader", _strip_think_tags(str(trader_plan)))

    risk = chunk.get("risk_debate_state")
    if risk and isinstance(risk, dict):
        risk_judge = risk.get("judge_decision", "")
        if risk_judge and tracker.stage_status("risk") != "done":
            tracker.mark_stage_done("risk", str(risk_judge))

    final = chunk.get("final_trade_decision", "")
    if final and tracker.stage_status("pm") != "done":
        tracker.mark_stage_done("pm", _strip_think_tags(str(final)))


def _infer_active_stage(tracker: ProgressTracker) -> None:
    """Set the current_stage to the first non-completed stage."""
    from web.progress import STAGE_IDS
    for sid in STAGE_IDS:
        if tracker.stage_status(sid) == "pending":
            tracker.mark_stage_active(sid)
            return


def _run(ticker: str, trade_date: str, config: dict, tracker: ProgressTracker) -> None:
    """Execute the full pipeline in the current thread."""
    from cli.stats_handler import StatsCallbackHandler
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    stats = StatsCallbackHandler()

    graph = TradingAgentsGraph(
        debug=True,
        config=config,
        callbacks=[stats],
    )

    init_state, args, _ = graph.prepare_graph_run(
        ticker,
        trade_date,
        callbacks=[stats],
    )

    last_chunk: dict[str, Any] = {}

    try:
        def _close_and_discard() -> None:
            graph.close_graph_run()
            _discard_stopped_run(ticker, trade_date, config, tracker)

        if tracker.stop_requested:
            _close_and_discard()
            return

        stream = graph.graph.stream(init_state, **args)
        while True:
            tracker.wait_if_paused()
            if tracker.stop_requested:
                _close_and_discard()
                return
            try:
                chunk = next(stream)
            except StopIteration:
                break

            if tracker.stop_requested:
                _close_and_discard()
                return

            last_chunk = chunk
            _detect_completed_stages(chunk, tracker)
            _infer_active_stage(tracker)
            record_incomplete_task(
                ticker,
                trade_date,
                status="paused" if tracker.is_paused else "running",
                completed_stages=tracker.completed_stages,
            )

            s = stats.get_stats()
            tracker.update_stats(s["llm_calls"], s["tool_calls"], s["tokens_in"], s["tokens_out"])

        if tracker.stop_requested:
            _close_and_discard()
            return

        if not last_chunk:
            raise RuntimeError("分析没有返回任何结果，请清理断点后重试。")

        signal = graph.finalize_graph_run(ticker, trade_date, last_chunk)
        if tracker.stop_requested:
            _close_and_discard()
            return

        tracker.mark_complete(last_chunk, signal)
        clear_incomplete_task(ticker, trade_date)
    finally:
        graph.close_graph_run()


def run_analysis_in_thread(
    ticker: str,
    trade_date: str,
    config: dict,
    tracker: ProgressTracker,
) -> threading.Thread:
    """Launch the pipeline in a daemon thread. Returns the thread handle."""
    tracker.ticker = ticker
    tracker.trade_date = trade_date
    tracker.is_running = True
    tracker.mark_stage_active("market")
    record_incomplete_task(
        ticker,
        trade_date,
        status="running",
        completed_stages=tracker.completed_stages,
    )

    def _target() -> None:
        try:
            _run(ticker, trade_date, config, tracker)
        except Exception as exc:
            if tracker.stop_requested:
                try:
                    _discard_stopped_run(ticker, trade_date, config, tracker)
                except Exception:
                    traceback.print_exc()
                return
            traceback.print_exc()
            record_incomplete_task(
                ticker,
                trade_date,
                status="error",
                error=str(exc),
                completed_stages=tracker.completed_stages,
            )
            tracker.mark_error(str(exc))

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    return t
