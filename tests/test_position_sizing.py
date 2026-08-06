"""Unit tests for deterministic position sizing and ExecutionAdvice validation.

The position size must never come from the LLM: it is derived from the stop
distance via ``position_size_pct``, and ``validate_advice`` rejects levels
that violate ``stop_loss < price < target_price`` (returning an "N/A"
placeholder instead of trusting bad numbers).
"""

import pytest

from tradingagents.agents.schemas import ExecutionAdvice
from tradingagents.agents.utils.position_sizing import (
    position_size_pct,
    validate_advice,
)


@pytest.mark.unit
class TestPositionSizePct:
    def test_normal_case(self):
        # price 10, stop 9.0 → stop distance 10% → 1.5 / 0.10 = 15%
        assert position_size_pct(10.0, 9.0) == 15.0

    def test_capped_at_max(self):
        # stop 9.9 → distance 1% → 150% → capped at 20%
        assert position_size_pct(10.0, 9.9) == 20.0

    def test_never_above_cap(self):
        for stop in (9.99, 9.9, 9.8, 9.5):
            assert position_size_pct(10.0, stop) <= 20.0

    def test_stop_at_or_above_price_is_zero(self):
        assert position_size_pct(10.0, 10.0) == 0.0
        assert position_size_pct(10.0, 10.5) == 0.0

    def test_non_positive_inputs_are_zero(self):
        assert position_size_pct(0.0, 5.0) == 0.0
        assert position_size_pct(10.0, 0.0) == 0.0
        assert position_size_pct(10.0, -1.0) == 0.0

    def test_zero_risk_budget_is_zero(self):
        assert position_size_pct(10.0, 9.0, risk_budget_pct=0.0) == 0.0

    def test_custom_budget_and_cap(self):
        assert position_size_pct(10.0, 9.0, risk_budget_pct=2.0, cap_pct=30.0) == 20.0
        assert position_size_pct(10.0, 9.0, risk_budget_pct=4.0, cap_pct=30.0) == 30.0


@pytest.mark.unit
class TestValidateAdvice:
    def _advice(self, stop_loss=9.0, target=11.5, entry="9.8 - 10.2", rationale="ok"):
        return ExecutionAdvice(
            entry_zone=entry, stop_loss=stop_loss, target_price=target,
            rationale=rationale,
        )

    def test_valid_levels_fill_position(self):
        out = validate_advice(self._advice(), price=10.0)
        assert out.position_size_pct == 15.0
        assert out.stop_loss == 9.0
        assert out.target_price == 11.5

    def test_invalid_levels_rejected_to_placeholder(self):
        # stop >= price, target <= price → whole advice becomes N/A
        out = validate_advice(self._advice(stop_loss=10.5, target=9.0), price=10.0)
        assert out.entry_zone == "N/A"
        assert out.stop_loss == 0.0
        assert out.target_price == 0.0
        assert out.position_size_pct == 0.0

    def test_missing_price_rejected(self):
        out = validate_advice(self._advice(), price=None)
        assert out.entry_zone == "N/A"
        assert out.position_size_pct == 0.0

    def test_llm_position_value_is_overwritten(self):
        # Even if the LLM somehow smuggles a percentage in, the rule wins.
        advice = self._advice()
        advice.position_size_pct = 88.0
        out = validate_advice(advice, price=10.0)
        assert out.position_size_pct == 15.0
