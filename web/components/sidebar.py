"""Sidebar: stock input, LLM config, and history list."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import streamlit as st

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.checkpointer import clear_checkpoint
from tradingagents.llm_clients.model_catalog import ARK_PLAN_ENDPOINTS, MODEL_OPTIONS
from web.history import (
    clear_incomplete_task,
    get_history,
    get_incomplete_history,
    record_incomplete_task,
)

# Provider display names in recommended order
_PROVIDERS: list[tuple[str, str]] = [
    ("MiniMax（推荐·国内直连）", "minimax"),
    ("火山方舟 Coding Plan（Anthropic 协议）", "ark_coding"),
    ("火山方舟 Agent Plan（Anthropic 协议）", "ark_agent"),
    ("DeepSeek", "deepseek"),
    ("通义千问 Qwen", "qwen"),
    ("智谱 GLM", "glm"),
    ("OpenAI", "openai"),
    ("Anthropic", "anthropic"),
    ("Google Gemini", "google"),
    ("xAI Grok", "xai"),
    ("OpenRouter（聚合·填 vendor/model 形式 ID）", "openrouter"),
    ("OpenAI 兼容（自定义 base_url·9Router/AI Router/自建代理）", "openai_compatible"),
    ("Ollama（本地）", "ollama"),
]

_PROVIDER_DISPLAY = [name for name, _ in _PROVIDERS]
_PROVIDER_KEYS = [key for _, key in _PROVIDERS]

# Web 端的兜底 provider。DEFAULT_CONFIG 里的默认是 openai（面向 CLI 和上游），
# Web 这边一直以 MiniMax 为推荐入口，所以两边默认值不同。模型没有对应常量：
# 未指定时一律回落到该 provider 候选列表的首项（见 _default_model_idx）。
_WEB_FALLBACK_PROVIDER = "minimax"

# 仓库根目录的 .env，「保存为默认」写这里
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def _save_defaults_to_env(values: dict[str, str]) -> None:
    """把 values 写回 .env：同名变量原地覆盖，其余行（含注释、空行）原样保留。"""
    lines = (
        _ENV_PATH.read_text(encoding="utf-8").splitlines()
        if _ENV_PATH.exists()
        else []
    )
    pending = dict(values)
    out: list[str] = []
    for line in lines:
        name = line.split("=", 1)[0].strip() if "=" in line else ""
        if name in pending:
            out.append(f"{name}={pending.pop(name)}")
        else:
            out.append(line)
    out.extend(f"{name}={value}" for name, value in pending.items())
    _ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")



def _configured(env_name: str) -> str | None:
    """只在 .env 里显式配了该变量时返回其值，否则返回 None。

    不能复用 DEFAULT_CONFIG——它已经把未设置的情况填成了上游默认值
    （llm_provider=openai），而 openai 恰好也在 Web 的候选列表里，导致无法区分
    "用户显式选了 openai" 和 "什么都没配"。后者必须保持 Web 原有的 MiniMax 默认。
    """
    raw = os.getenv(env_name)
    return raw.strip() if raw and raw.strip() else None


def _default_provider_idx() -> int:
    """.env 里 TRADINGAGENTS_LLM_PROVIDER 对应的下拉序号。

    未配置、或配了 Web 端不提供的 provider（比如 azure）时，退回 Web 的推荐默认值。
    """
    provider = _configured("TRADINGAGENTS_LLM_PROVIDER") or _WEB_FALLBACK_PROVIDER
    if provider not in _PROVIDER_KEYS:
        provider = _WEB_FALLBACK_PROVIDER
    return _PROVIDER_KEYS.index(provider)


def _default_model_idx(options: list[tuple[str, str]], env_name: str) -> int:
    """.env 里 env_name 指定的模型在 options 里的序号，找不到就回 0。

    只在当前 provider 的候选列表里找。用户配了 A 家的模型却选了 B 家的 provider
    时，落回 0（B 家的首个模型）比硬塞一个跑不通的 ID 更好。
    """
    configured = _configured(env_name)
    if not configured:
        return 0
    values = [value for _, value in options]
    return values.index(configured) if configured in values else 0


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


def _clear_analysis_artifacts(ticker: str, trade_date: str) -> None:
    clear_incomplete_task(ticker, trade_date)
    clear_checkpoint(DEFAULT_CONFIG["data_cache_dir"], ticker, trade_date)


def _render_analysis_controls(raw_ticker: str, trade_date_value: date) -> None:
    tracker = st.session_state.get("tracker")
    is_running = tracker is not None and tracker.is_running
    trade_date = trade_date_value.strftime("%Y-%m-%d")

    pause_col, resume_col, stop_col = st.columns(3)

    pause_disabled = not is_running or tracker.is_paused or tracker.stop_requested
    if pause_col.button(
        "暂停",
        key="sidebar_pause_analysis",
        use_container_width=True,
        disabled=pause_disabled,
    ):
        if tracker.pause():
            record_incomplete_task(
                tracker.ticker,
                tracker.trade_date,
                status="paused",
                completed_stages=tracker.completed_stages,
            )
        st.rerun()

    resume_disabled = not is_running or not tracker.is_paused or tracker.stop_requested
    if resume_col.button(
        "恢复",
        key="sidebar_resume_analysis",
        use_container_width=True,
        disabled=resume_disabled,
    ):
        if tracker.resume():
            record_incomplete_task(
                tracker.ticker,
                tracker.trade_date,
                status="running",
                completed_stages=tracker.completed_stages,
            )
        st.rerun()

    can_stop = tracker is not None or bool(raw_ticker.strip())
    if stop_col.button(
        "停止",
        key="sidebar_stop_analysis",
        use_container_width=True,
        disabled=not can_stop,
    ):
        target_ticker = tracker.ticker if tracker is not None and tracker.ticker else ""
        target_date = (
            tracker.trade_date
            if tracker is not None and tracker.trade_date
            else trade_date
        )

        if not target_ticker:
            target_ticker, err = _resolve_user_input(raw_ticker)
            if err:
                st.error(f"❌ {err}")
                return

        if tracker is not None and tracker.is_running:
            tracker.request_stop()
            clear_incomplete_task(target_ticker, target_date)
        else:
            if tracker is not None:
                tracker.mark_stopped()
                st.session_state["tracker"] = None
            _clear_analysis_artifacts(target_ticker, target_date)

        st.session_state["viewing_history"] = None
        st.success("已清空当前进度；下一次开始分析会从头生成。")
        st.rerun()

    if tracker is not None and tracker.stop_requested:
        st.caption("正在停止并清空，收尾完成后可重新开始。")


def _render_llm_config() -> None:
    """Render LLM provider and model selection controls."""

    provider_idx = st.selectbox(
        "LLM 供应商",
        range(len(_PROVIDERS)),
        format_func=lambda i: _PROVIDER_DISPLAY[i],
        index=_default_provider_idx(),
        key="llm_provider_idx",
        help="选择你配置了 API Key 的供应商。默认值可在 .env 里用 TRADINGAGENTS_LLM_PROVIDER 指定",
    )
    provider_key = _PROVIDER_KEYS[provider_idx]
    st.session_state["llm_provider"] = provider_key

    if provider_key in MODEL_OPTIONS:
        quick_options = MODEL_OPTIONS[provider_key]["quick"]
        deep_options = MODEL_OPTIONS[provider_key]["deep"]

        quick_labels = [label for label, _ in quick_options]
        quick_values = [value for _, value in quick_options]
        deep_labels = [label for label, _ in deep_options]
        deep_values = [value for _, value in deep_options]

        quick_idx = st.selectbox(
            "快速思考模型",
            range(len(quick_options)),
            format_func=lambda i: quick_labels[i],
            index=_default_model_idx(
                quick_options, "TRADINGAGENTS_QUICK_THINK_LLM"
            ),
            key="quick_model_idx",
            help="用于常规分析任务，速度优先。默认值可在 .env 里用 TRADINGAGENTS_QUICK_THINK_LLM 指定",
        )
        st.session_state["quick_think_llm"] = quick_values[quick_idx]

        deep_idx = st.selectbox(
            "深度思考模型",
            range(len(deep_options)),
            format_func=lambda i: deep_labels[i],
            index=_default_model_idx(
                deep_options, "TRADINGAGENTS_DEEP_THINK_LLM"
            ),
            key="deep_model_idx",
            help="用于辩论/决策等需要深度推理的任务。默认值可在 .env 里用 TRADINGAGENTS_DEEP_THINK_LLM 指定",
        )
        st.session_state["deep_think_llm"] = deep_values[deep_idx]
    else:
        # 该 provider 没有预置模型清单（openrouter / openai_compatible），手填 ID。
        # 初值只取 .env 里显式配的值；没配就留空——上游默认的 gpt-5.4-mini 对这类
        # provider 未必是合法 ID，预填反而误导。
        custom_quick = st.text_input(
            "快速思考模型 ID",
            value=_configured("TRADINGAGENTS_QUICK_THINK_LLM") or "",
            key="custom_quick_model",
        )
        custom_deep = st.text_input(
            "深度思考模型 ID",
            value=_configured("TRADINGAGENTS_DEEP_THINK_LLM") or "",
            key="custom_deep_model",
        )
        st.session_state["quick_think_llm"] = custom_quick
        st.session_state["deep_think_llm"] = custom_deep

    base_url_required = provider_key == "openai_compatible"
    # 方舟两个套餐的端点是固定的，直接预填；其余 provider 沿用 .env 的全局 backend_url。
    if provider_key in ARK_PLAN_ENDPOINTS:
        default_base = ARK_PLAN_ENDPOINTS[provider_key][0]
    else:
        default_base = DEFAULT_CONFIG.get("backend_url") or ""
    # 按 provider 分开存：共用一个 key 时，在 A 家填的网关地址会跟着切换带到 B 家，
    # 把 A 家的中转地址连同 B 家的 Key 一起发出去。
    base_url = st.text_input(
        "API Base URL（第三方/代理" + ("·必填" if base_url_required else "，可选") + "）",
        value=default_base,
        key=f"llm_base_url_{provider_key}",
        placeholder="例: https://your-relay.example/v1",
        help=(
            "通过第三方中转/代理访问模型时填写网关地址；留空则用所选供应商的官方地址。"
            "初值取自 .env 的 TRADINGAGENTS_BACKEND_URL（或旧名 BACKEND_URL）；"
            "选中火山方舟套餐时预填该套餐的官方端点。"
            "API Key 仍从 .env 读取，每个供应商用各自的环境变量——"
            "OpenAI=OPENAI_API_KEY、DeepSeek=DEEPSEEK_API_KEY、"
            "通义=DASHSCOPE_API_KEY、智谱=ZHIPU_API_KEY、MiniMax=MINIMAX_API_KEY、"
            "Claude=ANTHROPIC_API_KEY、OpenRouter=OPENROUTER_API_KEY、xAI=XAI_API_KEY、"
            "方舟 Coding Plan=ARK_CODING_API_KEY、方舟 Agent Plan=ARK_AGENT_API_KEY"
            "（两者都可回落 ANTHROPIC_API_KEY）、"
            "OpenAI 兼容（自定义）=OPENAI_COMPATIBLE_API_KEY（也接受 OPENAI_API_KEY）。"
        ),
    )
    # app.py 只读这一个键，所以把当前 provider 的取值汇总到这里。
    st.session_state["llm_base_url"] = base_url
    if base_url_required:
        st.caption(
            "已选「OpenAI 兼容（自定义）」：**Base URL 必填**（你的网关，走标准 Chat "
            "Completions），模型 ID 手动填写，Key 在 .env 设 `OPENAI_COMPATIBLE_API_KEY`。"
        )

    if st.button("保存为默认配置", use_container_width=True):
        quick = st.session_state["quick_think_llm"]
        deep = st.session_state["deep_think_llm"]
        if not quick or not deep:
            st.warning("两个模型 ID 都填好再保存。")
        else:
            _save_defaults_to_env(
                {
                    "TRADINGAGENTS_LLM_PROVIDER": provider_key,
                    "TRADINGAGENTS_QUICK_THINK_LLM": quick,
                    "TRADINGAGENTS_DEEP_THINK_LLM": deep,
                }
            )
            st.success("已写入 .env。重启服务后默认就是这套配置。")


def render_sidebar() -> None:
    """Render the sidebar with input controls and history."""

    st.markdown(
        """
        <div style="text-align:center; margin-bottom:1.5rem;">
            <span style="font-size:2rem; font-weight:800; color:#ff5a1f;">Trading</span><span style="font-size:2rem; font-weight:800; color:#f5f1eb;">Agents</span><span style="font-size:2rem; font-weight:800; color:#f5f1eb;">-</span><span style="font-size:2rem; font-weight:800; color:#ff5a1f;">Astock</span>
            <div style="font-size:0.85rem; color:#888; margin-top:0.2rem;">
                A股多Agent投研系统
            </div>
            <div style="font-size:0.7rem; color:#555; margin-top:0.3rem;">
                by <a href="https://github.com/simonlin1212" style="color:#ff5a1f; text-decoration:none;">simonlin1212</a>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
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
        value=trade_date.replace(day=1),   # 默认本月第一天
        key="input_start_date",
        help="技术分析回溯到该日期（默认本月第一天）。分析区间 = 起始日期 → 分析日期，"
             "用于「按月」或自定义时段分析；留默认即分析当月至今。",
    )
    # 分析窗口天数 → market_lookback_days（下限 5 天，保证指标有意义）
    st.session_state["market_lookback_days"] = max((trade_date - start_date).days, 5)
    if start_date >= trade_date:
        st.caption("⚠️ 起始日期应早于分析日期，已按最小窗口（5 天）处理。")

    with st.expander("⚙️ 模型配置", expanded=False):
        _render_llm_config()

    tracker = st.session_state.get("tracker")
    is_busy = tracker is not None and tracker.is_running
    is_stopping = is_busy and tracker.stop_requested

    if st.button(
        "开始分析" if not is_busy else "停止中..." if is_stopping else "分析进行中...",
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
                "fresh": True,
            }
            st.session_state["viewing_history"] = None

    _render_analysis_controls(ticker, trade_date)

    st.markdown("---")
    st.markdown("#### 未完成任务")

    incomplete = get_incomplete_history()
    if not incomplete:
        st.caption("暂无未完成任务")
    else:
        for entry in incomplete[:10]:
            t, d = entry["ticker"], entry["trade_date"]
            status_label = {
                "error": "出错",
                "paused": "已暂停",
                "running": "进行中",
            }.get(entry.get("status"), "可继续")
            step = entry.get("checkpoint_step")
            step_label = f" · step {step}" if step is not None else ""
            label = f"{t}  ·  {d}  ·  {status_label}{step_label}"
            if st.button(
                label,
                key=f"resume_{t}_{d}",
                use_container_width=True,
                disabled=is_busy,
            ):
                st.session_state["start_analysis"] = {
                    "ticker": t,
                    "trade_date": d,
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
    st.caption("⚠️ 仅供学习研究，不构成投资建议")
