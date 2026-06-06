"""Render the completed analysis report with expandable sections and PDF download."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any

import streamlit as st

from tradingagents.dataflows.missing_data import (
    get_missing_tasks,
    retry_missing_tasks,
)
from web.pdf_export import generate_markdown, generate_pdf


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()


def _signal_style(signal: str) -> tuple[str, str]:
    s = signal.upper()
    if "BUY" in s:
        return "#22c55e", "买入"
    if "SELL" in s:
        return "#ef4444", "卖出"
    return "#fbbf24", "持有"


_ANALYST_SECTIONS = [
    ("market_report", "📊 技术分析"),
    ("sentiment_report", "💬 市场情绪"),
    ("news_report", "📰 新闻舆情"),
    ("fundamentals_report", "📋 基本面"),
    ("policy_report", "🏛️ 政策分析"),
    ("hot_money_report", "🔥 游资追踪"),
    ("lockup_report", "🔒 解禁/减持"),
]


def _active_missing_tasks(
    final_state: dict[str, Any],
    ticker: str,
    trade_date: str,
) -> list[dict[str, Any]]:
    live_tasks = get_missing_tasks(ticker, trade_date, active_only=True)
    if live_tasks:
        return live_tasks

    tasks = final_state.get("missing_data_tasks")
    if not isinstance(tasks, list):
        return []
    return [
        task
        for task in tasks
        if isinstance(task, dict) and task.get("status", "active") == "active"
    ]


def _format_task_args(args: Any) -> str:
    if not isinstance(args, dict):
        return str(args)
    return ", ".join(f"{key}={value}" for key, value in args.items())


def _start_reanalysis_button(
    ticker: str,
    trade_date: str,
    key_suffix: str,
) -> None:
    if st.button(
        "用补齐后的数据重新分析",
        key=f"reanalyze_after_missing_{ticker}_{trade_date}_{key_suffix}",
        type="primary",
        use_container_width=True,
    ):
        st.session_state["start_analysis"] = {
            "ticker": ticker,
            "trade_date": trade_date,
        }
        st.session_state["viewing_history"] = None
        st.rerun()


def _render_missing_data_panel(
    final_state: dict[str, Any],
    ticker: str,
    trade_date: str,
    key_suffix: str,
) -> None:
    tasks = _active_missing_tasks(final_state, ticker, trade_date)
    count = len(tasks)
    requires_reanalysis = bool(final_state.get("missing_data_requires_reanalysis"))

    if count == 0:
        if requires_reanalysis:
            st.info("缺失接口已经补到数据，但当前报告仍是补数前生成的。请重新分析一次，让分析师、辩论和最终决策使用补齐后的数据。")
            _start_reanalysis_button(ticker, trade_date, key_suffix)
        elif (
            final_state.get("missing_data_tasks") == []
            or final_state.get("missing_data_complete") is True
        ):
            st.success("缺失数据清单为空：当前没有记录到取数失败或必采项缺失。", icon="✅")
        return

    st.warning(
        f"当前报告仍有 {count} 个取数缺口。你仍可先下载按现有内容生成的 PDF；补齐后再重新分析，可得到吸收补齐数据的完整版。",
        icon="⚠️",
    )

    with st.expander(f"查看缺失/失败取数项（{count}）", expanded=False):
        for idx, task in enumerate(tasks, start=1):
            stage = task.get("stage_label") or task.get("stage") or "未知分析段"
            tool = task.get("tool_label") or task.get("tool_name") or "未知接口"
            missing_items = task.get("missing_items") or []
            if isinstance(missing_items, list):
                missing_text = "、".join(str(item) for item in missing_items)
            else:
                missing_text = str(missing_items)
            st.markdown(f"**{idx}. {stage} · {tool}**")
            st.caption(f"调用参数：{_format_task_args(task.get('args', {}))}")
            if missing_text:
                st.markdown(f"- 缺失内容：{missing_text}")
            if task.get("message"):
                st.markdown(f"- 返回信息：{task['message']}")
            retry_attempts = int(task.get("retry_attempts", 0) or 0)
            if retry_attempts:
                st.caption(f"已重试 {retry_attempts} 次")

        retry_key = f"retry_missing_{ticker}_{trade_date}_{key_suffix}"
        if st.button("重新取数这些缺失项", key=retry_key, type="primary", use_container_width=True):
            with st.spinner("正在重新调用缺失数据接口..."):
                result = retry_missing_tasks(ticker, trade_date)
            final_state["missing_data_tasks"] = result.get("remaining", [])
            final_state["missing_data_complete"] = result.get("remaining_count", 0) == 0
            if result.get("resolved_count", 0):
                final_state["missing_data_requires_reanalysis"] = True
            final_state["missing_data_updated_at"] = datetime.now().timestamp()
            st.session_state[f"{retry_key}_result"] = result
            st.rerun()

        retry_result = st.session_state.get(f"{retry_key}_result")
        if retry_result:
            resolved_count = retry_result.get("resolved_count", 0)
            remaining_count = retry_result.get("remaining_count", 0)
            if resolved_count:
                st.success(f"本次已补到 {resolved_count} 个缺失接口的数据。")
            if remaining_count:
                st.info(f"仍有 {remaining_count} 个缺失项没有补齐，可稍后继续重试。")
            else:
                st.success("所有缺失取数项都已补齐。现在可以重新分析，生成基于补齐数据的完整报告。")
                _start_reanalysis_button(ticker, trade_date, key_suffix)


def render_report(
    final_state: dict[str, Any],
    ticker: str,
    trade_date: str,
    signal: str,
    elapsed: float | None = None,
) -> None:
    """Render the full analysis report."""

    color, cn_signal = _signal_style(signal)

    stats_html = ""
    if elapsed is not None:
        m, s = divmod(int(elapsed), 60)
        stats_html = f'<div style="font-size:0.9rem; color:#888; margin-top:0.3rem;">耗时 {m}:{s:02d}</div>'

    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border: 1px solid #333;
            border-radius: 16px;
            padding: 2rem;
            text-align: center;
            margin: 1rem 0 2rem;
        ">
            <div style="font-size:0.9rem; color:#888; letter-spacing:2px;">TRADING SIGNAL</div>
            <div style="font-size:3.5rem; font-weight:900; color:{color}; margin:0.3rem 0;">
                {signal.upper()}
            </div>
            <div style="font-size:1.2rem; color:#f5f1eb;">
                {ticker} · {trade_date}
            </div>
            {stats_html}
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.caption("⚠️ 本报告由 AI 自动生成，仅供学习研究，不构成投资建议。")

    missing_count = len(_active_missing_tasks(final_state, ticker, trade_date))
    requires_reanalysis = bool(final_state.get("missing_data_requires_reanalysis"))
    missing_panel_key = f"missing_panel_{ticker}_{trade_date}"

    col_md, col_pdf, col_missing, col_spacer = st.columns([1, 1, 1, 1])
    with col_md:
        md_text = generate_markdown(final_state, ticker, trade_date, signal)
        st.download_button(
            "📥 下载 Markdown",
            data=md_text.encode("utf-8"),
            file_name=f"TradingAgents-Astock_{ticker}_{trade_date}.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with col_pdf:
        try:
            pdf_bytes = generate_pdf(final_state, ticker, trade_date, signal)
            st.download_button(
                "📄 下载 PDF",
                data=pdf_bytes,
                file_name=f"TradingAgents-Astock_{ticker}_{trade_date}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as exc:  # noqa: BLE001 — never let PDF crash the page
            st.button(
                "📄 PDF 不可用",
                disabled=True,
                use_container_width=True,
                help=f"PDF 生成失败，请改用 Markdown 导出。原因：{exc}",
            )

    with col_missing:
        if missing_count:
            missing_label = f"缺失项 ({missing_count})"
            disabled = False
        elif requires_reanalysis:
            missing_label = "需重新分析"
            disabled = False
        else:
            missing_label = "✅ 无缺失项"
            disabled = True
        if st.button(
            missing_label,
            key=f"missing_toggle_{ticker}_{trade_date}",
            use_container_width=True,
            disabled=disabled,
        ):
            st.session_state[missing_panel_key] = not st.session_state.get(missing_panel_key, False)

    if missing_count:
        st.caption(f"⚠️ 仍有 {missing_count} 个取数缺口；PDF 会按当前已有内容生成，可能缺少部分分析。")
    elif requires_reanalysis:
        st.caption("✅ 缺失接口已补到数据；当前 PDF 仍基于旧报告内容，重新分析后可生成吸收补齐数据的完整版。")

    if st.session_state.get(missing_panel_key):
        _render_missing_data_panel(final_state, ticker, trade_date, missing_panel_key)

    st.markdown("---")

    inv_plan = final_state.get("investment_plan", "")
    if inv_plan:
        st.markdown("### 👔 最终投资建议")
        st.markdown(_strip_think(str(inv_plan)))
        st.markdown("---")

    st.markdown("### 📊 分析师报告")

    for key, title in _ANALYST_SECTIONS:
        content = final_state.get(key, "")
        if not content:
            continue
        with st.expander(title, expanded=False):
            st.markdown(_strip_think(str(content)))

    debate = final_state.get("investment_debate_state")
    if debate and isinstance(debate, dict):
        st.markdown("### ⚔️ 多空辩论")
        tab_bull, tab_bear, tab_judge = st.tabs(["多方", "空方", "研究经理"])
        with tab_bull:
            st.markdown(_strip_think(debate.get("bull_history", "") or "无数据"))
        with tab_bear:
            st.markdown(_strip_think(debate.get("bear_history", "") or "无数据"))
        with tab_judge:
            st.markdown(_strip_think(debate.get("judge_decision", "") or "无数据"))

    trader_decision = final_state.get("trader_investment_decision", "")
    if trader_decision:
        with st.expander("💹 交易员决策", expanded=False):
            st.markdown(_strip_think(str(trader_decision)))

    risk = final_state.get("risk_debate_state")
    if risk and isinstance(risk, dict):
        st.markdown("### 🛡️ 风控评估")
        tab_agg, tab_con, tab_neu, tab_rj = st.tabs(["激进", "保守", "中性", "风控决策"])
        with tab_agg:
            st.markdown(_strip_think(risk.get("aggressive_history", "") or "无数据"))
        with tab_con:
            st.markdown(_strip_think(risk.get("conservative_history", "") or "无数据"))
        with tab_neu:
            st.markdown(_strip_think(risk.get("neutral_history", "") or "无数据"))
        with tab_rj:
            st.markdown(_strip_think(risk.get("judge_decision", "") or "无数据"))

    dqs = final_state.get("data_quality_summary", "")
    if dqs:
        with st.expander("✅ 数据质量", expanded=False):
            st.markdown(str(dqs))
