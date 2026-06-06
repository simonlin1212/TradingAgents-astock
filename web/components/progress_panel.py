"""Real-time progress display for the analysis pipeline."""

from __future__ import annotations

import streamlit as st

from web.progress import PIPELINE_STAGES, ProgressTracker


def _status_badge(status: str) -> str:
    if status == "done":
        return '<span style="color:#22c55e; font-size:1.3rem;">●</span>'
    if status == "active":
        return '<span style="color:#ff5a1f; font-size:1.3rem;">◉</span>'
    return '<span style="color:#333; font-size:1.3rem;">○</span>'


def _format_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def render_progress(tracker: ProgressTracker) -> None:
    """Render the pipeline progress panel."""

    st.markdown(
        f"""
        <div style="text-align:center; margin:1rem 0 0.5rem;">
            <span style="font-size:1.6rem; font-weight:700; color:#f5f1eb;">
                分析进行中
            </span>
            <span style="font-size:1.1rem; color:#888; margin-left:0.8rem;">
                {tracker.ticker}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if tracker.stop_requested:
        st.caption("正在停止当前分析并清空内容；收尾完成后可重新开始。")
        return

    if tracker.is_paused:
        st.caption("当前分析已暂停。")

    completed = len(tracker.completed_stages)
    total = len(PIPELINE_STAGES)
    pct = completed / total if total else 0
    st.progress(pct, text=f"{completed}/{total} 阶段完成  ·  {_format_time(tracker.elapsed)}")

    analyst_stages = PIPELINE_STAGES[:7]
    post_stages = PIPELINE_STAGES[7:]

    st.markdown(
        '<div style="margin:0.5rem 0 0.3rem; font-size:0.85rem; color:#888;">ANALYSTS</div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(len(analyst_stages))
    for col, stage in zip(cols, analyst_stages):
        status = tracker.stage_status(stage["id"])
        badge = _status_badge(status)
        label_color = "#f5f1eb" if status == "active" else "#888" if status == "pending" else "#22c55e"
        col.markdown(
            f"""
            <div style="text-align:center; padding:0.5rem 0;">
                {badge}<br>
                <span style="font-size:0.75rem; color:{label_color};">{stage['name']}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div style="margin:0.8rem 0 0.3rem; font-size:0.85rem; color:#888;">PIPELINE</div>',
        unsafe_allow_html=True,
    )

    cols2 = st.columns(len(post_stages))
    for col, stage in zip(cols2, post_stages):
        status = tracker.stage_status(stage["id"])
        badge = _status_badge(status)
        label_color = "#f5f1eb" if status == "active" else "#888" if status == "pending" else "#22c55e"
        col.markdown(
            f"""
            <div style="text-align:center; padding:0.5rem 0;">
                {badge}<br>
                <span style="font-size:0.75rem; color:{label_color};">{stage['name']}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("LLM 调用", tracker.llm_calls)
    c2.metric("工具调用", tracker.tool_calls)
    c3.metric("输入 Tokens", f"{tracker.tokens_in:,}")
    c4.metric("输出 Tokens", f"{tracker.tokens_out:,}")

    if tracker.error:
        st.error(f"错误: {tracker.error}")

    completed_reports = [
        (stage["name"], stage["icon"], tracker.stage_reports[stage["id"]])
        for stage in PIPELINE_STAGES
        if stage["id"] in tracker.stage_reports
    ]

    if completed_reports:
        st.markdown(
            '<div style="margin:0.5rem 0 0.3rem; font-size:0.85rem; color:#888;">'
            f"REPORTS ({len(completed_reports)})</div>",
            unsafe_allow_html=True,
        )
        for name, icon, report in reversed(completed_reports):
            is_latest = (name == completed_reports[-1][0])
            with st.expander(f"{icon} {name}", expanded=is_latest):
                st.markdown(report[:3000])
