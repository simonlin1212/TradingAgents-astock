"""Generate PDF reports using Chrome headless (native CJK support)."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()


def _inline_md(text: str) -> str:
    """Escape HTML chars then convert inline markdown to HTML tags."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    return text


def _md_to_html(md: str) -> str:
    """Simple markdown to HTML conversion for reports."""
    lines = md.split("\n")
    html_parts: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            html_parts.append("<br>")
            i += 1
            continue

        # Headings
        if stripped.startswith("### "):
            html_parts.append(f"<h4>{_inline_md(stripped[4:])}</h4>")
            i += 1
            continue
        if stripped.startswith("## "):
            html_parts.append(f"<h3>{_inline_md(stripped[3:])}</h3>")
            i += 1
            continue
        if stripped.startswith("# "):
            html_parts.append(f"<h2>{_inline_md(stripped[2:])}</h2>")
            i += 1
            continue

        # Horizontal rule
        if stripped in ("---", "***", "___"):
            html_parts.append("<hr>")
            i += 1
            continue

        # Table
        if stripped.startswith("|") and stripped.endswith("|"):
            rows: list[list[str]] = []
            while i < len(lines):
                ln = lines[i].strip()
                if not (ln.startswith("|") and ln.endswith("|")):
                    break
                if re.match(r"^\|[-:\s|]+\|$", ln):
                    i += 1
                    continue
                cells = [c.strip() for c in ln.strip("|").split("|")]
                rows.append(cells)
                i += 1
            if rows:
                tbl = "<table><tbody>\n"
                for row in rows:
                    tag = "th" if rows.index(row) == 0 else "td"
                    tbl += "<tr>" + "".join(f"<{tag}>{_inline_md(c)}</{tag}>" for c in row) + "</tr>\n"
                tbl += "</tbody></table>"
                html_parts.append(tbl)
            continue

        # Bullet list (-, *)
        if re.match(r"^[-*]\s", stripped):
            items: list[str] = []
            while i < len(lines):
                ln = lines[i].strip()
                m = re.match(r"^[-*]\s(.*)", ln)
                if not m:
                    break
                items.append(f"<li>{_inline_md(m.group(1))}</li>")
                i += 1
            if items:
                html_parts.append("<ul>" + "".join(items) + "</ul>")
            continue

        # Numbered list
        num_match = re.match(r"^(\d+)[.)]\s(.*)", stripped)
        if num_match:
            items = []
            while i < len(lines):
                ln = lines[i].strip()
                m = re.match(r"^\d+[.)]\s(.*)", ln)
                if not m:
                    break
                items.append(f"<li>{_inline_md(m.group(1))}</li>")
                i += 1
            if items:
                html_parts.append("<ol>" + "".join(items) + "</ol>")
            continue

        # Regular paragraph
        html_parts.append(f"<p>{_inline_md(stripped)}</p>")
        i += 1

    return "\n".join(html_parts)


_SIGNAL_COLORS = {"BUY": "#22c55e", "SELL": "#ef4444", "HOLD": "#fbbf24"}


def _signal_color(signal: str) -> str:
    return _SIGNAL_COLORS.get(signal.upper(), "#fbbf24")


def _extract_signal(state: dict) -> str:
    for field in ("investment_plan", "trader_investment_decision", "final_trade_decision"):
        text = state.get(field, "")
        if not text:
            continue
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        upper = cleaned.upper()
        if "SELL" in upper or "卖出" in upper:
            return "SELL"
        if "BUY" in upper or "买入" in upper:
            return "BUY"
        if "HOLD" in upper or "持有" in upper:
            return "HOLD"
    return "N/A"


_REPORT_SECTIONS = [
    ("market_report", "技术分析报告"),
    ("sentiment_report", "市场情绪报告"),
    ("news_report", "新闻舆情报告"),
    ("fundamentals_report", "基本面报告"),
    ("policy_report", "政策分析报告"),
    ("hot_money_report", "游资追踪报告"),
    ("lockup_report", "解禁/减持报告"),
]


