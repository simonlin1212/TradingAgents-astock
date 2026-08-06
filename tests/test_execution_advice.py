"""Unit tests for the Execution Advisor node.

Covers the price-snapshot derivation (mock vendor CSV), the non-buy
placeholder path (no LLM call), and the buy path where the LLM proposes
price levels that are validated and sized deterministically.
"""

from unittest.mock import MagicMock

import pytest

from tradingagents.agents.managers import execution_advisor as ea
from tradingagents.agents.schemas import ExecutionAdvice

# Same shape the a_stock vendor returns: # comment headers + CSV body.
OHLCV_CSV = """# Stock data for 600519 (A-stock)
# Total records: 3
Date,Open,High,Low,Close,Volume
2026-08-01,10.0,10.5,9.8,10.2,10000
2026-08-02,10.2,10.6,9.9,10.4,12000
2026-08-03,10.4,10.8,9.9,10.0,11000
"""


@pytest.mark.unit
class TestPriceSnapshot:
    def test_parse_and_derive(self, monkeypatch):
        monkeypatch.setattr(ea, "route_to_vendor", lambda *a, **k: OHLCV_CSV)
        snap = ea._fetch_price_snapshot("600519", "2026-08-03")
        assert snap is not None
        assert snap["price"] == 10.0          # last close
        assert snap["high20"] == 10.8
        assert snap["low20"] == 9.8
        # TR: row1 (no prev close) = high-low = 0.7; row2 = 0.7; row3 = 0.9
        # ATR(14) over 3 rows = mean(0.7, 0.7, 0.9) = 2.3/3
        assert snap["atr"] == pytest.approx(2.3 / 3)

    def test_vendor_failure_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            ea, "route_to_vendor",
            lambda *a, **k: "K线数据获取失败：mootdx和新浪备用源均不可用",
        )
        assert ea._fetch_price_snapshot("600519", "2026-08-03") is None

    def test_exception_returns_none(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("network down")

        monkeypatch.setattr(ea, "route_to_vendor", boom)
        assert ea._fetch_price_snapshot("600519", "2026-08-03") is None


def _state(rating_text="**Rating**: Buy\n\n**Executive Summary**: s"):
    return {
        "company_of_interest": "600519",
        "trade_date": "2026-08-03",
        "final_trade_decision": rating_text,
        "trader_investment_plan": "FINAL TRANSACTION PROPOSAL: **BUY**",
    }


@pytest.mark.unit
class TestExecutionAdvisorNode:
    def test_sell_rating_placeholder_and_no_llm(self, monkeypatch):
        monkeypatch.setattr(ea, "route_to_vendor", lambda *a, **k: OHLCV_CSV)
        llm = MagicMock()
        node = ea.create_execution_advisor(llm)
        out = node(_state("**Rating**: Sell"))
        assert "Position Size**: 0%" in out["execution_advice"]
        assert "离场" in out["execution_advice"]
        llm.invoke.assert_not_called()

    def test_hold_rating_placeholder(self, monkeypatch):
        monkeypatch.setattr(ea, "route_to_vendor", lambda *a, **k: OHLCV_CSV)
        node = ea.create_execution_advisor(MagicMock())
        out = node(_state("**Rating**: Hold"))
        assert "Position Size**: 0%" in out["execution_advice"]

    def test_buy_rating_structured_levels_and_size(self, monkeypatch):
        monkeypatch.setattr(ea, "route_to_vendor", lambda *a, **k: OHLCV_CSV)
        llm = MagicMock()
        structured = MagicMock()
        structured.invoke.return_value = ExecutionAdvice(
            entry_zone="9.8 - 10.2", stop_loss=9.0, target_price=11.5,
            rationale="near support",
        )
        llm.with_structured_output.return_value = structured
        node = ea.create_execution_advisor(llm)

        out = node(_state())
        text = out["execution_advice"]
        assert "**Entry Zone**: 9.8 - 10.2" in text
        assert "**Stop Loss**: 9.0" in text
        assert "**Target Price**: 11.5" in text
        # 1.5% budget / 10% stop distance = 15% — deterministic, not from LLM
        assert "**Position Size**: 15.0%" in text

    def test_buy_rating_invalid_levels_rejected(self, monkeypatch):
        monkeypatch.setattr(ea, "route_to_vendor", lambda *a, **k: OHLCV_CSV)
        llm = MagicMock()
        structured = MagicMock()
        structured.invoke.return_value = ExecutionAdvice(
            entry_zone="9.8 - 10.2", stop_loss=10.5, target_price=9.0,
            rationale="bad levels",
        )
        llm.with_structured_output.return_value = structured
        node = ea.create_execution_advisor(llm)

        out = node(_state())
        assert "N/A" in out["execution_advice"]
        assert "Position Size**: 0.0%" in out["execution_advice"]

    def test_buy_rating_without_price_snapshot_placeholder(self, monkeypatch):
        monkeypatch.setattr(
            ea, "route_to_vendor",
            lambda *a, **k: "K线数据获取失败：mootdx和新浪备用源均不可用",
        )
        llm = MagicMock()
        node = ea.create_execution_advisor(llm)
        out = node(_state())
        assert "Position Size**: 0%" in out["execution_advice"]
        llm.invoke.assert_not_called()
