"""决策绩效统计 —— 这套 agent 到底准不准（#61）。

决策和真实收益其实一直都在存：`TradingMemoryLog` 每次分析落一条
`[日期 | 代码 | 评级 | pending]`，下次跑同一只票时 `_resolve_pending_entries()`
会拉真实行情回填 raw 收益与 alpha（对沪深 300）。缺的只是**汇总**——在此之前
整个仓库连一个胜率都算不出来。

零 LLM 成本：只读已经落盘的结果，不重跑任何分析。

⚠️ 这不是回测。每条记录是"某天做的判断在固定持有期后的表现"，不是一个可交易的
组合：持有窗口互相重叠、没有仓位管理、没有交易成本、幸存下来的样本也可能有偏。
所以这里**不算夏普、不做年化**——用离散、重叠的决策点去annualize 只会得到一个
看着专业但没有意义的数字。

指标口径参考 Vibe-Trading（MIT，https://github.com/HKUDS/Vibe-Trading）的
`agent/backtest/metrics.py`：胜率与盈亏统计按已完成交易计，不按逐 bar 收益计。
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from tradingagents.agents.utils.rating import RATINGS_5_TIER

# 样本少于这个数时，任何比率都只是噪音。宁可明说，也不要让人把 3 条记录里的
# "66.7% 胜率"当回事——这是这类统计最常见的误读。
MIN_MEANINGFUL_SAMPLE = 20


def _parse_pct(value: Optional[str]) -> Optional[float]:
    """把记忆日志里的 "+5.0%" 解析回 0.05。解析不了返回 None（不当成 0）。"""
    if not value:
        return None
    text = str(value).strip().replace("%", "")
    try:
        return float(text) / 100.0
    except ValueError:
        return None


def _parse_holding_days(value) -> Optional[int]:
    """解析持有天数。记忆日志的格式是 `5d`，不是裸数字。"""
    if value is None:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return int(digits) if digits else None


# 评级的方向：看多为 +1，看空为 -1，Hold 视为无方向（不参与方向正确率）。
_RATING_DIRECTION = {
    "Buy": 1, "Overweight": 1,
    "Hold": 0,
    "Underweight": -1, "Sell": -1,
}


@dataclass
class DecisionRecord:
    """一条已结算的决策。"""

    date: str
    ticker: str
    rating: str
    raw_return: float
    alpha_return: Optional[float]
    holding_days: Optional[int]


@dataclass
class GroupStats:
    """一组决策的表现。"""

    count: int = 0
    # ⚠️ 命名即口径：下面两个是**标的涨跌**，不是"决策对不对"。
    # 给出 Sell 评级后股价下跌，是判断正确，但 up_rate 会把它记成 0。
    # 衡量判断准不准的是 direction_accuracy。
    up_rate: Optional[float] = None
    outperform_rate: Optional[float] = None
    direction_accuracy: Optional[float] = None
    directional_count: int = 0
    avg_return: Optional[float] = None
    median_return: Optional[float] = None
    avg_alpha: Optional[float] = None
    best: Optional[float] = None
    worst: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "count": self.count,
            "up_rate": self.up_rate,
            "outperform_rate": self.outperform_rate,
            "direction_accuracy": self.direction_accuracy,
            "directional_count": self.directional_count,
            "avg_return": self.avg_return,
            "median_return": self.median_return,
            "avg_alpha": self.avg_alpha,
            "best": self.best,
            "worst": self.worst,
        }


def _stats(records: List[DecisionRecord]) -> GroupStats:
    if not records:
        return GroupStats()
    raws = [r.raw_return for r in records]
    alphas = [r.alpha_return for r in records if r.alpha_return is not None]

    # 方向正确率：只统计**有方向**的评级（Hold 不表态，无所谓对错），
    # 并按方向判定——看多要涨、看空要跌才算对。用 alpha 判（跑赢/跑输大盘），
    # 拿不到 alpha 时退回绝对收益。
    directional = [
        r for r in records if _RATING_DIRECTION.get(r.rating, 0) != 0
    ]
    hits = sum(
        1 for r in directional
        if (r.alpha_return if r.alpha_return is not None else r.raw_return)
        * _RATING_DIRECTION[r.rating] > 0
    )

    return GroupStats(
        count=len(records),
        up_rate=sum(1 for v in raws if v > 0) / len(raws),
        # A 股 beta 很强，跟着大盘涨不代表判断对，所以单独看跑赢比例。
        outperform_rate=(
            sum(1 for v in alphas if v > 0) / len(alphas) if alphas else None
        ),
        direction_accuracy=(hits / len(directional) if directional else None),
        directional_count=len(directional),
        avg_return=statistics.fmean(raws),
        median_return=statistics.median(raws),
        avg_alpha=statistics.fmean(alphas) if alphas else None,
        best=max(raws),
        worst=min(raws),
    )


def load_records(entries: List[dict]) -> List[DecisionRecord]:
    """从 TradingMemoryLog 解析出的条目里取已结算的那些。

    未结算（pending）和 raw 收益解析不出来的都跳过——把解析失败当成 0% 收益会
    悄悄把统计拉向中性，正是这类报表最容易骗人的地方。
    """
    records: List[DecisionRecord] = []
    for e in entries:
        if e.get("pending"):
            continue
        raw = _parse_pct(e.get("raw"))
        if raw is None:
            continue
        # 记忆日志写的是 "5d"（memory.py 的 tag 带 d 后缀），直接 int() 会抛，
        # 于是每条的持有期都被吞成 None、平均持有期永远显示不出来。
        holding_days = _parse_holding_days(e.get("holding"))
        records.append(
            DecisionRecord(
                date=e.get("date", ""),
                ticker=e.get("ticker", ""),
                rating=e.get("rating", "") or "Unknown",
                raw_return=raw,
                alpha_return=_parse_pct(e.get("alpha")),
                holding_days=holding_days,
            )
        )
    return records


def rating_monotonicity(by_rating: Dict[str, GroupStats]) -> Optional[bool]:
    """更看好的评级，实际收益是不是真的更高？

    这是"这套 agent 准不准"最直接的检验：五档评级从 Buy 到 Sell，平均 alpha
    应当单调递减。只在**每一档都有样本**时才给结论，否则返回 None——拿两三档
    去判断单调性没有意义。
    """
    ordered = [by_rating.get(r) for r in RATINGS_5_TIER]
    if any(g is None or g.count == 0 or g.avg_alpha is None for g in ordered):
        return None
    values = [g.avg_alpha for g in ordered]
    return all(a >= b for a, b in zip(values, values[1:]))


def summarize(entries: List[dict]) -> Dict[str, Any]:
    """汇总记忆日志里的全部决策。

    Args:
        entries: `TradingMemoryLog.load_entries()` 的返回值。

    Returns:
        统计字典。`resolved` 为 0 时其余字段为空，调用方据此提示"还没有可统计的
        结果"，而不是显示一堆 0%。
    """
    total = len(entries)
    pending = sum(1 for e in entries if e.get("pending"))
    records = load_records(entries)

    by_rating: Dict[str, GroupStats] = {}
    for rating in RATINGS_5_TIER:
        by_rating[rating] = _stats([r for r in records if r.rating == rating])
    others = [r for r in records if r.rating not in RATINGS_5_TIER]
    if others:
        by_rating["Unknown"] = _stats(others)

    by_ticker: Dict[str, GroupStats] = {}
    for ticker in sorted({r.ticker for r in records}):
        by_ticker[ticker] = _stats([r for r in records if r.ticker == ticker])

    overall = _stats(records)
    holdings = [r.holding_days for r in records if r.holding_days]

    return {
        "total_decisions": total,
        "pending": pending,
        "resolved": len(records),
        # 样本太小的时候必须自己说出来，不能等用户自己去数。
        # ⚠️ 分母要各算各的：`direction_accuracy` 只统计有方向的评级（Hold 不计入），
        # 拿"已结算总数"给它做显著性判据会高估——20 条已结算里只有 1 条有方向时，
        # 提示被抑制，报告却敢显示"方向正确率 100%"。
        "sample_is_meaningful": len(records) >= MIN_MEANINGFUL_SAMPLE,
        "direction_sample_is_meaningful": (
            overall.directional_count >= MIN_MEANINGFUL_SAMPLE
        ),
        "min_meaningful_sample": MIN_MEANINGFUL_SAMPLE,
        "avg_holding_days": statistics.fmean(holdings) if holdings else None,
        "overall": overall.as_dict(),
        "by_rating": {k: v.as_dict() for k, v in by_rating.items() if v.count},
        "by_ticker": {k: v.as_dict() for k, v in by_ticker.items()},
        "rating_monotonic": rating_monotonicity(by_rating),
        "date_range": (
            (min(r.date for r in records), max(r.date for r in records))
            if records else None
        ),
    }


def _pct(value: Optional[float], digits: int = 1) -> str:
    return "—" if value is None else f"{value:+.{digits}%}"


def _rate(value: Optional[float]) -> str:
    return "—" if value is None else f"{value:.1%}"


def format_report(summary: Dict[str, Any]) -> str:
    """把统计结果排成给人看的文本。"""
    if summary["resolved"] == 0:
        return (
            f"暂无可统计的决策结果。\n"
            f"共 {summary['total_decisions']} 条决策记录，其中 {summary['pending']} 条"
            f"尚未结算。\n"
            f"结算发生在下一次分析同一只股票时（自动拉取真实行情回填收益），"
            f"或等持有期结束后重新跑一次该股票。"
        )

    lines: List[str] = ["# 决策绩效统计", ""]
    if summary["date_range"]:
        lines.append(f"区间：{summary['date_range'][0]} → {summary['date_range'][1]}")
    lines.append(
        f"决策 {summary['total_decisions']} 条 · 已结算 {summary['resolved']} 条 · "
        f"待结算 {summary['pending']} 条"
    )
    if summary["avg_holding_days"]:
        lines.append(f"平均持有 {summary['avg_holding_days']:.1f} 个交易日")

    if not summary["sample_is_meaningful"]:
        lines += [
            "",
            f"⚠️ 样本仅 {summary['resolved']} 条，少于 "
            f"{summary['min_meaningful_sample']} 条时下面的比率基本是噪音，"
            f"**不要据此判断这套流程有效或无效**。",
        ]
    elif not summary["direction_sample_is_meaningful"]:
        # 总样本够、但有方向的评级不够——最关键的那个指标仍然不可信，必须单独说
        lines += [
            "",
            f"⚠️ 已结算 {summary['resolved']} 条，但其中**有方向的评级只有 "
            f"{summary['overall']['directional_count']} 条**（Hold 不计入方向判断）。"
            f"少于 {summary['min_meaningful_sample']} 条时「方向正确率」基本是噪音，"
            f"**不要据此判断这套流程准不准**；下面其余比率的样本量以已结算总数为准。",
        ]

    o = summary["overall"]
    lines += [
        "",
        "## 整体",
        f"- **方向正确率：{_rate(o['direction_accuracy'])}**"
        f"（{o['directional_count']} 条有方向的评级；看多要跑赢、看空要跑输才算对）",
        f"- 标的上涨占比：{_rate(o['up_rate'])}",
        f"- 跑赢沪深300占比：{_rate(o['outperform_rate'])}",
        f"- 平均收益：{_pct(o['avg_return'])}　中位数：{_pct(o['median_return'])}",
        f"- 平均 alpha：{_pct(o['avg_alpha'])}",
        f"- 最好：{_pct(o['best'])}　最差：{_pct(o['worst'])}",
        "",
        "> **只有「方向正确率」衡量判断准不准。** 下面两个比率描述的是标的怎么走，"
        "与评级方向无关：给出卖出评级后股价下跌是**判断正确**，但它不会计入"
        "「上涨占比」。Hold 不表态，不计入方向正确率。",
        "> A 股 beta 很强，跟着大盘涨不等于判断对，所以看 alpha 口径比看绝对收益更可靠。",
    ]

    if summary["by_rating"]:
        lines += ["", "## 按评级", "",
                  "| 评级 | 条数 | 方向正确率 | 上涨占比 | 跑赢占比 | 平均收益 | 平均alpha |",
                  "|---|---|---|---|---|---|---|"]
        for rating, g in summary["by_rating"].items():
            lines.append(
                f"| {rating} | {g['count']} | {_rate(g['direction_accuracy'])} | "
                f"{_rate(g['up_rate'])} | {_rate(g['outperform_rate'])} | "
                f"{_pct(g['avg_return'])} | {_pct(g['avg_alpha'])} |"
            )
        mono = summary["rating_monotonic"]
        if mono is True:
            lines += ["", "✅ 评级越看好，平均 alpha 越高——评级带有区分度。"]
        elif mono is False:
            lines += ["", "⚠️ 评级与实际 alpha **不单调**：更看好的评级并没有带来更高的超额收益。"]
        else:
            lines += ["", "（五档评级尚未各自积累到样本，暂不判断评级是否有区分度。）"]

    if summary["by_ticker"]:
        lines += ["", "## 按标的", "",
                  "| 代码 | 条数 | 方向正确率 | 平均收益 | 平均alpha |",
                  "|---|---|---|---|---|"]
        for ticker, g in summary["by_ticker"].items():
            lines.append(
                f"| {ticker} | {g['count']} | {_rate(g['direction_accuracy'])} | "
                f"{_pct(g['avg_return'])} | {_pct(g['avg_alpha'])} |"
            )

    lines += [
        "",
        "---",
        "⚠️ **这不是回测，也不是策略业绩。** 每条记录是「某天做出的判断在固定持有期后的"
        "表现」，持有窗口互相重叠、没有仓位管理、未计交易成本与冲击成本，样本也可能有"
        "选择偏差。它只用来观察这套分析流程自身的一致性，不构成任何投资建议。",
    ]
    return "\n".join(lines)
