"""Helpers for displaying A-share stock identifiers in the web UI."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any


def _clean_stock_name(name: str) -> str:
    return "".join(ch for ch in str(name) if ch.isprintable()).strip()


def _looks_like_stock_name(value: str) -> bool:
    return bool(value and any("一" <= ch <= "鿿" for ch in str(value)))


def _is_plausible_stock_name(value: str, code: str) -> bool:
    if not value or value == code or not _looks_like_stock_name(value):
        return False
    # Avoid treating report headings such as "技术面分析报告" as a stock name
    # when older states only contain the plain code in stock_input.
    non_name_markers = (
        "技术面",
        "技术分析",
        "市场情绪",
        "新闻舆情",
        "基本面",
        "政策分析",
        "游资追踪",
        "风险评估",
        "投资建议",
        "交易决策",
        "最终决策",
        "分析报告",
        "报告",
        "当前",
        "最新",
    )
    return not any(marker in value for marker in non_name_markers)


def _normalize_display_code(ticker: str) -> str:
    code = str(ticker or "").strip().upper()
    for suffix in (".SH", ".SZ", ".BJ"):
        if code.endswith(suffix):
            code = code[: -len(suffix)]
            break
    for prefix in ("SH", "SZ", "BJ"):
        if code.startswith(prefix):
            code = code[len(prefix) :]
            break
    return code


@lru_cache(maxsize=1024)
def _resolve_display_code(ticker: str) -> str:
    code = _normalize_display_code(ticker)
    if re.match(r"^[036]\d{5}$", code):
        return code

    if any("一" <= ch <= "鿿" for ch in code):
        try:
            from tradingagents.dataflows.a_stock import resolve_ticker

            return resolve_ticker(code)
        except Exception:
            return code

    return code


@lru_cache(maxsize=1024)
def resolve_stock_name(ticker: str) -> str | None:
    """Return the A-share name for a ticker code when local market data can resolve it."""
    code = _resolve_display_code(ticker)
    if not re.match(r"^[036]\d{5}$", code):
        return None

    try:
        from tradingagents.dataflows.a_stock import _build_name_code_map

        _, code_to_name = _build_name_code_map()
    except Exception:
        return None

    name = _clean_stock_name(code_to_name.get(code, ""))
    return name or None


def _iter_text_values(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_text_values(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_text_values(item)


def _clean_extracted_name(name: str) -> str:
    cleaned = _clean_stock_name(name)
    cleaned = cleaned.strip("`_[]【】")
    cleaned = re.sub(r"[*_`]+$", "", cleaned).strip()
    for marker in (
        "给出",
        "当前",
        "技术",
        "市场",
        "新闻",
        "基本面",
        "政策",
        "风险",
        "投资",
        "交易",
        "最终",
        "报告",
        "评级",
    ):
        if marker in cleaned:
            cleaned = cleaned.split(marker, 1)[0]
    return cleaned.strip("，。；：:、（）()")


def _extract_stock_name_from_text(code: str, text: str) -> str | None:
    code_pattern = re.escape(code)
    patterns = (
        rf"(?<!\d){code_pattern}\s*[（(]\s*([^\s，。；：:、（）()|]{{2,16}})\s*[）)]",
        rf"(?:标的\s*[：:]\s*)?(?<!\d){code_pattern}\s+([^\s，。；：:、（）()|]{{2,16}})",
        rf"([^\s，。；：:、（）()|]{{2,16}})\s*[（(]\s*{code_pattern}\s*[）)]",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            name = _clean_extracted_name(match.group(1))
            if _is_plausible_stock_name(name, code):
                return name
    return None


def _extract_stock_name_from_state(code: str, final_state: dict) -> str | None:
    for key in ("stock_name", "company_name", "stock_input", "raw_ticker", "input_ticker"):
        name = _clean_extracted_name(str(final_state.get(key, "")))
        if _is_plausible_stock_name(name, code):
            return name

    company = _clean_extracted_name(str(final_state.get("company_of_interest", "")))
    if _is_plausible_stock_name(company, code):
        return company

    for key in (*_REPORT_TEXT_KEYS, *_REPORT_DICT_KEYS):
        if key not in final_state:
            continue
        for text in _iter_text_values(final_state[key]):
            name = _extract_stock_name_from_text(code, text)
            if name:
                return name
    return None


def stock_display_label(ticker: str, final_state: dict | None = None) -> str:
    """Format a stock as 'code name', falling back to the code when the name is unknown."""
    code = _resolve_display_code(ticker)
    name = resolve_stock_name(code)

    if not name and final_state:
        name = _extract_stock_name_from_state(code, final_state)

    if name:
        name = _clean_stock_name(name)

    if name and name != code:
        return f"{code} {name}"
    return code


def stock_display_parts(ticker: str, final_state: dict | None = None) -> tuple[str, str | None]:
    """Return the resolved display code and optional stock name."""
    code = _resolve_display_code(ticker)
    label = stock_display_label(code, final_state)
    if label == code:
        return code, None
    return code, label.removeprefix(code).strip() or None


def normalize_stock_mentions(text: str, ticker: str, final_state: dict | None = None) -> str:
    """Render code/name mentions in report text as the unified 'code name' label."""
    if not text:
        return text

    code, name = stock_display_parts(ticker, final_state)
    if not name:
        return text

    label = f"{code} {name}"
    name_pattern = re.escape(name)
    code_pattern = re.escape(code)

    normalized = re.sub(rf"(?<!\d){code_pattern}\s*{name_pattern}", label, text)

    def replace_code(match: re.Match[str]) -> str:
        following = normalized[match.end() : match.end() + len(name) + 8]
        if re.match(rf"\s*{name_pattern}", following):
            return match.group(0)
        return label

    normalized = re.sub(rf"(?<!\d){code_pattern}(?!\d)", replace_code, normalized)

    def replace_name(match: re.Match[str]) -> str:
        prefix = normalized[max(0, match.start() - len(code) - 8) : match.start()]
        if re.search(rf"{code_pattern}\s*$", prefix):
            return match.group(0)
        return label

    return re.sub(name_pattern, replace_name, normalized)


_REPORT_TEXT_KEYS = (
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
    "policy_report",
    "hot_money_report",
    "lockup_report",
    "data_quality_summary",
    "trader_investment_plan",
    "trader_investment_decision",
    "investment_plan",
    "final_trade_decision",
)

_REPORT_DICT_KEYS = (
    "investment_debate_state",
    "risk_debate_state",
)


def _normalize_report_value(value: Any, ticker: str, final_state: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return normalize_stock_mentions(value, ticker, final_state)
    if isinstance(value, dict):
        return {
            key: _normalize_report_value(item, ticker, final_state)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _normalize_report_value(item, ticker, final_state)
            for item in value
        ]
    return value


def normalize_report_state_mentions(final_state: dict[str, Any], ticker: str) -> dict[str, Any]:
    """Normalize generated report fields in-place before saving/displaying them."""
    for key in _REPORT_TEXT_KEYS:
        if key in final_state:
            final_state[key] = _normalize_report_value(final_state[key], ticker, final_state)

    for key in _REPORT_DICT_KEYS:
        if key in final_state:
            final_state[key] = _normalize_report_value(final_state[key], ticker, final_state)

    return final_state
