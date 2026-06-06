"""Track data tool calls that returned missing or failed data.

The analysis graph can continue even when a vendor endpoint returns an error or
partial result.  This module keeps those gaps visible after the LLM report is
finished, and lets the Web UI retry the exact tool calls later.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from langchain_core.messages import ToolMessage

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.dataflows.utils import safe_ticker_component


_MISSING_DATA_TASKS_FILE = Path.home() / ".tradingagents" / "missing_data_tasks.json"
_MISSING_DATA_CACHE_DIR = Path.home() / ".tradingagents" / "missing_data_cache"


STAGE_LABELS = {
    "market": ("技术分析", "market_report"),
    "social": ("情绪分析", "sentiment_report"),
    "news": ("新闻舆情", "news_report"),
    "fundamentals": ("基本面", "fundamentals_report"),
    "policy": ("政策分析", "policy_report"),
    "hot_money": ("游资追踪", "hot_money_report"),
    "lockup": ("解禁监控", "lockup_report"),
}

TOOL_LABELS = {
    "get_stock_data": "K线行情",
    "get_indicators": "技术指标",
    "get_fundamentals": "综合基本面",
    "get_balance_sheet": "资产负债表",
    "get_cashflow": "现金流量表",
    "get_income_statement": "利润表",
    "get_news": "个股新闻",
    "get_global_news": "宏观新闻",
    "get_insider_transactions": "股东/内部人交易",
    "get_profit_forecast": "机构一致预期",
    "get_hot_stocks": "热门股题材",
    "get_northbound_flow": "北向资金",
    "get_concept_blocks": "概念板块",
    "get_fund_flow": "个股资金流",
    "get_dragon_tiger_board": "龙虎榜",
    "get_lockup_expiry": "限售解禁",
    "get_industry_comparison": "行业对比",
}

_EXPLICIT_MISSING_RE = re.compile(r"\[数据缺失:\s*([^\]]+?)\s*\]")

_FAILURE_PATTERNS = [
    re.compile(r"^Error\b", re.IGNORECASE),
    re.compile(r"\bError (?:retrieving|fetching)\b", re.IGNORECASE),
    re.compile(r"\bNo data found\b", re.IGNORECASE),
    re.compile(r"\bNo data from\b", re.IGNORECASE),
    re.compile(r"\bNo OHLCV data\b", re.IGNORECASE),
    re.compile(r"\bAPI error\b", re.IGNORECASE),
    re.compile(r"查询失败"),
    re.compile(r"获取失败"),
    re.compile(r"获取为空"),
    re.compile(r"工具调用失败"),
    re.compile(r"无法获取"),
]


def _task_file() -> Path:
    return _MISSING_DATA_TASKS_FILE


def _cache_dir() -> Path:
    return _MISSING_DATA_CACHE_DIR


def _cache_path(task_id: str) -> Path:
    return _cache_dir() / f"{task_id}.txt"


def _write_cached_output(task_id: str, content: Any) -> Path:
    path = _cache_path(task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("" if content is None else str(content))
    tmp.replace(path)
    return path


def _read_cached_output(task_id: str) -> str | None:
    path = _cache_path(task_id)
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _load_index() -> list[dict[str, Any]]:
    path = _task_file()
    if not path.exists():
        return []

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(data, list):
        return []

    entries: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker", "")).strip().upper()
        trade_date = str(item.get("trade_date", "")).strip()
        task_id = str(item.get("id", "")).strip()
        if not ticker or not trade_date or not task_id:
            continue
        item["ticker"] = ticker
        item["trade_date"] = trade_date
        item["id"] = task_id
        entries.append(item)
    return entries


def _save_index(entries: list[dict[str, Any]]) -> None:
    path = _task_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2, default=str)
    tmp.replace(path)


def _normalize_args(args: Any) -> dict[str, Any]:
    if isinstance(args, dict):
        return dict(args)
    return {"value": args}


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _task_id(
    ticker: str,
    trade_date: str,
    stage: str,
    tool_name: str,
    args: dict[str, Any],
) -> str:
    raw = _stable_json(
        {
            "ticker": ticker.upper(),
            "trade_date": trade_date,
            "stage": stage,
            "tool_name": tool_name,
            "args": args,
        }
    )
    return "md_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _text_preview(text: str, limit: int = 500) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."


def _diagnose_result(content: Any, *, status: str = "success") -> dict[str, Any] | None:
    text = "" if content is None else str(content)
    markers = sorted({m.strip() for m in _EXPLICIT_MISSING_RE.findall(text) if m.strip()})
    failed = status == "error" or any(pattern.search(text) for pattern in _FAILURE_PATTERNS)

    if not markers and not failed:
        return None

    if not markers:
        markers = ["接口返回失败或空数据"]

    severity = "failed" if failed and not _EXPLICIT_MISSING_RE.search(text) else "partial"
    return {
        "severity": severity,
        "missing_items": markers,
        "message": _text_preview(text) or "工具调用没有返回可用内容",
    }


def _stage_info(stage: str) -> tuple[str, str]:
    return STAGE_LABELS.get(stage, (stage or "未知分析段", ""))


def _same_run(entry: dict[str, Any], ticker: str, trade_date: str) -> bool:
    return (
        str(entry.get("ticker", "")).upper() == ticker.upper()
        and str(entry.get("trade_date", "")) == trade_date
    )


def reset_missing_tasks_for_run(ticker: str, trade_date: str) -> None:
    """Clear prior active tasks when a fresh full analysis starts.

    Resolved retry outputs are preserved so the next full reanalysis can reuse
    the data that was just recovered from flaky endpoints.
    """
    ticker = ticker.strip().upper()
    trade_date = trade_date.strip()
    entries = [
        entry
        for entry in _load_index()
        if not _same_run(entry, ticker, trade_date) or entry.get("status") != "active"
    ]
    _save_index(entries)


def record_tool_result(
    *,
    ticker: str,
    trade_date: str,
    stage: str,
    tool_name: str,
    args: Any,
    content: Any,
    status: str = "success",
    retry_attempt: bool = False,
) -> dict[str, Any] | None:
    """Record or resolve a missing-data task based on one tool result."""
    ticker = (ticker or "").strip().upper()
    trade_date = (trade_date or "").strip()
    if not ticker or not trade_date or not tool_name:
        return None

    normalized_args = _normalize_args(args)
    task_id = _task_id(ticker, trade_date, stage, tool_name, normalized_args)
    diagnosis = _diagnose_result(content, status=status)
    entries = _load_index()
    now = time.time()

    if diagnosis is None:
        changed = False
        for entry in entries:
            if entry.get("id") != task_id or entry.get("status") != "active":
                continue
            entry["status"] = "resolved"
            entry["resolved_at"] = now
            entry["updated_at"] = now
            entry["last_result_preview"] = _text_preview(str(content))
            if retry_attempt:
                cached_path = _write_cached_output(task_id, content)
                entry["resolved_output_path"] = str(cached_path)
                entry["resolved_output_chars"] = len("" if content is None else str(content))
                entry["retry_attempts"] = int(entry.get("retry_attempts", 0)) + 1
                entry["last_retry_at"] = now
            changed = True
        if changed:
            _save_index(entries)
        return None

    stage_label, report_key = _stage_info(stage)
    existing = next((entry for entry in entries if entry.get("id") == task_id), None)
    task = existing or {
        "id": task_id,
        "ticker": ticker,
        "trade_date": trade_date,
        "stage": stage,
        "stage_label": stage_label,
        "report_key": report_key,
        "tool_name": tool_name,
        "tool_label": TOOL_LABELS.get(tool_name, tool_name),
        "args": normalized_args,
        "first_seen": now,
        "retry_attempts": 0,
    }

    task.update(
        {
            "status": "active",
            "severity": diagnosis["severity"],
            "missing_items": diagnosis["missing_items"],
            "message": diagnosis["message"],
            "updated_at": now,
            "resolved_at": None,
            "needs_reanalysis": True,
        }
    )
    if retry_attempt:
        task["retry_attempts"] = int(task.get("retry_attempts", 0)) + 1
        task["last_retry_at"] = now

    if existing is None:
        entries.append(task)

    entries.sort(key=lambda item: float(item.get("updated_at", 0)), reverse=True)
    _save_index(entries)
    return task


def cached_retry_output(
    *,
    ticker: str,
    trade_date: str,
    stage: str,
    tool_name: str,
    args: Any,
) -> str | None:
    """Return a successful retry output for the exact tool call, if any."""
    ticker = (ticker or "").strip().upper()
    trade_date = (trade_date or "").strip()
    if not ticker or not trade_date or not tool_name:
        return None

    normalized_args = _normalize_args(args)
    task_id = _task_id(ticker, trade_date, stage, tool_name, normalized_args)
    entries = _load_index()
    for entry in entries:
        if entry.get("id") != task_id or entry.get("status") != "resolved":
            continue
        output = _read_cached_output(task_id)
        if output is not None:
            entry["used_in_reanalysis_at"] = time.time()
            _save_index(entries)
            return output
    return None


def _request_context(stage: str, request: Any) -> tuple[str, str, str, dict[str, Any], str]:
    state = getattr(request, "state", None) or {}
    ticker = str(state.get("company_of_interest", "")).strip().upper()
    trade_date = str(state.get("trade_date", "")).strip()
    tool_call = getattr(request, "tool_call", {}) or {}
    tool_name = str(tool_call.get("name", ""))
    args = tool_call.get("args", {})
    tool_call_id = str(tool_call.get("id", ""))
    return ticker, trade_date, tool_name, _normalize_args(args), tool_call_id


def record_tool_response(stage: str, request: Any, response: Any) -> None:
    """LangGraph ToolNode wrapper hook."""
    try:
        ticker, trade_date, tool_name, args, _ = _request_context(stage, request)

        responses = response if isinstance(response, list) else [response]
        for item in responses:
            content = getattr(item, "content", "")
            status = getattr(item, "status", "success")
            record_tool_result(
                ticker=ticker,
                trade_date=trade_date,
                stage=stage,
                tool_name=tool_name,
                args=args,
                content=content,
                status=status,
            )
    except Exception:
        # Recording missing data should never break the analysis graph.
        return


def make_tool_call_recorder(stage: str):
    """Create a ToolNode wrapper that records missing data after execution."""

    def _wrapper(request: Any, execute: Any) -> Any:
        ticker, trade_date, tool_name, args, tool_call_id = _request_context(stage, request)
        cached = cached_retry_output(
            ticker=ticker,
            trade_date=trade_date,
            stage=stage,
            tool_name=tool_name,
            args=args,
        )
        if cached is not None and tool_call_id:
            return ToolMessage(
                content=cached,
                name=tool_name,
                tool_call_id=tool_call_id,
                status="success",
            )

        response = execute(request)
        record_tool_response(stage, request, response)
        return response

    return _wrapper


def get_missing_tasks(
    ticker: str,
    trade_date: str,
    *,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    """Return missing-data tasks for one ticker/date."""
    ticker = ticker.strip().upper()
    trade_date = trade_date.strip()
    tasks = [
        entry
        for entry in _load_index()
        if _same_run(entry, ticker, trade_date)
        and (not active_only or entry.get("status") == "active")
    ]
    tasks.sort(key=lambda item: (str(item.get("stage", "")), str(item.get("tool_name", ""))))
    return tasks


def get_resolved_tasks(ticker: str, trade_date: str) -> list[dict[str, Any]]:
    """Return successfully retried tasks for one ticker/date."""
    ticker = ticker.strip().upper()
    trade_date = trade_date.strip()
    tasks = [
        entry
        for entry in _load_index()
        if _same_run(entry, ticker, trade_date) and entry.get("status") == "resolved"
    ]
    tasks.sort(key=lambda item: float(item.get("resolved_at", 0)), reverse=True)
    return tasks


def mark_resolved_tasks_consumed(ticker: str, trade_date: str) -> None:
    """Archive resolved retry outputs after a fresh full analysis completes."""
    ticker = ticker.strip().upper()
    trade_date = trade_date.strip()
    entries = _load_index()
    changed = False
    now = time.time()

    for entry in entries:
        if not _same_run(entry, ticker, trade_date) or entry.get("status") != "resolved":
            continue
        entry["status"] = "consumed"
        entry["consumed_at"] = now
        cache_path = entry.get("resolved_output_path")
        if cache_path:
            try:
                Path(cache_path).unlink(missing_ok=True)
            except OSError:
                pass
        changed = True

    if changed:
        _save_index(entries)


def attach_missing_data_snapshot(
    final_state: dict[str, Any],
    ticker: str,
    trade_date: str,
    *,
    requires_reanalysis: bool = False,
) -> dict[str, Any]:
    """Attach the current active missing-data snapshot to a final state."""
    tasks = get_missing_tasks(ticker, trade_date, active_only=True)
    resolved_tasks = get_resolved_tasks(ticker, trade_date)
    final_state["missing_data_tasks"] = tasks
    final_state["missing_data_complete"] = len(tasks) == 0
    final_state["missing_data_resolved_count"] = len(resolved_tasks)
    final_state["missing_data_requires_reanalysis"] = bool(requires_reanalysis)
    final_state["missing_data_updated_at"] = time.time()
    return final_state


def analysis_log_path(ticker: str, trade_date: str) -> Path:
    safe_ticker = safe_ticker_component(ticker)
    return (
        Path(DEFAULT_CONFIG["results_dir"])
        / safe_ticker
        / "TradingAgentsStrategy_logs"
        / f"full_states_log_{trade_date}.json"
    )


def sync_missing_snapshot_to_analysis_log(
    ticker: str,
    trade_date: str,
    *,
    requires_reanalysis: bool | None = None,
) -> None:
    """Update an already-saved report JSON with the latest missing-data snapshot."""
    path = analysis_log_path(ticker, trade_date)
    if not path.exists():
        return

    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError):
        return

    if requires_reanalysis is None:
        requires_reanalysis = bool(state.get("missing_data_requires_reanalysis", False))
    attach_missing_data_snapshot(
        state,
        ticker,
        trade_date,
        requires_reanalysis=bool(requires_reanalysis),
    )
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=4, default=str)
    tmp.replace(path)


def _tool_registry() -> dict[str, Any]:
    from tradingagents.agents.utils.agent_utils import (
        get_balance_sheet,
        get_cashflow,
        get_concept_blocks,
        get_dragon_tiger_board,
        get_fund_flow,
        get_fundamentals,
        get_global_news,
        get_hot_stocks,
        get_income_statement,
        get_indicators,
        get_industry_comparison,
        get_insider_transactions,
        get_lockup_expiry,
        get_news,
        get_northbound_flow,
        get_profit_forecast,
        get_stock_data,
    )

    tools = [
        get_stock_data,
        get_indicators,
        get_fundamentals,
        get_balance_sheet,
        get_cashflow,
        get_income_statement,
        get_news,
        get_global_news,
        get_insider_transactions,
        get_profit_forecast,
        get_hot_stocks,
        get_northbound_flow,
        get_concept_blocks,
        get_fund_flow,
        get_dragon_tiger_board,
        get_lockup_expiry,
        get_industry_comparison,
    ]
    return {tool.name: tool for tool in tools}


def retry_missing_tasks(
    ticker: str,
    trade_date: str,
    *,
    task_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Retry active missing-data tool calls.

    Returns a summary with resolved/unresolved task records.  The analysis report
    itself is not mutated here; if all missing tasks resolve, the Web UI can kick
    off a fresh full analysis so downstream decisions are regenerated from the
    now-complete data.
    """
    selected = set(task_ids or [])
    tasks = [
        task
        for task in get_missing_tasks(ticker, trade_date, active_only=True)
        if not selected or task["id"] in selected
    ]

    registry = _tool_registry()
    resolved: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for task in tasks:
        tool = registry.get(task.get("tool_name"))
        if tool is None:
            task["message"] = f"找不到工具: {task.get('tool_name')}"
            unresolved.append(task)
            continue

        try:
            output = tool.invoke(task.get("args") or {})
            new_task = record_tool_result(
                ticker=ticker,
                trade_date=trade_date,
                stage=str(task.get("stage", "")),
                tool_name=str(task.get("tool_name", "")),
                args=task.get("args") or {},
                content=output,
                status="success",
                retry_attempt=True,
            )
            if new_task is None:
                resolved.append({**task, "last_result_preview": _text_preview(str(output))})
            else:
                unresolved.append(new_task)
        except Exception as exc:
            new_task = record_tool_result(
                ticker=ticker,
                trade_date=trade_date,
                stage=str(task.get("stage", "")),
                tool_name=str(task.get("tool_name", "")),
                args=task.get("args") or {},
                content=f"{type(exc).__name__}: {exc}",
                status="error",
                retry_attempt=True,
            )
            unresolved.append(new_task or task)

    remaining = get_missing_tasks(ticker, trade_date, active_only=True)
    sync_missing_snapshot_to_analysis_log(
        ticker,
        trade_date,
        requires_reanalysis=bool(resolved),
    )
    return {
        "attempted": len(tasks),
        "resolved": resolved,
        "unresolved": unresolved,
        "remaining": remaining,
        "remaining_count": len(remaining),
        "resolved_count": len(resolved),
    }
