"""Pydantic schemas used by agents that produce structured output.

The framework's primary artifact is still prose: each agent's natural-language
reasoning is what users read in the saved markdown reports and what the
downstream agents read as context.  Structured output is layered onto the
three decision-making agents (Research Manager, Trader, Portfolio Manager)
so that:

- Their outputs follow consistent section headers across runs and providers
- Each provider's native structured-output mode is used (json_schema for
  OpenAI/xAI, response_schema for Gemini, tool-use for Anthropic)
- Schema field descriptions become the model's output instructions, freeing
  the prompt body to focus on context and the rating-scale guidance
- A render helper turns the parsed Pydantic instance back into the same
  markdown shape the rest of the system already consumes, so display,
  memory log, and saved reports keep working unchanged
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared rating types
# ---------------------------------------------------------------------------


class PortfolioRating(str, Enum):
    """5-tier rating used by the Research Manager and Portfolio Manager."""

    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"


class TraderAction(str, Enum):
    """3-tier transaction direction used by the Trader.

    The Trader's job is to translate the Research Manager's investment plan
    into a concrete transaction proposal: should the desk execute a Buy, a
    Sell, or sit on Hold this round.  Position sizing and the nuanced
    Overweight / Underweight calls happen later at the Portfolio Manager.
    """

    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"


# ---------------------------------------------------------------------------
# Research Manager
# ---------------------------------------------------------------------------


class ResearchPlan(BaseModel):
    """Structured investment plan produced by the Research Manager.

    Hand-off to the Trader: the recommendation pins the directional view,
    the rationale captures which side of the bull/bear debate carried the
    argument, and the strategic actions translate that into concrete
    instructions the trader can execute against.
    """

    recommendation: PortfolioRating = Field(
        description=(
            "The investment recommendation. Exactly one of Buy / Overweight / "
            "Hold / Underweight / Sell. Reserve Hold for situations where the "
            "evidence on both sides is genuinely balanced; otherwise commit to "
            "the side with the stronger arguments."
        ),
    )
    rationale: str = Field(
        description=(
            "Conversational summary of the key points from both sides of the "
            "debate, ending with which arguments led to the recommendation. "
            "Speak naturally, as if to a teammate."
        ),
    )
    strategic_actions: str = Field(
        description=(
            "Concrete steps for the trader to implement the recommendation, "
            "consistent with the rating."
        ),
    )


def render_research_plan(plan: ResearchPlan) -> str:
    """Render a ResearchPlan to markdown for storage and the trader's prompt context."""
    return "\n".join([
        f"**Recommendation**: {plan.recommendation.value}",
        "",
        f"**Rationale**: {plan.rationale}",
        "",
        f"**Strategic Actions**: {plan.strategic_actions}",
    ])


# ---------------------------------------------------------------------------
# Trader
# ---------------------------------------------------------------------------


class TraderProposal(BaseModel):
    """Structured transaction proposal produced by the Trader.

    The trader reads the Research Manager's investment plan and the analyst
    reports, then states a direction and the reasoning behind it.

    It deliberately carries **no executable price levels** — no entry price,
    no stop-loss, no position size. This project is a research and education
    implementation of the upstream TradingAgents framework, and concrete trade
    levels for a named security are what turn a research tool into an
    investment-advisory product. The capability is not shipped here; a
    downstream fork that wants it can add it under its own responsibility.
    """

    action: TraderAction = Field(
        description="The transaction direction. Exactly one of Buy / Hold / Sell.",
    )
    reasoning: str = Field(
        description=(
            "The case for this action, anchored in the analysts' reports and "
            "the research plan. Two to four sentences. Do not quote specific "
            "entry, stop-loss or position-size levels."
        ),
    )


def render_trader_proposal(proposal: TraderProposal) -> str:
    """Render a TraderProposal to markdown.

    The trailing ``FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**`` line is
    preserved for backward compatibility with the analyst stop-signal text
    and any external code that greps for it.
    """
    return "\n".join([
        f"**Action**: {proposal.action.value}",
        "",
        f"**Reasoning**: {proposal.reasoning}",
        "",
        f"FINAL TRANSACTION PROPOSAL: **{proposal.action.value.upper()}**",
    ])


# ---------------------------------------------------------------------------
# Portfolio Manager
# ---------------------------------------------------------------------------


