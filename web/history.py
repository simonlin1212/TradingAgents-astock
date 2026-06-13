"""Manage analysis history by scanning existing log files."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def _results_dir() -> Path:
    return Path.home() / ".tradingagents" / "logs"


def get_history() -> list[dict[str, str]]:
    """Scan saved analysis logs and return a sorted list (newest first).

    Each entry includes ticker/code, stock_name and minute-level timestamp.
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
        stock_name = ticker
        timestamp = datetime.fromtimestamp(log_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        sort_time = timestamp
        try:
            with open(log_file, encoding="utf-8") as f:
                state = json.load(f)
            stock_name = (
                str(state.get("stock_name") or "").strip()
                or str(state.get("company_of_interest") or "").strip()
                or ticker
            )
            generated_at = str(state.get("generated_at") or "").strip()
            if generated_at:
                try:
                    sort_dt = datetime.strptime(generated_at, "%Y-%m-%d %H:%M:%S")
                    timestamp = sort_dt.strftime("%Y-%m-%d %H:%M")
                    sort_time = sort_dt.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    pass
        except Exception:
            pass

        entries.append(
            {
                "ticker": ticker,
                "stock_name": stock_name,
                "date": date,
                "timestamp": timestamp,
                "sort_time": sort_time,
                "path": str(log_file),
            }
        )

    entries.sort(key=lambda e: e.get("sort_time", e.get("timestamp", e["date"])), reverse=True)
    return entries


def load_analysis(path: str) -> dict[str, Any]:
    """Load a saved analysis JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def extract_signal(state: dict[str, Any]) -> str:
    """Extract the short signal (Buy/Sell/Hold) from a final state dict."""
    import re

    for field in (
        "investment_plan",
        "trader_investment_decision",
        "final_trade_decision",
    ):
        text = state.get(field, "")
        if not text:
            continue
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        for keyword in ("BUY", "SELL", "HOLD"):
            if keyword in cleaned.upper():
                return keyword.capitalize()
    return "N/A"
