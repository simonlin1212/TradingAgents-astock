"""Shared 5-tier rating vocabulary and a deterministic heuristic parser.

The same five-tier scale (Buy, Overweight, Hold, Underweight, Sell) is used by:
- The Research Manager (investment plan recommendation)
- The Portfolio Manager (final position decision)
- The signal processor (rating extracted for downstream consumers)
- The memory log (rating tag stored alongside each decision entry)

Centralising it here avoids drift between those call sites.

Chinese output: when ``output_language`` is Chinese and a weak model or an
OpenAI-compatible relay falls back from structured output to free-text (see
:func:`tradingagents.agents.utils.structured.invoke_structured_or_freetext`),
the final decision arrives as Chinese prose with **no** English ``Rating:``
header — just a line like ``最终评级：卖出``. The parser therefore also
recognises the Chinese 5-tier vocabulary; without it, every such run silently
defaulted to Hold regardless of the model's actual call (issues #78 / #80).
"""

from __future__ import annotations

import re
from typing import Tuple


# Canonical, ordered 5-tier scale (most bullish to most bearish).
RATINGS_5_TIER: Tuple[str, ...] = (
    "Buy", "Overweight", "Hold", "Underweight", "Sell",
)

_RATING_SET = {r.lower() for r in RATINGS_5_TIER}

# Matches "Rating: X" / "rating - X" / "Rating: **X**" — tolerates markdown
# bold wrappers and either a colon or hyphen separator.
_RATING_LABEL_RE = re.compile(r"rating.*?[:\-][\s*]*(\w+)", re.IGNORECASE)

# Chinese 5-tier vocabulary → canonical English rating.
_CN_RATING_MAP = {
    "强烈买入": "Buy", "买入": "Buy", "买进": "Buy",
    "增持": "Overweight",
    "持有": "Hold", "中性": "Hold", "观望": "Hold", "维持": "Hold",
    "减持": "Underweight",
    "强烈卖出": "Sell", "清仓": "Sell", "卖出": "Sell",
}
# Longest-first so "强烈买入" beats "买入" and "强烈卖出" beats "卖出" at the
# same position (regex alternation is leftmost, first-listed among equals).
_CN_ALT = "|".join(sorted(_CN_RATING_MAP, key=len, reverse=True))

_CN_LABEL_PREFIX = (
    r"(?:最终评级|评级|投资评级|评级结论|最终投资建议|投资建议|操作建议|"
    r"推荐评级|建议|推荐)\s*[:：\-]\s*\*{0,2}\s*"
)

# A labelled Chinese rating, e.g. "最终评级：卖出" / "投资建议: **增持**".
_CN_LABEL_RE = re.compile(_CN_LABEL_PREFIX + r"(" + _CN_ALT + r")")

# 中文标签后面跟**英文**评级词，例如 "最终评级：Buy"。output_language 设为中文、
# 但模型保留了英文评级词时就是这个形状——而它躲过了上面每一条规则：
# 英文标签规则要求出现 "rating"；中文标签规则只认中文评级词；裸英文词扫描按
# 空白切分，"最终评级：Buy" 是**一个** token，`strip("*:.,")` 又剥不掉全角冒号。
# 结果是静默落到默认值 Hold —— 决策评级被悄悄改写，报告里完全看不出来。
# 评级词后面**不能延续成更长的词**。
#
# 判据刻意选"否定词字符"而不是"枚举允许的标点"——后者是个填不完的坑，这条规则
# 前后被修了三轮才收敛：
#   · `(?![A-Za-z])`  漏掉连字符与数字：`Sell-off risk`→Sell、`Buy2024`→Buy
#   · 枚举收尾标点     漏掉开引号：`Buy（基于风险收益比）`、`Underweight(估值偏高)`
#     被判成 Hold —— 而静默改写决策评级会一路污染记忆日志与绩效统计
# 现在只问一件事：紧跟其后的字符会不会让它变成另一个词？会就不算评级。
# 中文、各种括号、标点、空白、行尾一律放行。
# 「会让它变成另一个词」的字符。连字符要看后面：`Sell-off` 是构词，
# `Sell- 退出` 里的 `-` 只是分隔符，后者不该被判否。
_WORD_CONTINUATION = r"(?:[A-Za-z0-9_]|-(?=[A-Za-z0-9_]))"
# ⚠️ markdown 的收尾星号必须**放进前瞻内部**，不能写成 `\*{0,2}(?!...)` 先消耗再判断：
# 那样正则会回溯——`建议：**Sell**-off risk` 里 `\*{0,2}` 先吃掉 `**` 被 `-` 判否，
# 退一步只吃一个 `*`，剩下的 `*` 恰好满足边界，于是又判成 Sell。
# 写成"后面不能是（0~2 个星号 + 词字符）"就没有可回溯的余地。
# （不用占有量词 `(?>...)`：那是 Python 3.11+ 才有的，本项目声明支持 3.10。）
_RATING_VALUE_END = r"(?!\*{0,2}" + _WORD_CONTINUATION + r")"

_CN_LABEL_EN_RE = re.compile(
    _CN_LABEL_PREFIX + r"(" + "|".join(RATINGS_5_TIER) + r")" + _RATING_VALUE_END,
    re.IGNORECASE,
)
# Bare Chinese rating term anywhere (last-resort fallback).
_CN_TERM_RE = re.compile(_CN_ALT)


def parse_rating(text: str, default: str = "Hold") -> str:
    """Heuristically extract a 5-tier rating from English or Chinese prose.

    Pass order (first hit wins; explicit labels always beat bare words):
    1. English ``Rating: X`` label (tolerant of markdown bold).
    2. Chinese rating label, e.g. ``最终评级：卖出`` / ``投资建议: 增持``；
       也接受中文标签后跟英文评级词的混排（``最终评级：Buy``）。
    3. First bare English 5-tier word found anywhere.
    4. First bare Chinese rating term found anywhere (longest match wins).

    Returns a Title-cased canonical rating, or ``default`` if none appears.
    """
    # 1. English explicit label
    for line in text.splitlines():
        m = _RATING_LABEL_RE.search(line)
        if m and m.group(1).lower() in _RATING_SET:
            return m.group(1).capitalize()

    # 2. Chinese explicit label (最终评级：卖出 …)
    m = _CN_LABEL_RE.search(text)
    if m:
        return _CN_RATING_MAP[m.group(1)]

    # 2b. Chinese label + English rating word (最终评级：Buy)
    m = _CN_LABEL_EN_RE.search(text)
    if m:
        return m.group(1).capitalize()

    # 3. Bare English rating word
    for line in text.splitlines():
        for word in line.lower().split():
            clean = word.strip("*:.,")
            if clean in _RATING_SET:
                return clean.capitalize()

    # 4. Bare Chinese rating term (last resort; leftmost, longest at that spot)
    m = _CN_TERM_RE.search(text)
    if m:
        return _CN_RATING_MAP[m.group(0)]

    return default