class PortfolioDecision(BaseModel):
    """Structured output produced by the Portfolio Manager.

    The model fills every field as part of its primary LLM call; no separate
    extraction pass is required. Field descriptions double as the model's
    output instructions, so the prompt body only needs to convey context and
    the rating-scale guidance.

    Like :class:`TraderProposal`, this carries no price target and no other
    executable level — see that class for why.
    """

    rating: PortfolioRating = Field(
        description=(
            "The final position rating. Exactly one of Buy / Overweight / Hold / "
            "Underweight / Sell, picked based on the analysts' debate."
        ),
    )
    executive_summary: str = Field(
        description=(
            "A concise summary of what drove the rating and the main "
            "considerations on each side. Two to four sentences. Do not quote "
            "specific entry, stop-loss, position-size or target-price levels."
        ),
    )
    investment_thesis: str = Field(
        description=(
            "Detailed reasoning anchored in specific evidence from the analysts' "
            "debate. If prior lessons are referenced in the prompt context, "
            "incorporate them; otherwise rely solely on the current analysis."
        ),
    )
    time_horizon: Optional[str] = Field(
        default=None,
        description="Optional analysis horizon, e.g. '3-6 months'.",
    )


def render_pm_decision(decision: PortfolioDecision) -> str:
    """Render a PortfolioDecision back to the markdown shape the rest of the system expects.

    Memory log, CLI display, and saved report files all read this markdown,
    so the rendered output preserves the exact section headers (``**Rating**``,
    ``**Executive Summary**``, ``**Investment Thesis**``) that downstream
    parsers and the report writers already handle.
    """
    parts = [
        f"**Rating**: {decision.rating.value}",
        "",
        f"**Executive Summary**: {decision.executive_summary}",
        "",
        f"**Investment Thesis**: {decision.investment_thesis}",
    ]
    if decision.time_horizon:
        parts.extend(["", f"**Time Horizon**: {decision.time_horizon}"])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Execution Advisor
# ---------------------------------------------------------------------------


class ExecutionAdvice(BaseModel):
    """Research-reference execution levels produced by the Execution Advisor.

    Runs *after* the Portfolio Manager, whose mandate deliberately excludes
    executable levels. This node translates the final rating into concrete
    research-reference figures — entry zone, stop-loss, target price — used
    for study and education only, not as an investment-advisory signal.

    ``position_size_pct`` is intentionally NOT filled by the LLM: it is
    computed deterministically from the stop distance by
    ``tradingagents.agents.utils.position_sizing.position_size_pct`` and
    written into the instance during validation, so the model cannot
    hallucinate a position size.
    """

    entry_zone: str = Field(
        description=(
            "Recommended entry range as a narrow band around the latest close, "
            "e.g. '12.5 - 13.2'. Must include the latest close inside it."
        ),
    )
    stop_loss: float = Field(
        description=(
            "Stop-loss level, strictly BELOW the latest close. Base it on the "
            "recent support level or close minus ~1.5x ATR."
        ),
    )
    target_price: float = Field(
        description=(
            "Target price, strictly ABOVE the latest close. Base it on the "
            "recent resistance level or close plus ~2x ATR."
        ),
    )
    rationale: str = Field(
        description=(
            "One short sentence explaining the entry/stop/target choice, "
            "60 characters or fewer. Do not repeat the rating rationale."
        ),
    )
    position_size_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description=(
            "Recommended position size as a percentage of total portfolio "
            "capital, 0-100. Filled deterministically by position sizing "
            "logic; the model does not propose this value."
        ),
    )


def render_execution_advice(advice: ExecutionAdvice) -> str:
    """Render an ExecutionAdvice to markdown for reports and the Web UI.

    Section headers are stable (``**Entry Zone**`` / ``**Stop Loss**`` /
    ``**Target Price**`` / ``**Position Size**`` / ``**Rationale**``) so
    report writers can consume the output without parsing the model object.
    """
    parts = [
        f"**Entry Zone**: {advice.entry_zone}",
        f"**Stop Loss**: {advice.stop_loss}",
        f"**Target Price**: {advice.target_price}",
        f"**Position Size**: {advice.position_size_pct}%",
    ]
    if advice.rationale:
        parts.append(f"**Rationale**: {advice.rationale}")
    return "\n".join(parts)
