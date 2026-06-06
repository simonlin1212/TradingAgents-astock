"""Tests for missing-data task recording and retry helpers."""

from __future__ import annotations

from pathlib import Path
import sys
import types
from unittest.mock import MagicMock

import pytest

messages_stub = types.ModuleType("langchain_core.messages")
messages_stub.ToolMessage = type("ToolMessage", (), {})
langchain_stub = types.ModuleType("langchain_core")
langchain_stub.messages = messages_stub
dataflow_utils_stub = types.ModuleType("tradingagents.dataflows.utils")
dataflow_utils_stub.safe_ticker_component = lambda value: str(value).strip().upper()
sys.modules.setdefault("langchain_core", langchain_stub)
sys.modules.setdefault("langchain_core.messages", messages_stub)
sys.modules.setdefault("tradingagents.dataflows.utils", dataflow_utils_stub)

from tradingagents.dataflows import missing_data


@pytest.fixture()
def missing_index(tmp_path, monkeypatch):
    index = tmp_path / "missing_data_tasks.json"
    cache_dir = tmp_path / "missing_data_cache"
    monkeypatch.setattr(missing_data, "_MISSING_DATA_TASKS_FILE", index)
    monkeypatch.setattr(missing_data, "_MISSING_DATA_CACHE_DIR", cache_dir)
    return index


def test_records_explicit_missing_items(missing_index):
    task = missing_data.record_tool_result(
        ticker="300476",
        trade_date="2026-06-03",
        stage="fundamentals",
        tool_name="get_fundamentals",
        args={"ticker": "300476", "curr_date": "2026-06-03"},
        content="| ROE | -- | [数据缺失: ROE] |\n| EPS | -- | [数据缺失: 机构一致预期EPS] |",
    )

    assert task is not None
    assert task["ticker"] == "300476"
    assert task["stage_label"] == "基本面"
    assert task["tool_label"] == "综合基本面"
    assert task["missing_items"] == ["ROE", "机构一致预期EPS"]

    tasks = missing_data.get_missing_tasks("300476", "2026-06-03")
    assert [t["id"] for t in tasks] == [task["id"]]


def test_successful_retry_resolves_task(missing_index, monkeypatch):
    task = missing_data.record_tool_result(
        ticker="300476",
        trade_date="2026-06-03",
        stage="market",
        tool_name="get_indicators",
        args={"symbol": "300476", "curr_date": "2026-06-03", "look_back_days": 90},
        content="Error retrieving technical summary for 300476: timeout",
    )
    assert task is not None

    fake_tool = MagicMock()
    fake_tool.invoke.return_value = "最新收盘价: 12.34\n| 指标 | 数值 |\n|---|---|\n| RSI | 55 |"
    monkeypatch.setattr(missing_data, "_tool_registry", lambda: {"get_indicators": fake_tool})
    monkeypatch.setattr(
        missing_data,
        "sync_missing_snapshot_to_analysis_log",
        lambda ticker, date, **kwargs: None,
    )

    result = missing_data.retry_missing_tasks("300476", "2026-06-03")

    assert result["attempted"] == 1
    assert result["resolved_count"] == 1
    assert result["remaining_count"] == 0
    fake_tool.invoke.assert_called_once_with(task["args"])

    all_tasks = missing_data.get_missing_tasks("300476", "2026-06-03", active_only=False)
    assert all_tasks[0]["status"] == "resolved"
    assert all_tasks[0]["retry_attempts"] == 1


def test_retry_keeps_unresolved_task_when_still_missing(missing_index, monkeypatch):
    missing_data.record_tool_result(
        ticker="300476",
        trade_date="2026-06-03",
        stage="fundamentals",
        tool_name="get_profit_forecast",
        args={"ticker": "300476"},
        content="[数据缺失: 机构一致预期EPS]",
    )

    fake_tool = MagicMock()
    fake_tool.invoke.return_value = "[数据缺失: 机构一致预期EPS]"
    monkeypatch.setattr(missing_data, "_tool_registry", lambda: {"get_profit_forecast": fake_tool})
    monkeypatch.setattr(
        missing_data,
        "sync_missing_snapshot_to_analysis_log",
        lambda ticker, date, **kwargs: None,
    )

    result = missing_data.retry_missing_tasks("300476", "2026-06-03")

    assert result["resolved_count"] == 0
    assert result["remaining_count"] == 1
    assert result["remaining"][0]["status"] == "active"
    assert result["remaining"][0]["retry_attempts"] == 1


