"""Render the completed analysis report with expandable sections and PDF download."""

from __future__ import annotations

import re
from typing import Any

import streamlit as st

from web.pdf_export import generate_pdf


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

    col_pdf, col_spacer = st.columns([1, 3])
    with col_pdf:
        try:
            pdf_bytes = generate_pdf(final_state, ticker, trade_date, signal)
            st.download_button(
                "📥 下载 PDF 报告",
                data=pdf_bytes,
                file_name=f"TradingAgents-Astock_{ticker}_{trade_date}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as e:
            st.warning(f"PDF 生成失败（不影响报告查看）: {type(e).__name__}")

    st.markdown("---")

    inv_plan = final_state.get("investment_plan", "")
    if inv_plan:
        st.markdown("### 👔 最终投资建议")
        try:
            st.markdown(_strip_think(str(inv_plan)))
        except Exception as e:
            st.error(f"❌ 最终投资建议渲染失败: {e}")
        st.markdown("---")

    st.markdown("### 📊 分析师报告")

    for key, title in _ANALYST_SECTIONS:
        content = final_state.get(key, "")
        if not content:
            continue
        with st.expander(title, expanded=False):
            try:
                st.markdown(_strip_think(str(content)))
            except Exception as e:
                st.error(f"❌ {title}渲染失败: {e}")

    debate = final_state.get("investment_debate_state")
    if debate and isinstance(debate, dict):
        st.markdown("### ⚔️ 多空辩论")
        tab_bull, tab_bear, tab_judge = st.tabs(["多方", "空方", "研究经理"])
        with tab_bull:
            try:
                st.markdown(_strip_think(debate.get("bull_history", "") or "无数据"))
            except Exception as e:
                st.error(f"❌ 多方辩论渲染失败: {e}")
        with tab_bear:
            try:
                st.markdown(_strip_think(debate.get("bear_history", "") or "无数据"))
            except Exception as e:
                st.error(f"❌ 空方辩论渲染失败: {e}")
        with tab_judge:
            try:
                st.markdown(_strip_think(debate.get("judge_decision", "") or "无数据"))
            except Exception as e:
                st.error(f"❌ 研究经理决策渲染失败: {e}")

    trader_decision = final_state.get("trader_investment_decision", "")
    if trader_decision:
        with st.expander("💹 交易员决策", expanded=False):
            try:
                st.markdown(_strip_think(str(trader_decision)))
            except Exception as e:
                st.error(f"❌ 交易员决策渲染失败: {e}")

    risk = final_state.get("risk_debate_state")
    if risk and isinstance(risk, dict):
        st.markdown("### 🛡️ 风控评估")
        tab_agg, tab_con, tab_neu, tab_rj = st.tabs(["激进", "保守", "中性", "风控决策"])
        with tab_agg:
            try:
                st.markdown(_strip_think(risk.get("aggressive_history", "") or "无数据"))
            except Exception as e:
                st.error(f"❌ 激进观点渲染失败: {e}")
        with tab_con:
            try:
                st.markdown(_strip_think(risk.get("conservative_history", "") or "无数据"))
            except Exception as e:
                st.error(f"❌ 保守观点渲染失败: {e}")
        with tab_neu:
            try:
                st.markdown(_strip_think(risk.get("neutral_history", "") or "无数据"))
            except Exception as e:
                st.error(f"❌ 中性观点渲染失败: {e}")
        with tab_rj:
            try:
                st.markdown(_strip_think(risk.get("judge_decision", "") or "无数据"))
            except Exception as e:
                st.error(f"❌ 风控决策渲染失败: {e}")

    dqs = final_state.get("data_quality_summary", "")
    if dqs:
        with st.expander("✅ 数据质量", expanded=False):
            try:
                st.markdown(str(dqs))
            except Exception as e:
                st.error(f"❌ 数据质量渲染失败: {e}")
