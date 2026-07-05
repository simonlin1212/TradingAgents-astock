"""Extract structured KOL signals from normalized text."""

from __future__ import annotations

import hashlib
import re

from .models import EXTRACTOR_VERSION, KolSignal, RawKolPost


ACTION_PATTERNS = [
    ("buy", ("低吸", "买入", "看多", "关注", "上车")),
    ("add", ("加仓", "继续拿", "做多")),
    ("sell", ("卖出", "清仓", "止盈")),
    ("reduce", ("减仓", "降低仓位")),
    ("hold", ("持有", "拿着")),
    ("watch", ("观察", "跟踪", "留意")),
    ("avoid", ("回避", "别碰", "不碰")),
    ("risk", ("风险", "追高", "谨慎")),
]


def extract_signals(
    post: RawKolPost,
    stock_name_map: dict[str, str] | None = None,
) -> list[KolSignal]:
    """Extract confirmed A-stock code mentions from one post.

    Name-only mentions are intentionally ignored in v1 unless a caller provides a
    reliable code through the text. This avoids turning fuzzy oral references
    into false trading signals.
    """
    stock_name_map = stock_name_map or {}
    symbols = sorted(set(re.findall(r"(?<!\d)([036]\d{5})(?!\d)", post.content)))
    signals = []
    for symbol in symbols:
        stock_name = stock_name_map.get(symbol, symbol)
        action, action_text = _classify_action(post.content)
        horizon = _classify_horizon(post.content)
        risk_warning = _extract_risk(post.content)
        excerpt = post.content[:240]
        signal_id = _signal_id(post.post_id, symbol, EXTRACTOR_VERSION)
        signals.append(
            KolSignal(
                signal_id=signal_id,
                post_id=post.post_id,
                author_id=post.author_id,
                platform=post.platform,
                symbol=symbol,
                stock_name=stock_name,
                action=action,
                action_text=action_text,
                strength="medium",
                horizon=horizon,
                reason=excerpt,
                risk_warning=risk_warning,
                llm_confidence=0.8,
                published_at=post.published_at,
                source_url=post.source_url,
                content_excerpt=excerpt,
                review_status="confirmed",
            )
        )
    return signals


def _signal_id(post_id: str, symbol: str, extractor_version: str) -> str:
    raw = f"{post_id}:{symbol}:{extractor_version}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _classify_action(text: str) -> tuple[str, str]:
    for action, words in ACTION_PATTERNS:
        for word in words:
            if word in text:
                return action, word
    return "unknown", ""


def _classify_horizon(text: str) -> str:
    if any(word in text for word in ("短线", "1-5天", "1-5 天", "几天")):
        return "short"
    if any(word in text for word in ("日内", "盘中", "今天")):
        return "intraday"
    if any(word in text for word in ("波段", "1-4周", "1-4 周")):
        return "swing"
    if any(word in text for word in ("中线", "1-3月", "1-3 月")):
        return "mid"
    if any(word in text for word in ("长线", "长期", "3个月")):
        return "long"
    return "unknown"


def _extract_risk(text: str) -> str:
    for marker in ("风险", "追高", "谨慎", "止损"):
        idx = text.find(marker)
        if idx >= 0:
            return text[idx : idx + 80]
    return ""
