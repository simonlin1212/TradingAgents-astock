"""Background thread runner for TradingAgentsGraph pipeline."""

from __future__ import annotations

import re
import threading
from typing import Any

from web.progress import PIPELINE_STAGES, ProgressTracker
from web.stock_display import normalize_report_state_mentions, normalize_stock_mentions


_REPORT_KEY_TO_STAGE = {s["report_key"]: s["id"] for s in PIPELINE_STAGES}

_ANALYST_REPORT_KEYS = [
    "market_report", "sentiment_report", "news_report",
    "fundamentals_report", "policy_report", "hot_money_report", "lockup_report",
]


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
            report = normalize_stock_mentions(str(content), tracker.ticker, chunk)
            tracker.mark_stage_done(stage_id, _strip_think_tags(report))

    dqs = chunk.get("data_quality_summary", "")
    if dqs and tracker.stage_status("quality_gate") != "done":
        tracker.mark_stage_done("quality_gate", normalize_stock_mentions(str(dqs), tracker.ticker, chunk))

    debate = chunk.get("investment_debate_state")
    if debate and isinstance(debate, dict):
        judge = debate.get("judge_decision", "")
        if judge and tracker.stage_status("debate") != "done":
            tracker.mark_stage_done("debate", normalize_stock_mentions(str(judge), tracker.ticker, chunk))

    trader_plan = chunk.get("trader_investment_plan", "")
    if trader_plan and tracker.stage_status("trader") != "done":
        report = normalize_stock_mentions(str(trader_plan), tracker.ticker, chunk)
        tracker.mark_stage_done("trader", _strip_think_tags(report))

    risk = chunk.get("risk_debate_state")
    if risk and isinstance(risk, dict):
        risk_judge = risk.get("judge_decision", "")
        if risk_judge and tracker.stage_status("risk") != "done":
            tracker.mark_stage_done("risk", normalize_stock_mentions(str(risk_judge), tracker.ticker, chunk))

    final = chunk.get("final_trade_decision", "")
    if final and tracker.stage_status("pm") != "done":
        report = normalize_stock_mentions(str(final), tracker.ticker, chunk)
        tracker.mark_stage_done("pm", _strip_think_tags(report))


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

    init_state = graph.propagator.create_initial_state(ticker, trade_date)
    args = graph.propagator.get_graph_args(callbacks=[stats])

    last_chunk: dict[str, Any] = {}

    for chunk in graph.graph.stream(init_state, **args):
        last_chunk = chunk
        _detect_completed_stages(chunk, tracker)
        _infer_active_stage(tracker)

        s = stats.get_stats()
        tracker.update_stats(s["llm_calls"], s["tool_calls"], s["tokens_in"], s["tokens_out"])

    signal = graph.process_signal(last_chunk.get("final_trade_decision", ""))

    normalize_report_state_mentions(last_chunk, ticker)
    graph.ticker = ticker
    graph._log_state(trade_date, last_chunk)

    tracker.mark_complete(last_chunk, signal)


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

    def _target() -> None:
        try:
            _run(ticker, trade_date, config, tracker)
        except Exception as exc:
            tracker.mark_error(str(exc))

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    return t
