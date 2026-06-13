"""Generate PDF reports from analysis results using fpdf2."""

from __future__ import annotations

import platform
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import fpdf as _fpdf_mod
from fpdf import FPDF


# fpdf2 (maintained fork) and the abandoned pyfpdf 1.x BOTH import as `fpdf`, and
# installing both leaves whichever was installed last on disk. pyfpdf 1.x encodes
# every page as latin-1, so any Chinese character raises a cryptic
# `UnicodeEncodeError: 'latin-1' codec can't encode` deep inside the library
# (issue #54). Detect the wrong library up front and tell the user exactly how to
# fix it, instead of letting the PDF blow up mid-render.
_FPDF_VERSION = getattr(_fpdf_mod, "__version__", None) or getattr(_fpdf_mod, "FPDF_VERSION", "0")


def _ensure_fpdf2() -> None:
    try:
        major = int(str(_FPDF_VERSION).split(".")[0])
    except (ValueError, IndexError):
        major = 0
    if major < 2:
        raise RuntimeError(
            f"检测到旧版 fpdf (pyfpdf {_FPDF_VERSION})，它用 latin-1 编码、无法处理中文，"
            "会导致 PDF 导出崩溃（issue #54）。请执行：\n"
            '    pip uninstall -y fpdf && pip install "fpdf2>=2.8.0"\n'
            "（fpdf 与 fpdf2 都以 `fpdf` 名称导入、互相冲突，必须卸载旧的 fpdf），"
            "或改用「下载 Markdown」导出。"
        )


# Per-OS CJK font candidates. The current OS's fonts are tried first so a
# user on Windows/Linux/macOS all get a working PDF without manual config.
_WIN_FONTS = [
    "C:/Windows/Fonts/msyh.ttc",      # 微软雅黑
    "C:/Windows/Fonts/msyhbd.ttc",    # 微软雅黑 Bold
    "C:/Windows/Fonts/simhei.ttf",    # 黑体
    "C:/Windows/Fonts/simsun.ttc",    # 宋体
    "C:/Windows/Fonts/simfang.ttf",   # 仿宋
]
_MAC_FONTS = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]
_LINUX_FONTS = [
    "/usr/share/fonts/truetype/noto/NotoSansSC-Regular.ttf",
    "/usr/share/fonts/noto-cjk/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
]

# Substrings that reliably indicate a CJK-capable font during the recursive
# fallback scan (deliberately excludes bare "noto", which also matches the
# Latin-only Noto family).
_CJK_FONT_KEYWORDS = (
    "msyh", "simhei", "simsun", "simfang", "yahei", "fangsong",
    "pingfang", "heiti", "stheiti", "stsong", "songti", "kaiti",
    "hiragino sans gb", "arial unicode",
    "notosanscjk", "notoserifcjk", "notosanssc", "notoserifsc",
    "sourcehansans", "sourcehanserif", "wqy", "uming", "ukai",
)


def _font_candidates() -> list[str]:
    """Return CJK font paths ordered with the current OS's fonts first."""
    system = platform.system()
    if system == "Windows":
        return _WIN_FONTS + _MAC_FONTS + _LINUX_FONTS
    if system == "Darwin":
        return _MAC_FONTS + _WIN_FONTS + _LINUX_FONTS
    return _LINUX_FONTS + _MAC_FONTS + _WIN_FONTS


def _search_dirs() -> list[str]:
    home = Path.home()
    system = platform.system()
    if system == "Windows":
        return ["C:/Windows/Fonts"]
    if system == "Darwin":
        return ["/System/Library/Fonts", "/Library/Fonts", str(home / "Library/Fonts")]
    return ["/usr/share/fonts", "/usr/local/share/fonts", str(home / ".fonts")]


def _find_cjk_font() -> str | None:
    """Locate a CJK-capable TTF/TTC/OTF font, cross-platform.

    1. Try the known per-OS candidate paths.
    2. Fall back to recursively scanning common font directories for any
       file whose name looks CJK-capable.
    """
    for path in _font_candidates():
        if Path(path).exists():
            return path

    for directory in _search_dirs():
        dpath = Path(directory)
        if not dpath.exists():
            continue
        for ext in ("*.ttc", "*.ttf", "*.otf"):
            try:
                for font_path in sorted(dpath.rglob(ext)):
                    if any(k in font_path.name.lower() for k in _CJK_FONT_KEYWORDS):
                        return str(font_path)
            except OSError:
                continue
    return None


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()