def test_snapshot_sync_updates_saved_report(missing_index, tmp_path, monkeypatch):
    log_path = tmp_path / "full_states_log_2026-06-03.json"
    log_path.write_text('{"final_trade_decision": "HOLD"}', encoding="utf-8")
    monkeypatch.setattr(missing_data, "analysis_log_path", lambda ticker, date: Path(log_path))

    missing_data.record_tool_result(
        ticker="300476",
        trade_date="2026-06-03",
        stage="news",
        tool_name="get_news",
        args={"ticker": "300476", "start_date": "2026-05-27", "end_date": "2026-06-03"},
        content="Error fetching news for 300476: timeout",
    )

    missing_data.sync_missing_snapshot_to_analysis_log("300476", "2026-06-03")

    text = log_path.read_text(encoding="utf-8")
    assert '"missing_data_complete": false' in text
    assert '"tool_name": "get_news"' in text


def test_cached_retry_output_is_available_for_reanalysis(missing_index, monkeypatch):
    args = {"symbol": "300476", "curr_date": "2026-06-03", "look_back_days": 90}
    missing_data.record_tool_result(
        ticker="300476",
        trade_date="2026-06-03",
        stage="market",
        tool_name="get_indicators",
        args=args,
        content="Error retrieving technical summary for 300476: timeout",
    )

    fake_tool = MagicMock()
    fake_tool.invoke.return_value = "补齐后的技术摘要"
    monkeypatch.setattr(missing_data, "_tool_registry", lambda: {"get_indicators": fake_tool})
    monkeypatch.setattr(
        missing_data,
        "sync_missing_snapshot_to_analysis_log",
        lambda ticker, date, **kwargs: None,
    )

    missing_data.retry_missing_tasks("300476", "2026-06-03")

    output = missing_data.cached_retry_output(
        ticker="300476",
        trade_date="2026-06-03",
        stage="market",
        tool_name="get_indicators",
        args=args,
    )

    assert output == "补齐后的技术摘要"
    all_tasks = missing_data.get_missing_tasks("300476", "2026-06-03", active_only=False)
    assert all_tasks[0]["used_in_reanalysis_at"] is not None


def test_consumed_resolved_task_removes_cached_output(missing_index, monkeypatch):
    args = {"symbol": "300476", "curr_date": "2026-06-03", "look_back_days": 90}
    task = missing_data.record_tool_result(
        ticker="300476",
        trade_date="2026-06-03",
        stage="market",
        tool_name="get_indicators",
        args=args,
        content="Error retrieving technical summary for 300476: timeout",
    )
    assert task is not None

    fake_tool = MagicMock()
    fake_tool.invoke.return_value = "补齐后的技术摘要"
    monkeypatch.setattr(missing_data, "_tool_registry", lambda: {"get_indicators": fake_tool})
    monkeypatch.setattr(
        missing_data,
        "sync_missing_snapshot_to_analysis_log",
        lambda ticker, date, **kwargs: None,
    )

    missing_data.retry_missing_tasks("300476", "2026-06-03")
    resolved = missing_data.get_resolved_tasks("300476", "2026-06-03")
    cache_path = Path(resolved[0]["resolved_output_path"])
    assert cache_path.exists()

    missing_data.mark_resolved_tasks_consumed("300476", "2026-06-03")

    assert not cache_path.exists()
    all_tasks = missing_data.get_missing_tasks("300476", "2026-06-03", active_only=False)
    assert all_tasks[0]["status"] == "consumed"
    assert (
        missing_data.cached_retry_output(
            ticker="300476",
            trade_date="2026-06-03",
            stage="market",
            tool_name="get_indicators",
            args=args,
        )
        is None
    )
