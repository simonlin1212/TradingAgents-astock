"""Web 侧栏模型选择的回归测试。

线上事故：`MODEL_OPTIONS` 每个供应商都带一条哨兵项
`("Custom model ID", "custom")`，含义是"自己填模型 ID"。CLI 会就此追问输入
（`cli/utils.py::_select_model`），而 Web 侧栏把它**当成模型名直接发了出去**——
用户在 DeepSeek 的深模型下拉里停在 index 3（正是那条哨兵），于是 API 回：

    The supported API model names are deepseek-flash, deepseek-v4-pro,
    but you passed custom.

这里锁死两件事：哨兵必须被翻成用户填的 ID，以及没填时要在开始分析前拦住。
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS
from web.components import sidebar


@pytest.fixture()
def fake_st(monkeypatch):
    """替掉 streamlit：text_input 记下调用并回一个可控值。"""
    st = types.SimpleNamespace(session_state={}, text_input_calls=[])

    def text_input(label, key=None, placeholder=None, **kwargs):
        st.text_input_calls.append({"label": label, "key": key})
        return st.typed_value

    st.typed_value = "deepseek-v4-pro"
    st.text_input = text_input
    monkeypatch.setattr(sidebar, "st", st)
    return st


@pytest.mark.unit
def test_sentinel_renders_text_input_and_uses_typed_id(fake_st):
    fake_st.typed_value = "  deepseek-v4-pro  "

    resolved = sidebar._resolve_model_value(
        sidebar._CUSTOM_MODEL_SENTINEL, "custom_quick_model", "快速思考模型 ID"
    )

    assert resolved == "deepseek-v4-pro"  # 已 strip
    assert fake_st.text_input_calls == [
        {"label": "快速思考模型 ID", "key": "custom_quick_model"}
    ]


@pytest.mark.unit
def test_real_model_value_passes_through_without_prompting(fake_st):
    resolved = sidebar._resolve_model_value("deepseek-chat", "custom_quick_model", "x")

    assert resolved == "deepseek-chat"
    assert fake_st.text_input_calls == []


@pytest.mark.unit
def test_every_provider_sentinel_is_intercepted(fake_st):
    """回归：任何供应商的「Custom model ID」都不能原样流过。"""
    seen_sentinel = False
    for provider, modes in MODEL_OPTIONS.items():
        for mode, options in modes.items():
            for label, value in options:
                if value == sidebar._CUSTOM_MODEL_SENTINEL:
                    seen_sentinel = True
                resolved = sidebar._resolve_model_value(value, "k", "l")
                assert resolved != sidebar._CUSTOM_MODEL_SENTINEL, (
                    f"{provider}/{mode} 的 {label!r} 把哨兵值漏了出去"
                )

    assert seen_sentinel, "目录里已经没有哨兵项了，这个回归测试需要跟着改"


@pytest.mark.unit
def test_deepseek_deep_index_three_was_the_reported_case(fake_st):
    """事故现场：deepseek 的 deep 列表 index 3 就是哨兵。"""
    deep_options = MODEL_OPTIONS["deepseek"]["deep"]

    assert deep_options[3][1] == sidebar._CUSTOM_MODEL_SENTINEL
    fake_st.typed_value = "deepseek-v4-pro"
    assert (
        sidebar._resolve_model_value(deep_options[3][1], "custom_deep_model", "深")
        == "deepseek-v4-pro"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "quick,deep,expected_label",
    [
        ("custom", "deepseek-v4-pro", "快速思考模型"),
        ("deepseek-chat", "custom", "深度思考模型"),
        ("", "deepseek-v4-pro", "快速思考模型"),
        ("deepseek-chat", "   ", "深度思考模型"),
    ],
)
def test_validation_blocks_sentinel_or_empty(fake_st, quick, deep, expected_label):
    fake_st.session_state.update(
        {"quick_think_llm": quick, "deep_think_llm": deep}
    )

    err = sidebar.validate_model_selection()

    assert err is not None
    assert expected_label in err


@pytest.mark.unit
def test_validation_passes_for_real_models(fake_st):
    fake_st.session_state.update(
        {"quick_think_llm": "deepseek-flash", "deep_think_llm": "deepseek-v4-pro"}
    )

    assert sidebar.validate_model_selection() is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "quick,deep,expected_label",
    [
        ("", "deepseek-v4-pro", "快速思考模型"),
        ("deepseek-flash", "", "深度思考模型"),
        ("custom", "", "快速思考模型"),
    ],
)
def test_validation_accepts_an_explicit_config(quick, deep, expected_label):
    """消费点校验的是 `_build_config()` 的产物，不读 session_state。"""
    config = {"quick_think_llm": quick, "deep_think_llm": deep}

    err = sidebar.validate_model_selection(config)

    assert err is not None
    assert expected_label in err


@pytest.mark.unit
def test_validation_of_explicit_config_passes():
    config = {"quick_think_llm": "deepseek-flash", "deep_think_llm": "deepseek-v4-pro"}

    assert sidebar.validate_model_selection(config) is None


@pytest.mark.unit
def test_app_guards_at_the_consumption_point():
    """结构性回归：模型校验必须挂在 `start_analysis` 的**消费点**。

    `start_analysis` 有 5 个生产者（侧栏开始分析 / 未完成任务续跑 / 历史记录 /
    报告页重新分析 / 错误页继续未完成任务）。只在侧栏按钮里守一个是不够的——实测
    漏过：深模型选「Custom model ID」且留空、走续跑路径，请求带着空模型打了出去，
    收到 `The supported API model names are ..., but you passed .`。

    这里断言 web/app.py 在取出 start_analysis 之后、起线程之前调用了校验，而且校验
    的是将要发出去的那份 config。
    """
    app_src = (
        Path(sidebar.__file__).resolve().parent.parent / "app.py"
    ).read_text(encoding="utf-8")

    pop_at = app_src.index('st.session_state.pop("start_analysis"')
    guard_at = app_src.index("validate_model_selection(config)")
    run_at = app_src.index("run_analysis_in_thread(")

    assert pop_at < guard_at < run_at
