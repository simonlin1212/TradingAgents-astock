"""Plain-language labels for the pipeline's intermediate and final ratings."""

from __future__ import annotations

import re


_FINAL_RATINGS = {
    "buy": ("#22c55e", "买入", "持仓：倾向加仓；空仓：倾向买入"),
    "overweight": ("#22c55e", "增持", "持仓：倾向增加仓位；空仓：可考虑建立仓位"),
    "hold": ("#fbbf24", "持有 / 观望", "持仓：倾向维持；空仓：倾向观望"),
    "underweight": ("#f97316", "低配 / 减仓", "持仓：倾向降低仓位；空仓：暂缓买入"),
    "sell": ("#ef4444", "卖出", "持仓：倾向卖出；空仓：不买入"),
}


def final_rating_display(rating: str) -> tuple[str, str, str]:
    """Return color, Chinese label and position-dependent meaning."""
    return _FINAL_RATINGS.get(str(rating).strip().lower(), (
        "#888888", "评级未识别", "请核对最终决策原文",
    ))


_TRADER_ACTION_RE = re.compile(
    r"(?im)^\s*\*{0,2}Action\*{0,2}\s*:\s*\*{0,2}(Buy|Hold|Sell)\b"
)


def trader_action_display(report: str) -> str | None:
    """Read the explicit trader action without guessing from its reasoning."""
    match = _TRADER_ACTION_RE.search(report)
    if not match:
        return None
    return {"buy": "买入", "hold": "持有 / 观望", "sell": "卖出 / 减仓"}[
        match.group(1).lower()
    ]