def _build_html(state: dict[str, Any], ticker: str, trade_date: str, signal: str) -> str:
    sections_html = ""

    for key, title in _REPORT_SECTIONS:
        content = state.get(key, "")
        if content:
            cleaned = _strip_think(str(content))
            body = _md_to_html(cleaned)
            sections_html += f"""
            <div class="section">
                <div class="section-title">{title}</div>
                <div class="section-body">{body}</div>
            </div>"""

    # Debate section
    debate = state.get("investment_debate_state")
    if debate and isinstance(debate, dict):
        parts = []
        if debate.get("bull_history"):
            parts.append(f"<h3>多方论点</h3>{_md_to_html(debate['bull_history'])}")
        if debate.get("bear_history"):
            parts.append(f"<h3>空方论点</h3>{_md_to_html(debate['bear_history'])}")
        if debate.get("judge_decision"):
            parts.append(f"<h3>研究经理决策</h3>{_md_to_html(debate['judge_decision'])}")
        if parts:
            sections_html += f'<div class="section"><div class="section-title">多空辩论</div>{"".join(parts)}</div>'

    # Trader
    trader = state.get("trader_investment_decision", "")
    if trader:
        sections_html += f'<div class="section"><div class="section-title">交易员决策</div>{_md_to_html(_strip_think(str(trader)))}</div>'

    # Investment plan
    plan = state.get("investment_plan", "")
    if plan:
        sections_html += f'<div class="section"><div class="section-title">最终投资建议</div>{_md_to_html(_strip_think(str(plan)))}</div>'

    # Risk debate
    risk = state.get("risk_debate_state")
    if risk and isinstance(risk, dict):
        parts = []
        for key_name, label in [("aggressive_history", "激进观点"),
                                 ("conservative_history", "保守观点"),
                                 ("neutral_history", "中性观点")]:
            if risk.get(key_name):
                parts.append(f"<h3>{label}</h3>{_md_to_html(risk[key_name])}")
        if risk.get("judge_decision"):
            parts.append(f"<h3>风控决策</h3>{_md_to_html(risk['judge_decision'])}")
        if parts:
            sections_html += f'<div class="section"><div class="section-title">风控评估</div>{"".join(parts)}</div>'

    # Final decision
    final = state.get("final_trade_decision", "")
    if final:
        sections_html += f'<div class="section"><div class="section-title">最终决策</div>{_md_to_html(_strip_think(str(final)))}</div>'

    signal_color = _signal_color(signal)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
    @page {{ margin: 20mm 15mm; }}
    * {{ box-sizing: border-box; }}
    body {{
        font-family: "Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans SC",
                     "WenQuanYi Micro Hei", "Microsoft YaHei", sans-serif;
        font-size: 11pt;
        line-height: 1.7;
        color: #222;
        max-width: 800px;
        margin: 0 auto;
        padding: 0;
    }}
    .cover {{
        text-align: center;
        padding: 120px 0 60px;
    }}
    .cover h1 {{
        font-size: 28pt;
        color: #ff5a1f;
        margin-bottom: 20px;
    }}
    .cover .ticker {{
        font-size: 40pt;
        font-weight: bold;
        color: #1a1a1a;
        margin: 20px 0;
    }}
    .cover .meta {{ font-size: 13pt; color: #666; margin: 6px 0; }}
    .cover .signal {{
        font-size: 42pt;
        font-weight: bold;
        color: {signal_color};
        margin: 30px 0;
    }}
    .cover .disclaimer {{
        font-size: 9pt;
        color: #888;
        max-width: 500px;
        margin: 40px auto;
        line-height: 1.5;
    }}
    .section {{
        page-break-before: always;
        padding-top: 10px;
    }}
    .section-title {{
        font-size: 18pt;
        font-weight: bold;
        color: #ff5a1f;
        border-bottom: 2px solid #ff5a1f;
        padding-bottom: 8px;
        margin-bottom: 16px;
    }}
    h2 {{ font-size: 16pt; color: #ff5a1f; margin: 20px 0 10px; }}
    h3 {{ font-size: 14pt; color: #333; margin: 18px 0 8px; }}
    h4 {{ font-size: 12pt; color: #444; margin: 14px 0 6px; }}
    p {{ margin: 6px 0; text-align: justify; }}
    hr {{ border: none; border-top: 1px solid #ccc; margin: 16px 0; }}
    table {{
        width: 100%;
        border-collapse: collapse;
        margin: 10px 0;
        font-size: 10pt;
    }}
    td, th {{
        border: 1px solid #ccc;
        padding: 5px 8px;
        text-align: left;
    }}
    th {{
        background: #f5f5f5;
        font-weight: bold;
    }}
    ul, ol {{ margin: 6px 0; padding-left: 24px; }}
    li {{ margin: 3px 0; }}
    code {{
        background: #f0f0f0;
        padding: 1px 5px;
        border-radius: 3px;
        font-size: 10pt;
    }}
    .footer {{
        text-align: center;
        color: #aaa;
        font-size: 8pt;
        padding: 20px 0;
        page-break-after: always;
    }}
</style>
</head>
<body>
    <div class="cover">
        <h1>A股多Agent投研分析报告</h1>
        <div class="ticker">{ticker}</div>
        <div class="meta">分析日期：{trade_date}</div>
        <div class="meta">生成时间：{now}</div>
        <div class="signal">{signal}</div>
        <div class="disclaimer">
            免责声明：本报告由AI多Agent系统自动生成，仅供学习研究与技术演示，
            不构成任何投资建议。投资决策请咨询持牌专业机构。
            使用本报告所产生的任何损失由使用者自行承担。
        </div>
    </div>

    {sections_html}

    <div class="footer">仅供学习研究，不构成投资建议</div>
</body>
</html>"""


def generate_pdf(state: dict[str, Any], ticker: str, trade_date: str, signal: str | None = None) -> bytes:
    """Generate PDF using Chrome headless for native CJK rendering."""
    if not signal:
        signal = _extract_signal(state)

    html = _build_html(state, ticker, trade_date, signal)

    with tempfile.NamedTemporaryFile(suffix=".html", mode="w", encoding="utf-8", delete=False) as f:
        f.write(html)
        html_path = f.name

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        pdf_path = f.name

    try:
        result = subprocess.run(
            [
                "google-chrome-stable",
                "--headless=new",
                "--disable-gpu",
                "--no-margins",
                "--no-pdf-header-footer",
                f"--print-to-pdf={pdf_path}",
                f"file://{html_path}",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Chrome failed: {result.stderr}")

        pdf_bytes = Path(pdf_path).read_bytes()
        if len(pdf_bytes) < 1000:
            raise RuntimeError(f"PDF too small ({len(pdf_bytes)} bytes)")
        return pdf_bytes
    finally:
        Path(html_path).unlink(missing_ok=True)
        Path(pdf_path).unlink(missing_ok=True)
