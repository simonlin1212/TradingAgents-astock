"""Regression tests for PDF export."""

from pathlib import Path

import pytest
from fpdf.enums import WrapMode

from web.pdf_export import (
    PDFExportError,
    _ReportPDF,
    _compact_inline_text,
    _discover_cjk_fonts,
    _find_cjk_fonts,
    _format_table_cells,
    generate_pdf,
)


def test_generate_pdf_with_chinese_markdown_when_cjk_font_available():
    try:
        _find_cjk_fonts()
    except PDFExportError as exc:
        pytest.skip(str(exc))

    state = {
        "market_report": "# 技术分析\n- 趋势: 偏强\n- 结论: 中文字体测试通过。",
        "news_report": "| 项目 | 结论 |\n|---|---|\n| 中文 | 可嵌入 |",
        "final_trade_decision": "最终建议: HOLD 观望。",
    }

    pdf_bytes = generate_pdf(state, "600519", "2026-05-30", "HOLD")

    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000


def test_pdf_text_helpers_compact_alignment_whitespace():
    assert _compact_inline_text("Neutral        Analyst:        我会把") == "Neutral Analyst: 我会把"
    assert _format_table_cells(["表面看是放量反弹", "但对连续跌停后的", "ST"]) == "表面看是放量反弹 | 但对连续跌停后的 | ST"


def test_pdf_multicell_defaults_to_left_alignment():
    pdf = object.__new__(_ReportPDF)
    calls = []

    pdf.l_margin = 10
    pdf.r_margin = 10
    pdf.w = 210
    pdf.set_x = lambda x: None
    pdf.multi_cell = lambda *args, **kwargs: calls.append((args, kwargs))

    pdf._write_multicell(5.5, "近 5 日均量明显高于近 20 日均量。")

    assert calls[0][1]["align"] == "L"
    assert calls[0][1]["wrapmode"] == WrapMode.CHAR


def test_wqy_discovery_reuses_same_font_for_bold(monkeypatch, tmp_path):
    wqy = tmp_path / "wqy-microhei.ttc"
    noto_bold = tmp_path / "NotoSansCJK-Bold.ttc"
    wqy.write_bytes(b"font")
    noto_bold.write_bytes(b"font")

    def fake_find_font_file(pattern: str) -> Path | None:
        return {
            "wqy-microhei.ttc": wqy,
            "NotoSansCJK-Bold.ttc": noto_bold,
        }.get(pattern)

    monkeypatch.setattr("web.pdf_export._find_font_file", fake_find_font_file)

    assert _discover_cjk_fonts() == (wqy, wqy)
