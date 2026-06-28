"""Shared 5-tier rating vocabulary and a deterministic heuristic parser.

The same five-tier scale (Buy, Overweight, Hold, Underweight, Sell) is used by:
- The Research Manager (investment plan recommendation)
- The Portfolio Manager (final position decision)
- The signal processor (rating extracted for downstream consumers)
- The memory log (rating tag stored alongside each decision entry)

Centralising it here avoids drift between those call sites.
"""

from __future__ import annotations

import re
from typing import Tuple


# Canonical, ordered 5-tier scale (most bullish to most bearish).
RATINGS_5_TIER: Tuple[str, ...] = (
    "Buy", "Overweight", "Hold", "Underweight", "Sell",
)

_RATING_SET = {r.lower() for r in RATINGS_5_TIER}
_CN_RATING_ALIASES = {
    "强烈买入": "Buy",
    "推荐买入": "Buy",
    "买入": "Buy",
    "买进": "Buy",
    "加仓": "Overweight",
    "增持": "Overweight",
    "超配": "Overweight",
    "持有": "Hold",
    "观望": "Hold",
    "中性": "Hold",
    "减仓": "Underweight",
    "减持": "Underweight",
    "低配": "Underweight",
    "清仓": "Sell",
    "卖出": "Sell",
    "退出": "Sell",
    "回避": "Sell",
}

# Matches "Rating: X" / "最终评级：**卖出**" — tolerates markdown bold
# wrappers and either English or Chinese separators.
_RATING_LABEL_RE = re.compile(
    r"(?:rating|recommendation|最终评级|评级|最终建议|投资建议|交易决策)"
    r".*?[:：\-][\s*`]*(\w+|[\u4e00-\u9fff]{1,8})",
    re.IGNORECASE,
)


def _normalize_rating_token(token: str) -> str | None:
    clean = token.strip("*`：:，,。. \t\r\n")
    if clean.lower() in _RATING_SET:
        return clean.capitalize()
    for alias, rating in _CN_RATING_ALIASES.items():
        if alias in clean:
            return rating
    return None


def parse_rating(text: str, default: str = "Hold") -> str:
    """Heuristically extract a 5-tier rating from prose text.

    Two-pass strategy:
    1. Look for an explicit "Rating: X" label (tolerant of markdown bold).
    2. Fall back to the first 5-tier rating word found anywhere in the text.

    Returns a Title-cased rating string, or ``default`` if no rating word appears.
    """
    for line in text.splitlines():
        m = _RATING_LABEL_RE.search(line)
        if m:
            rating = _normalize_rating_token(m.group(1))
            if rating:
                return rating

    for line in text.splitlines():
        for word in line.lower().split():
            rating = _normalize_rating_token(word)
            if rating:
                return rating
        for alias, rating in _CN_RATING_ALIASES.items():
            if alias in line:
                return rating

    return default
