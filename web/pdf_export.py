"""Generate PDF reports from analysis results using WeasyPrint.

We render the report as styled HTML and let WeasyPrint do typography
and pagination. This replaces an earlier fpdf2 implementation that
either crashed (default word-wrap mode) or hung for minutes
(``wrapmode="CHAR"``) on real Chinese reports with mixed CJK + ASCII
content. HTML/CSS handles CJK natively, supports proper tables,
blockquotes, and code blocks, and renders a 300 KB report in seconds.
"""

from __future__ import annotations

import html
import re
from typing import Any

import markdown as md_lib
from weasyprint import CSS, HTML


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()


def _signal_color(signal: str) -> str:
    s = (signal or "").upper()
    if "BUY" in s:
        return "#22c55e"
    if "SELL" in s:
        return "#ef4444"
    return "#fbbf24"


def _signal_cn(signal: str) -> str:
    s = (signal or "").upper()
    if "BUY" in s:
        return "买入"
    if "SELL" in s:
        return "卖出"
    return "持有"


_REPORT_SECTIONS = [
    ("market_report", "技术分析报告"),
    ("sentiment_report", "市场情绪报告"),
    ("news_report", "新闻舆情报告"),
    ("fundamentals_report", "基本面报告"),
    ("policy_report", "政策分析报告"),
    ("hot_money_report", "游资追踪报告"),
    ("lockup_report", "解禁/减持报告"),
]


# Markdown → HTML with tables, fenced code, attr lists, sane breaks.
_MD = md_lib.Markdown(
    extensions=["tables", "fenced_code", "sane_lists", "nl2br"],
    output_format="html5",
)


def _md_to_html(text: str) -> str:
    """Convert one markdown string to an HTML fragment."""
    _MD.reset()
    return _MD.convert(_strip_think(text))


def _section_html(title: str, content: str) -> str:
    body = _md_to_html(content)
    return f'<section class="report"><h1>{html.escape(title)}</h1>{body}</section>'


def _build_html(
    final_state: dict[str, Any], ticker: str, trade_date: str, signal: str
) -> str:
    color = _signal_color(signal)
    cn = _signal_cn(signal)
    sig = html.escape(signal.upper() if signal else cn)

    cover = f"""
    <section class="cover">
        <div class="cover-tag">TRADING SIGNAL</div>
        <div class="cover-signal" style="color: {color};">{sig}</div>
        <div class="cover-meta">{html.escape(ticker)} · {html.escape(trade_date)}</div>
        <div class="cover-cn">{cn}</div>
        <div class="cover-disclaimer">
            ⚠️ 本报告由 AI 自动生成，仅供学习研究<br>
            不构成投资建议，使用本报告所产生的任何损失由使用者自行承担
        </div>
    </section>
    """

    body_parts: list[str] = [cover]

    inv_plan = final_state.get("investment_plan", "")
    if inv_plan:
        body_parts.append(_section_html("👔 投资建议（研究经理）", str(inv_plan)))

    for key, title in _REPORT_SECTIONS:
        c = final_state.get(key, "")
        if c:
            body_parts.append(_section_html(title, str(c)))

    debate = final_state.get("investment_debate_state")
    if isinstance(debate, dict):
        parts = []
        if debate.get("bull_history"):
            parts.append("## 多方论点\n\n" + str(debate["bull_history"]))
        if debate.get("bear_history"):
            parts.append("## 空方论点\n\n" + str(debate["bear_history"]))
        if debate.get("judge_decision"):
            parts.append("## 研究经理判定\n\n" + str(debate["judge_decision"]))
        if parts:
            body_parts.append(_section_html("⚔️ 多空辩论", "\n\n".join(parts)))

    trader = final_state.get("trader_investment_decision", "")
    if trader:
        body_parts.append(_section_html("💹 交易员决策", str(trader)))

    risk = final_state.get("risk_debate_state")
    if isinstance(risk, dict):
        parts = []
        if risk.get("aggressive_history"):
            parts.append("## 激进风险分析师\n\n" + str(risk["aggressive_history"]))
        if risk.get("conservative_history"):
            parts.append("## 保守风险分析师\n\n" + str(risk["conservative_history"]))
        if risk.get("neutral_history"):
            parts.append("## 中性风险分析师\n\n" + str(risk["neutral_history"]))
        if risk.get("judge_decision"):
            parts.append("## 风控经理判定\n\n" + str(risk["judge_decision"]))
        if parts:
            body_parts.append(_section_html("🛡️ 风控辩论", "\n\n".join(parts)))

    dqs = final_state.get("data_quality_summary", "")
    if dqs:
        body_parts.append(_section_html("✅ 数据质量", str(dqs)))

    final_dec = final_state.get("final_trade_decision", "")
    if final_dec:
        body_parts.append(_section_html("🎯 最终决策", str(final_dec)))

    body = "\n".join(body_parts)

    header_text = f"A股多Agent投研分析  ·  {html.escape(ticker)}  ·  {html.escape(trade_date)}"

    return f"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>TradingAgents-Astock Report {html.escape(ticker)} {html.escape(trade_date)}</title>
