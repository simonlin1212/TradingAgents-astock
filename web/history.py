"""Manage completed and incomplete analysis history."""

from __future__ import annotations

import json
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from tradingagents.default_config import DEFAULT_CONFIG


_INCOMPLETE_TASKS_FILE = Path.home() / ".tradingagents" / "incomplete_tasks.json"
# 带超时的锁：Streamlit runOnSave 中断脚本线程时不会释放 threading.Lock，
# 用超时 + try/finally 避免 dev 模式编辑文件导致的永久死锁。
_INCOMPLETE_TASKS_LOCK = threading.Lock()
_INCOMPLETE_TASKS_LOCK_TIMEOUT = 5.0  # 秒


class _LockAcquireError(RuntimeError):
    """获取 incomplete-tasks 锁超时时抛出，调用方可降级处理。"""


def _acquire_incomplete_lock():
    """获取锁，超时抛出 _LockAcquireError。必须配 try/finally 释放。"""
    if not _INCOMPLETE_TASKS_LOCK.acquire(timeout=_INCOMPLETE_TASKS_LOCK_TIMEOUT):
        raise _LockAcquireError(
            f"无法获取 incomplete_tasks 锁（超过 {_INCOMPLETE_TASKS_LOCK_TIMEOUT}s）。"
            "可能是上次脚本被 Streamlit 中断时未释放锁，请重启 Streamlit 服务。"
        )


def _results_dir() -> Path:
    return Path.home() / ".tradingagents" / "logs"


def get_history() -> list[dict[str, str]]:
    """Scan saved analysis logs and return a sorted list (newest first).

    Each entry: {"ticker": "300750", "date": "2026-05-12", "path": "/abs/path/...json"}
    """
    root = _results_dir()
    if not root.exists():
        return []

    entries: list[dict[str, str]] = []
    for log_file in root.rglob("full_states_log_*.json"):
        match = re.search(r"full_states_log_(\d{4}-\d{2}-\d{2})\.json$", log_file.name)
        if not match:
            continue
        date = match.group(1)
        ticker = log_file.parent.parent.name
        entries.append({"ticker": ticker, "date": date, "path": str(log_file)})

    entries.sort(key=lambda e: e["date"], reverse=True)
    return entries


def _completed_key(ticker: str, trade_date: str) -> tuple[str, str]:
    return ticker.upper(), trade_date


def _completed_keys() -> set[tuple[str, str]]:
    return {
        _completed_key(entry["ticker"], entry["date"])
        for entry in get_history()
    }


def _load_incomplete_index() -> list[dict[str, Any]]:
    if not _INCOMPLETE_TASKS_FILE.exists():
        return []

    try:
        with open(_INCOMPLETE_TASKS_FILE, encoding="utf-8") as f:
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
        if not ticker or not re.match(r"^\d{4}-\d{2}-\d{2}$", trade_date):
            continue
        item["ticker"] = ticker
        item["trade_date"] = trade_date
        entries.append(item)
    return entries


def _save_incomplete_index(entries: list[dict[str, Any]]) -> None:
    parent = _INCOMPLETE_TASKS_FILE.parent
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=parent,
        prefix=f"{_INCOMPLETE_TASKS_FILE.stem}.",
        suffix=".tmp",
        delete=False,
    ) as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
        tmp = Path(f.name)
    tmp.replace(_INCOMPLETE_TASKS_FILE)


def _checkpoint_step(ticker: str, trade_date: str) -> int | None:
    try:
        from tradingagents.graph.checkpointer import checkpoint_step

        return checkpoint_step(DEFAULT_CONFIG["data_cache_dir"], ticker, trade_date)
    except Exception:
        return None


def record_incomplete_task(
    ticker: str,
    trade_date: str,
    *,
    status: str,
    error: str | None = None,
    completed_stages: list[str] | None = None,
) -> None:
    """Upsert a resumable task entry."""
    ticker = ticker.strip().upper()
    trade_date = trade_date.strip()
    if not ticker or not trade_date:
        return

    _acquire_incomplete_lock()
    try:
        entries = [
            entry
            for entry in _load_incomplete_index()
            if _completed_key(entry["ticker"], entry["trade_date"])
            != _completed_key(ticker, trade_date)
        ]
        now = time.time()
        entries.append(
            {
                "ticker": ticker,
                "trade_date": trade_date,
                "status": status,
                "error": error or "",
                "completed_stages": completed_stages or [],
                "updated_at": now,
            }
        )
        entries.sort(key=lambda e: float(e.get("updated_at", 0)), reverse=True)
        _save_incomplete_index(entries)
    finally:
        _INCOMPLETE_TASKS_LOCK.release()


def clear_incomplete_task(ticker: str, trade_date: str) -> None:
    """Remove an incomplete task once it completes successfully.

    锁获取超时会抛出 _LockAcquireError，调用方应捕获并降级处理
    （例如显示提示让用户重启 Streamlit 服务），不要让整个应用卡死。
    """
    ticker = ticker.strip().upper()
    trade_date = trade_date.strip()
    _acquire_incomplete_lock()
    try:
        entries = [
            entry
            for entry in _load_incomplete_index()
            if _completed_key(entry["ticker"], entry["trade_date"])
            != _completed_key(ticker, trade_date)
        ]
        _save_incomplete_index(entries)
    finally:
        _INCOMPLETE_TASKS_LOCK.release()


def get_incomplete_history() -> list[dict[str, Any]]:
    """Return unfinished tasks that can be resumed from their checkpoint.

    锁获取超时时返回空列表（降级），避免阻塞 sidebar 渲染导致整个应用无响应。
    """
    completed = _completed_keys()
    active_entries: list[dict[str, Any]] = []

    try:
        _acquire_incomplete_lock()
    except _LockAcquireError:
        # 锁被占用（通常是 dev 模式编辑文件触发的死锁），降级返回空列表
        return active_entries

    try:
        entries = _load_incomplete_index()
        for entry in entries:
            key = _completed_key(entry["ticker"], entry["trade_date"])
            if key in completed:
                continue

            step = _checkpoint_step(entry["ticker"], entry["trade_date"])
            entry["checkpoint_step"] = step
            active_entries.append(entry)

        active_entries.sort(key=lambda e: float(e.get("updated_at", 0)), reverse=True)
        if len(active_entries) != len(entries):
            _save_incomplete_index(active_entries)
    finally:
        _INCOMPLETE_TASKS_LOCK.release()
    return active_entries


def load_analysis(path: str) -> dict[str, Any]:
    """Load a saved analysis JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def extract_signal(state: dict[str, Any]) -> str:
    """Extract the 5-tier rating from a final state dict for history reload.

    Delegates to the shared ``parse_rating`` heuristic so the history-reload
    display matches the live signal (``TradingAgentsGraph.process_signal``) and
    understands Chinese free-text decisions — not just English keywords. The
    old English-only ``BUY/SELL/HOLD`` scan silently returned Hold/N/A for
    every Chinese-output run (issues #78 / #80). ``final_trade_decision`` is
    checked first so the reload matches the authoritative live signal.
    """
    import re

    from tradingagents.agents.utils.rating import parse_rating

    _UNKNOWN = ""
    for field in (
        "final_trade_decision",
        "trader_investment_decision",
        "investment_plan",
    ):
        text = state.get(field, "")
        if not text:
            continue
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        rating = parse_rating(cleaned, default=_UNKNOWN)
        if rating:
            return rating
    return "N/A"
