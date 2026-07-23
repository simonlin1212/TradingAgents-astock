"""Tests for the configurable market analysis window (#16).

The Web sidebar / CLI derive ``market_lookback_days`` from a user-picked start
date and put it on the config; the market analyst reads it back via
``get_config()`` and injects it into its prompt so get_stock_data /
get_indicators cover the requested window (default: first of the analysis
month → "monthly" view).
"""

import datetime

import pytest

from tradingagents.dataflows.config import get_config, set_config
from tradingagents.default_config import DEFAULT_CONFIG


@pytest.mark.unit
class TestMarketLookbackConfig:
    def test_default_config_has_key_and_is_none(self):
        assert "market_lookback_days" in DEFAULT_CONFIG
        assert DEFAULT_CONFIG["market_lookback_days"] is None

    def test_market_analyst_reads_configured_value(self):
        # Mirrors `lookback = get_config().get("market_lookback_days") or 30`.
        set_config({"market_lookback_days": 15})
        assert (get_config().get("market_lookback_days") or 30) == 15

    def test_none_preserves_default_behaviour(self):
        set_config({"market_lookback_days": None})
        assert (get_config().get("market_lookback_days") or 30) == 30


def _derive_lookback(analysis: datetime.date, start: datetime.date) -> int:
    """The clamp shared by the sidebar and the CLI helper."""
    return max((analysis - start).days, 5)


@pytest.mark.unit
class TestLookbackDerivation:
    def test_first_of_month_default(self):
        assert _derive_lookback(datetime.date(2026, 7, 23), datetime.date(2026, 7, 1)) == 22

    def test_start_not_before_analysis_clamps_to_min(self):
        assert _derive_lookback(datetime.date(2026, 7, 10), datetime.date(2026, 7, 10)) == 5
        assert _derive_lookback(datetime.date(2026, 7, 10), datetime.date(2026, 7, 20)) == 5

    def test_custom_range(self):
        assert _derive_lookback(datetime.date(2026, 7, 31), datetime.date(2026, 6, 1)) == 60