</head>
<body>
<div class="page-header">{header_text}</div>
{body}
</body>
</html>"""


_CSS = """
@page {
    size: A4;
    margin: 16mm 14mm 18mm 14mm;
    @top-center {
        content: string(running-header);
        font-family: "PingFang SC", "Heiti SC", "Noto Sans CJK SC", sans-serif;
        font-size: 9pt;
        color: #999;
        border-bottom: 0.5pt solid #ddd;
        padding-bottom: 4mm;
    }
    @bottom-left {
        content: "仅供学习研究，不构成投资建议";
        font-family: "PingFang SC", "Heiti SC", "Noto Sans CJK SC", sans-serif;
        font-size: 7.5pt;
        color: #bbb;
    }
    @bottom-right {
        content: "Page " counter(page) " / " counter(pages);
        font-family: "PingFang SC", "Heiti SC", "Noto Sans CJK SC", sans-serif;
        font-size: 8.5pt;
        color: #aaa;
    }
}
@page cover {
    margin: 0;
    @top-center { content: none; }
    @bottom-left { content: none; }
    @bottom-right { content: none; }
}

* { box-sizing: border-box; }

html, body {
    font-family: "PingFang SC", "Heiti SC", "Noto Sans CJK SC", sans-serif;
    font-size: 10.5pt;
    line-height: 1.65;
    color: #2a2a2a;
    margin: 0;
    padding: 0;
}

.page-header { string-set: running-header content(); display: none; }

.cover {
    page: cover;
    page-break-after: always;
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    color: #f5f1eb;
    text-align: center;
    padding: 70mm 20mm 20mm 20mm;
    min-height: 297mm;
}
.cover-tag { font-size: 11pt; letter-spacing: 4pt; color: #888; }
.cover-signal {
    font-size: 64pt;
    font-weight: 900;
    line-height: 1;
    margin: 8mm 0 4mm;
    letter-spacing: 2pt;
}
.cover-meta { font-size: 16pt; color: #f5f1eb; margin-bottom: 2mm; }
.cover-cn { font-size: 14pt; color: #b8b3a8; margin-bottom: 30mm; }
.cover-disclaimer {
    margin-top: 60mm;
    font-size: 9pt;
    color: #888;
    line-height: 1.8;
}

section.report { page-break-before: always; }
section.report > h1 {
    font-size: 18pt;
    font-weight: 800;
    color: #ff5a1f;
    margin: 0 0 6mm 0;
    padding-bottom: 3mm;
    border-bottom: 1.5pt solid #ff5a1f;
}

h2 {
    font-size: 13pt;
    font-weight: 700;
    color: #1a1a1a;
    margin: 6mm 0 2mm 0;
    padding-bottom: 1.5mm;
    border-bottom: 0.5pt solid #ddd;
}
h3 {
    font-size: 11.5pt;
    font-weight: 700;
    color: #333;
    margin: 4mm 0 1.5mm 0;
}
h4, h5, h6 { font-size: 10.5pt; font-weight: 700; color: #444; margin: 3mm 0 1mm 0; }

p { margin: 1.5mm 0; orphans: 3; widows: 3; }

strong { color: #1a1a1a; }
em { color: #555; }

ul, ol { margin: 2mm 0 2mm 0; padding-left: 7mm; }
li { margin: 0.6mm 0; }

blockquote {
    border-left: 2pt solid #ff5a1f;
    background: #fff7f2;
    padding: 2mm 4mm;
    margin: 2mm 0;
    color: #444;
    font-size: 10pt;
}

code {
    font-family: "SF Mono", "Menlo", "Courier New", monospace;
    background: #f4f4f4;
    padding: 0.5mm 1.5mm;
    border-radius: 1mm;
    font-size: 9.5pt;
}
pre {
    background: #f7f7f7;
    border: 0.5pt solid #e0e0e0;
    padding: 3mm;
    border-radius: 1.5mm;
    font-size: 9pt;
    line-height: 1.45;
    overflow-wrap: break-word;
    white-space: pre-wrap;
}
pre code { background: transparent; padding: 0; }

table {
    border-collapse: collapse;
    width: 100%;
    margin: 3mm 0;
    font-size: 9.5pt;
    page-break-inside: avoid;
}
th, td {
    border: 0.5pt solid #ccc;
    padding: 1.5mm 2.5mm;
    text-align: left;
    vertical-align: top;
}
th {
    background: #fafafa;
    font-weight: 700;
    color: #1a1a1a;
}
tr:nth-child(even) td { background: #fcfcfc; }

hr { border: none; border-top: 0.5pt solid #ddd; margin: 4mm 0; }
"""


def generate_pdf(
    final_state: dict[str, Any], ticker: str, trade_date: str, signal: str
) -> bytes:
    """Generate a PDF report and return it as bytes."""
    html_str = _build_html(final_state, ticker, trade_date, signal)
    return HTML(string=html_str).write_pdf(stylesheets=[CSS(string=_CSS)])