def _strip_md_inline(text: str) -> str:
    """Remove inline markdown formatting: **bold**, *italic*, `code`, [link](url)."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    return text


def _signal_color(signal: str) -> tuple[int, int, int]:
    s = signal.upper()
    if "BUY" in s:
        return (34, 197, 94)
    if "SELL" in s:
        return (239, 68, 68)
    return (251, 191, 36)


_REPORT_SECTIONS = [
    ("market_report", "技术分析报告"),
    ("sentiment_report", "市场情绪报告"),
    ("news_report", "新闻舆情报告"),
    ("fundamentals_report", "基本面报告"),
    ("policy_report", "政策分析报告"),
    ("hot_money_report", "游资追踪报告"),
    ("lockup_report", "解禁/减持报告"),
]


class _ReportPDF(FPDF):
    def __init__(self, ticker: str, stock_name: str, trade_date: str, signal: str) -> None:
        super().__init__()
        self.ticker = ticker
        self.stock_name = stock_name or ticker
        self.trade_date = trade_date
        self.signal = signal
        font_path = _find_cjk_font()
        if not font_path:
            raise RuntimeError(
                "未找到可用的中文字体，无法生成 PDF。请安装一款中文字体后重试"
                "（Windows 自带微软雅黑/黑体，macOS 自带苹方，Linux 可 "
                "`apt install fonts-noto-cjk`），或改用「下载 Markdown」导出。"
            )
        self.add_font("CJK", "", font_path)
        self.add_font("CJK", "B", font_path)

    def _use_font(self, style: str = "", size: int = 10) -> None:
        self.set_font("CJK", style, size)

    def header(self) -> None:
        self._use_font("", 8)
        self.set_text_color(150, 150, 150)
        self.cell(
            0,
            6,
            f"A股多Agent投研分析  |  {self.stock_name}({self.ticker})  |  {self.trade_date}",
            align="C",
        )
        self.ln(8)
        self.set_draw_color(60, 60, 60)
        self.line(10, self.get_y(), self.w - 10, self.get_y())
        self.ln(4)

    def footer(self) -> None:
        self.set_y(-15)
        self._use_font("", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 5, f"Page {self.page_no()}/{{nb}}", align="C")
        self.ln(4)
        self._use_font("", 6)
        self.set_text_color(160, 160, 160)
        self.cell(0, 4, "仅供学习研究，不构成投资建议", align="C")

    def add_cover(self) -> None:
        self.add_page()
        self.ln(60)

        self._use_font("B", 24)
        self.set_text_color(255, 90, 31)
        self.cell(0, 12, "A股多Agent投研分析报告", align="C")
        self.ln(20)

        self._use_font("B", 36)
        self.set_text_color(30, 30, 30)
        self.cell(0, 18, f"{self.stock_name} ({self.ticker})", align="C")
        self.ln(16)

        self._use_font("", 14)
        self.set_text_color(100, 100, 100)
        self.cell(0, 10, f"分析日期: {self.trade_date}", align="C")
        self.ln(8)
        self.cell(0, 10, f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}", align="C")
        self.ln(20)

        r, g, b = _signal_color(self.signal)
        self._use_font("B", 40)
        self.set_text_color(r, g, b)
        self.cell(0, 20, self.signal.upper(), align="C")
        self.ln(20)

        self._use_font("", 9)
        self.set_text_color(120, 120, 120)
        self.multi_cell(
            0, 5,
            "免责声明: 本报告由 AI 多 Agent 系统自动生成, 仅供学习研究与技术演示, "
            "不构成任何投资建议。投资决策请咨询持牌专业机构。"
            "使用本报告所产生的任何损失由使用者自行承担。",
            align="C",
        )

    def add_section(self, title: str, content: str) -> None:
        self.add_page()
        self._use_font("B", 16)
        self.set_text_color(255, 90, 31)
        self.cell(0, 10, title)
        self.ln(12)

        cleaned = _strip_think(content)
        self._render_markdown(cleaned)

    @staticmethod
    def _is_md_table_separator_row(row: str) -> bool:
        """Return True if this markdown row is a separator like |---|:---:|."""
        stripped = row.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            return False
        inner = stripped.strip("|")
        parts = [p.strip() for p in inner.split("|")]
        if not parts:
            return False
        return all(re.fullmatch(r":?-{3,}:?", p or "") is not None for p in parts)

    @staticmethod
    def _parse_md_table_row(row: str) -> list[str]:
        """Parse one markdown table row into stripped cell values."""
        inner = row.strip().strip("|")
        return [_strip_md_inline(c.strip()) for c in inner.split("|")]

    def _wrap_text_by_width(self, text: str, max_width: float) -> list[str]:
        """Wrap text to fit max_width (character-based, CJK-friendly)."""
        text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
        if not text:
            return [""]

        wrapped: list[str] = []
        for raw_line in text.split("\n"):
            line = raw_line.strip()
            if not line:
                wrapped.append("")
                continue

            current = ""
            for ch in line:
                candidate = current + ch
                if current and self.get_string_width(candidate) > max_width:
                    wrapped.append(current)
                    current = ch
                else:
                    current = candidate
            wrapped.append(current if current else "")
        return wrapped or [""]

    def _render_table(self, table_lines: list[str]) -> None:
        """Render a markdown table using fixed grid cells."""
        rows = [
            self._parse_md_table_row(ln)
            for ln in table_lines
            if not self._is_md_table_separator_row(ln)
        ]
        if not rows:
            return

        col_count = max(len(r) for r in rows)
        if col_count <= 0:
            return
        rows = [r + [""] * (col_count - len(r)) for r in rows]

        table_width = self.w - self.l_margin - self.r_margin
        col_width = table_width / col_count
        pad_x = 1.2
        pad_y = 0.9
        line_h = 4.6

        # Header style (first row).
        header_fill = (245, 245, 245)
        border_color = (190, 190, 190)
        text_color = (55, 55, 55)

        self.set_draw_color(*border_color)
        self.set_text_color(*text_color)

        for row_idx, row in enumerate(rows):
            wrapped_cells: list[list[str]] = []
            max_lines = 1
            for cell in row:
                lines = self._wrap_text_by_width(cell, max(1.0, col_width - 2 * pad_x))
                wrapped_cells.append(lines)
                if len(lines) > max_lines:
                    max_lines = len(lines)
            row_h = max(6.0, 2 * pad_y + max_lines * line_h)

            # Auto page-break for full row before drawing.
            if self.get_y() + row_h > self.page_break_trigger:
                self.add_page()

            y0 = self.get_y()
            x0 = self.l_margin

            for col_idx, lines in enumerate(wrapped_cells):
                cell_x = x0 + col_idx * col_width
                if row_idx == 0:
                    self.set_fill_color(*header_fill)
                    self.rect(cell_x, y0, col_width, row_h, style="DF")
                else:
                    self.rect(cell_x, y0, col_width, row_h)

                self.set_xy(cell_x + pad_x, y0 + pad_y)
                self._use_font("B" if row_idx == 0 else "", 8.8 if row_idx == 0 else 8.4)
                self.multi_cell(
                    max(1.0, col_width - 2 * pad_x),
                    line_h,
                    "\n".join(lines),
                    border=0,
                    align="L",
                )

            self.set_xy(self.l_margin, y0 + row_h)

        self.ln(2)

    def _render_markdown(self, text: str) -> None:
        """Render markdown-formatted text with basic styling."""
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Empty line → small vertical gap
            if not stripped:
                self.ln(3)
                i += 1
                continue

            # Headings: ### → 11pt, ## → 13pt, # → 14pt
            if stripped.startswith("###"):
                self._use_font("B", 11)
                self.set_text_color(50, 50, 50)
                self.cell(0, 7, stripped.lstrip("#").strip())
                self.ln(8)
                i += 1
                continue
            if stripped.startswith("##"):
                self._use_font("B", 13)
                self.set_text_color(40, 40, 40)
                self.cell(0, 8, stripped.lstrip("#").strip())
                self.ln(9)
                i += 1
                continue
            if stripped.startswith("#"):
                self._use_font("B", 14)
                self.set_text_color(255, 90, 31)
                self.cell(0, 9, stripped.lstrip("#").strip())
                self.ln(10)
                i += 1
                continue

            # Horizontal rule
            if stripped in ("---", "***", "___"):
                self.set_draw_color(180, 180, 180)
                y = self.get_y() + 2
                self.line(10, y, self.w - 10, y)
                self.ln(6)
                i += 1
                continue

            # Bullet points (-, *, numbered)
            if re.match(r"^[-*]\s", stripped) or re.match(r"^\d+[.)]\s", stripped):
                self._use_font("", 10)
                self.set_text_color(40, 40, 40)
                if re.match(r"^[-*]\s", stripped):
                    bullet = "  •  "
                    body = stripped[2:].strip()
                else:
                    m = re.match(r"^(\d+[.)])\s*(.*)", stripped)
                    bullet = f"  {m.group(1)} "
                    body = m.group(2)
                body = _strip_md_inline(body)
                self.set_x(self.l_margin)
                self.multi_cell(0, 5.5, bullet + body, wrapmode="CHAR")
                i += 1
                continue

            # Markdown table block (|col|col|) → render as fixed grid
            if stripped.startswith("|") and stripped.endswith("|"):
                table_lines = []
                while i < len(lines):
                    row = lines[i].strip()
                    if row.startswith("|") and row.endswith("|"):
                        table_lines.append(row)
                        i += 1
                    else:
                        break
                self._render_table(table_lines)
                continue

            # Regular paragraph — collect consecutive non-special lines
            para_lines = []
            while i < len(lines):
                ln = lines[i].strip()
                if not ln or ln.startswith("#") or ln.startswith("|") or re.match(r"^[-*]\s", ln) or re.match(r"^\d+[.)]\s", ln) or ln in ("---", "***", "___"):
                    break
                para_lines.append(ln)
                i += 1

            if para_lines:
                self._use_font("", 10)
                self.set_text_color(40, 40, 40)
                para = " ".join(para_lines)
                para = _strip_md_inline(para)
                self.set_x(self.l_margin)
                self.multi_cell(0, 5.5, para, wrapmode="CHAR")
                self.ln(2)
                continue

            i += 1


def _collect_sections(final_state: dict[str, Any]) -> list[tuple[str, str]]:
    """Assemble the (title, content) report sections shared by PDF & Markdown.

    Keeps both export formats in sync from a single source of truth.
    """
    sections: list[tuple[str, str]] = []

    for key, title in _REPORT_SECTIONS:
        content = final_state.get(key, "")
        if content:
            sections.append((title, _strip_think(str(content))))

    debate = final_state.get("investment_debate_state")
    if debate and isinstance(debate, dict):
        parts = []
        if debate.get("bull_history"):
            parts.append(f"=== 多方论点 ===\n{debate['bull_history']}")
        if debate.get("bear_history"):
            parts.append(f"\n=== 空方论点 ===\n{debate['bear_history']}")
        if debate.get("judge_decision"):
            parts.append(f"\n=== 研究经理决策 ===\n{debate['judge_decision']}")
        if parts:
            sections.append(("多空辩论", _strip_think("\n".join(parts))))

    trader_decision = final_state.get("trader_investment_decision", "")
    if trader_decision:
        sections.append(("交易员决策", _strip_think(str(trader_decision))))

    inv_plan = final_state.get("investment_plan", "")
    if inv_plan:
        sections.append(("最终投资建议", _strip_think(str(inv_plan))))

    risk = final_state.get("risk_debate_state")
    if risk and isinstance(risk, dict):
        parts = []
        for key_name, label in [("aggressive_history", "激进观点"),
                                 ("conservative_history", "保守观点"),
                                 ("neutral_history", "中性观点")]:
            if risk.get(key_name):
                parts.append(f"=== {label} ===\n{risk[key_name]}")
        if risk.get("judge_decision"):
            parts.append(f"\n=== 风控决策 ===\n{risk['judge_decision']}")
        if parts:
            sections.append(("风控评估", _strip_think("\n".join(parts))))

    final_decision = final_state.get("final_trade_decision", "")
    if final_decision:
        sections.append(("最终决策", _strip_think(str(final_decision))))

    return sections


def generate_pdf(
    final_state: dict[str, Any],
    ticker: str,
    trade_date: str,
    signal: str,
    stock_name: str = "",
) -> bytes:
    """Generate a PDF report and return it as bytes.

    Raises RuntimeError if the wrong fpdf library is installed (issue #54) or no
    CJK font is available on the system — callers should catch this and fall back
    to Markdown export.
    """
    _ensure_fpdf2()
    pdf = _ReportPDF(ticker, stock_name, trade_date, signal)
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)

    pdf.add_cover()
    for title, content in _collect_sections(final_state):
        pdf.add_section(title, content)

    return bytes(pdf.output())


def generate_markdown(
    final_state: dict[str, Any],
    ticker: str,
    trade_date: str,
    signal: str,
    stock_name: str = "",
) -> str:
    """Generate a Markdown report. Font-free and always works — the safe export.

    This is the bulletproof alternative to PDF when the system lacks a CJK
    font (common on minimal Linux/Windows installs).
    """
    title_name = stock_name or ticker
    out = [
        f"# A股多Agent投研分析报告：{title_name} ({ticker})",
        "",
        f"- **股票名称**：{title_name}",
        f"- **股票代码**：{ticker}",
        f"- **分析日期**：{trade_date}",
        f"- **生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- **交易信号**：**{signal.upper()}**",
        "",
        "> ⚠️ 本报告由 AI 多 Agent 系统自动生成，仅供学习研究与技术演示，"
        "不构成任何投资建议。投资决策请咨询持牌专业机构，使用本报告所产生的"
        "任何损失由使用者自行承担。",
        "",
        "---",
        "",
    ]
    for title, content in _collect_sections(final_state):
        out.append(f"## {title}")
        out.append("")
        out.append(content)
        out.append("")

    return "\n".join(out)
