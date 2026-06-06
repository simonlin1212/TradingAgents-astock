"""Tests for web stock display labels."""

import web.stock_display as stock_display


def test_generate_markdown_uses_display_label(monkeypatch):
    from web.pdf_export import generate_markdown

    monkeypatch.setattr(stock_display, "resolve_stock_name", lambda ticker: None)
    state = {"market_report": "600602 云赛智联 技术面分析报告"}

    markdown = generate_markdown(state, "600602", "2026-06-05", "hold")

    assert "- **股票代码**：600602 云赛智联" in markdown
    assert "600602 云赛智联 技术面分析报告" in markdown


def test_stock_display_label_resolves_code_to_name(monkeypatch):
    monkeypatch.setattr(stock_display, "resolve_stock_name", lambda ticker: "退市博元")

    assert stock_display.stock_display_label("600370") == "600370 退市博元"
    assert stock_display.stock_display_label("SH600370") == "600370 退市博元"
    assert stock_display.stock_display_label("600370.SH") == "600370 退市博元"


def test_stock_display_label_removes_invisible_name_chars(monkeypatch):
    monkeypatch.setattr(stock_display, "resolve_stock_name", lambda ticker: "*ST三房\x00")

    assert stock_display.stock_display_label("600370") == "600370 *ST三房"


def test_stock_display_label_resolves_name_input(monkeypatch):
    monkeypatch.setattr(stock_display, "_resolve_display_code", lambda ticker: "600370")
    monkeypatch.setattr(stock_display, "resolve_stock_name", lambda ticker: "退市博元")

    assert stock_display.stock_display_label("退市博元") == "600370 退市博元"


def test_stock_display_label_falls_back_to_state_name(monkeypatch):
    monkeypatch.setattr(stock_display, "resolve_stock_name", lambda ticker: None)

    assert (
        stock_display.stock_display_label("600370", {"company_name": "退市博元"})
        == "600370 退市博元"
    )


def test_stock_display_label_falls_back_to_original_input_name(monkeypatch):
    monkeypatch.setattr(stock_display, "resolve_stock_name", lambda ticker: None)

    assert (
        stock_display.stock_display_label("600370", {"stock_input": "退市博元"})
        == "600370 退市博元"
    )


def test_stock_display_label_falls_back_to_report_code_name(monkeypatch):
    monkeypatch.setattr(stock_display, "resolve_stock_name", lambda ticker: None)

    state = {
        "stock_input": "600602",
        "market_report": "# 600602 云赛智联 技术面分析报告\n**标的：600602 云赛智联**",
    }

    assert stock_display.stock_display_label("600602", state) == "600602 云赛智联"


def test_stock_display_label_falls_back_to_nested_report_code_name(monkeypatch):
    monkeypatch.setattr(stock_display, "resolve_stock_name", lambda ticker: None)

    state = {
        "risk_debate_state": {
            "judge_decision": "对600602 云赛智联给出Sell评级。",
        },
    }

    assert stock_display.stock_display_label("600602", state) == "600602 云赛智联"


def test_stock_display_label_falls_back_to_code(monkeypatch):
    monkeypatch.setattr(stock_display, "resolve_stock_name", lambda ticker: None)

    assert stock_display.stock_display_label("600370") == "600370"


def test_normalize_stock_mentions_adds_name_without_duplicates(monkeypatch):
    monkeypatch.setattr(stock_display, "resolve_stock_name", lambda ticker: "*ST三房")

    text = (
        "600370 技术面分析报告\n"
        "标的：600370 -> 分析日期\n"
        "600370 *ST三房 已经补全。\n"
        "*ST三房 最新可用交易日为 2026-06-02。"
    )

    assert stock_display.normalize_stock_mentions(text, "600370") == (
        "600370 *ST三房 技术面分析报告\n"
        "标的：600370 *ST三房 -> 分析日期\n"
        "600370 *ST三房 已经补全。\n"
        "600370 *ST三房 最新可用交易日为 2026-06-02。"
    )


def test_normalize_report_state_mentions_updates_generated_fields(monkeypatch):
    monkeypatch.setattr(stock_display, "resolve_stock_name", lambda ticker: "*ST三房")
    state = {
        "company_of_interest": "600370",
        "market_report": "600370 技术面分析报告",
        "investment_debate_state": {
            "bull_history": "看多 600370",
            "round": 1,
        },
        "risk_debate_state": {
            "judge_decision": "*ST三房 风险偏高",
        },
    }

    result = stock_display.normalize_report_state_mentions(state, "600370")

    assert result is state
    assert state["company_of_interest"] == "600370"
    assert state["market_report"] == "600370 *ST三房 技术面分析报告"
    assert state["investment_debate_state"]["bull_history"] == "看多 600370 *ST三房"
    assert state["investment_debate_state"]["round"] == 1
    assert state["risk_debate_state"]["judge_decision"] == "600370 *ST三房 风险偏高"
