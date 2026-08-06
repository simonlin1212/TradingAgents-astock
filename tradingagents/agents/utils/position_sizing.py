"""Deterministic position sizing and validation for the Execution Advisor.

The Execution Advisor asks the LLM for *price levels only* (entry zone,
stop-loss, target). The position size is derived here, from a simple
risk-budget rule, so the model can never hallucinate a percentage:

    position % = min(risk_budget% / stop_distance%, single-name cap%)

Example: price 10.0, stop-loss 9.0 → stop distance 10% of price; with a
1.5% risk budget that gives 15% (below the 20% cap).

This is a deliberately simplified v1 model (no portfolio correlation,
no volatility cones); reports state the limitation.
"""

from __future__ import annotations

from tradingagents.agents.schemas import ExecutionAdvice

# Defaults, overridable by callers (planned config keys per dev_plan D4).
DEFAULT_RISK_BUDGET_PCT = 1.5
DEFAULT_CAP_PCT = 20.0


def position_size_pct(
    price: float,
    stop_loss: float,
    risk_budget_pct: float = DEFAULT_RISK_BUDGET_PCT,
    cap_pct: float = DEFAULT_CAP_PCT,
) -> float:
    """Return the recommended position size in percent of total capital.

    Returns ``0.0`` for invalid inputs (non-positive price, non-positive
    stop, or a stop at/above the price), meaning "do not enter".
    """
    if price <= 0 or stop_loss <= 0 or stop_loss >= price:
        return 0.0
    stop_distance = (price - stop_loss) / price
    if stop_distance <= 0:
        return 0.0
    raw = risk_budget_pct / stop_distance
    return round(min(raw, cap_pct), 1)


def _invalid_advice(rationale: str) -> ExecutionAdvice:
    """Build a placeholder advice that signals "no actionable levels"."""
    return ExecutionAdvice(
        entry_zone="N/A",
        stop_loss=0.0,
        target_price=0.0,
        position_size_pct=0.0,
        rationale=rationale,
    )


def validate_advice(advice: ExecutionAdvice, price: float) -> ExecutionAdvice:
    """Validate the LLM-proposed levels and fill in the position size.

    - ``stop_loss < price < target_price`` must hold; otherwise the advice
      is replaced with an "N/A" placeholder rather than trusting bad levels.
    - ``position_size_pct`` is always recomputed from the stop distance
      (the LLM's own value, if any, is overwritten).
    - A missing/unusable price also yields the placeholder.
    """
    if price is None or price <= 0:
        return _invalid_advice("无法获取有效现价，暂不提供执行建议")
    if not (0 < advice.stop_loss < price < advice.target_price):
        return _invalid_advice("价位不满足 止损<现价<目标 的约束，已拒绝，暂不提供执行建议")

    advice.position_size_pct = position_size_pct(price, advice.stop_loss)
    return advice
