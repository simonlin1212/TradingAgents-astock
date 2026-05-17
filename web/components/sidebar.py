"""Sidebar: stock input, config display, and history list."""

from __future__ import annotations

from datetime import date

import streamlit as st

from web.history import get_history


def _resolve_user_input(raw: str) -> tuple[str, str | None]:
    """Resolve raw user input to (ticker_code, error_msg).

    Accepts 6-digit codes or Chinese stock names (e.g. '宝光股份').
    Returns (code, None) on success or ("", error_msg) on failure.
    """
    from tradingagents.dataflows.a_stock import resolve_ticker

    try:
        code = resolve_ticker(raw)
        return code, None
    except ValueError as e:
        return "", str(e)


def render_sidebar() -> None:
    """Render the sidebar with input controls and history."""

    theme = st.session_state.get("theme_choice", "暗黑模式")
    if theme == "明亮模式":
        title_color = "#1a1a1a"
        subtitle_color = "#555"
        author_color = "#888"
    else:
        title_color = "#f5f1eb"
        subtitle_color = "#888"
        author_color = "#555"

    st.markdown(
        f"""
        <div style="text-align:center; margin-bottom:1.5rem;">
            <span style="font-size:2rem; font-weight:800; text-shadow: 0 0 0 #ff5a1f; -webkit-text-fill-color: #ff5a1f;">Trading</span><span style="font-size:2rem; font-weight:800; text-shadow: 0 0 0 {title_color}; -webkit-text-fill-color: {title_color};">Agents</span>
            <div style="font-size:0.85rem; color:{subtitle_color}; margin-top:0.2rem;">
                A股多Agent投研系统
            </div>
            <div style="font-size:0.7rem; color:{author_color}; margin-top:0.3rem;">
                by <a href="https://github.com/simonlin1212" style="text-shadow: 0 0 0 #ff5a1f; -webkit-text-fill-color: #ff5a1f; text-decoration:none;">simonlin1212</a>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("#### 界面设置")

    st.radio(
        "主题选择",
        ["暗黑模式", "明亮模式"],
        index=0,
        horizontal=True,
        key="theme_choice",
    )
    st.markdown("---")
    st.markdown("#### 新建分析")

    ticker = st.text_input(
        "股票代码",
        placeholder="例: 300750 或 宁德时代",
        key="input_ticker",
        help="输入6位A股代码或中文股票全称",
    )

    trade_date = st.date_input(
        "分析日期",
        value=date.today(),
        key="input_date",
    )

    start_date = st.date_input(
        "数据起始日期",
        value=date.today().replace(day=1),
        key="input_start_date",
        help="获取历史数据的起始日期，用于技术分析回溯",
    )
    tracker = st.session_state.get("tracker")
    is_busy = tracker is not None and tracker.is_running

    if st.button(
        "开始分析" if not is_busy else "分析进行中...",
        use_container_width=True,
        disabled=is_busy or not ticker,
        type="primary",
    ):
        resolved_code, err = _resolve_user_input(ticker)
        if err:
            st.error(f"❌ {err}")
        else:
            if resolved_code != ticker.strip():
                st.success(f"✅ {ticker.strip()} → {resolved_code}")
            st.session_state["start_analysis"] = {
                "ticker": resolved_code,
                "trade_date": trade_date.strftime("%Y-%m-%d"),
                "start_date": start_date.strftime("%Y-%m-%d"),
            }
            st.session_state["viewing_history"] = None

    st.markdown("---")
    st.markdown("#### 历史记录")

    history = get_history()
    if not history:
        st.caption("暂无历史记录")
        return

    for entry in history[:20]:
        t, d = entry["ticker"], entry["date"]
        label = f"{t}  ·  {d}"
        if st.button(label, key=f"hist_{t}_{d}", use_container_width=True):
            st.session_state["viewing_history"] = entry["path"]
            st.session_state["start_analysis"] = None

    st.markdown("---")
    st.markdown(
        f"""
        <style>
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] .stMarkdown,
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] .stCaption {{
            color: {title_color} !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.caption("⚠️ 仅供学习研究，不构成投资建议")