"""Sidebar: stock input, LLM config, and history list."""

from __future__ import annotations

import json
import logging
import os
from datetime import date
from pathlib import Path

import streamlit as st

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.checkpointer import clear_checkpoint
from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS
from web.history import (
    clear_incomplete_task,
    get_history,
    get_incomplete_history,
    record_incomplete_task,
)

logger = logging.getLogger(__name__)

# ── LLM config persistence ────────────────────────────────────────────────────
# Saves model selection to a JSON file so it survives browser tab close/reopen.
# 放用户目录而不是包目录：pip 安装时包目录在 site-packages（常只读、升级即清空），
# git clone 用户则会在仓库里多出一个未跟踪文件。~/.tradingagents/ 是本项目其它用户态
# 数据（logs / cache / memory）已经在用的位置。
_LLM_CONFIG_PATH = Path(os.path.expanduser("~")) / ".tradingagents" / "llm_config.json"
# 侧栏「个人 Claude 订阅覆盖」选项的取值；selectbox 的 widget 键是 subscription_scope_idx，
# 恢复时必须写这个索引，只写派生值 subscription_scope 会在渲染时被覆盖回默认。
_SCOPE_VALUES = ["off", "deep", "all"]


def _load_saved_llm_config() -> None:
    """Restore user's last model selection into session_state defaults."""
    try:
        cfg = json.loads(_LLM_CONFIG_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return
    provider_key = cfg.get("llm_provider", "")
    try:
        idx = _PROVIDER_KEYS.index(provider_key)
    except ValueError:
        idx = 0
    st.session_state.setdefault("llm_provider_idx", idx)
    st.session_state.setdefault("llm_provider", _PROVIDER_KEYS[idx])
    st.session_state.setdefault("quick_model_idx", cfg.get("quick_model_idx", 0))
    st.session_state.setdefault("deep_model_idx", cfg.get("deep_model_idx", 0))
    st.session_state.setdefault("llm_base_url", cfg.get("llm_base_url", ""))
    scope = cfg.get("subscription_scope", "off")
    st.session_state.setdefault("subscription_scope", scope)
    st.session_state.setdefault(
        "subscription_scope_idx", _SCOPE_VALUES.index(scope) if scope in _SCOPE_VALUES else 0
    )
    if cfg.get("agent_sdk_model"):
        st.session_state.setdefault("agent_sdk_model", cfg["agent_sdk_model"])
    st.session_state.setdefault("codex_cli_auth_mode", cfg.get("codex_cli_auth_mode", "chatgpt"))
    st.session_state.setdefault("codex_cli_path", cfg.get("codex_cli_path", ""))
    st.session_state.setdefault("codex_cli_quick_model", cfg.get("codex_cli_quick_model", ""))
    st.session_state.setdefault("codex_cli_deep_model", cfg.get("codex_cli_deep_model", ""))
    st.session_state.setdefault("codex_cli_reasoning_effort", cfg.get("codex_cli_reasoning_effort"))
    for key in ("custom_quick_model", "custom_deep_model"):
        if key in cfg and cfg[key]:
            st.session_state.setdefault(key, cfg[key])


def _save_llm_config() -> None:
    """Persist current LLM config to disk (called before analysis)."""
    cfg = {
        "llm_provider": st.session_state.get("llm_provider", "minimax"),
        "quick_model_idx": st.session_state.get("quick_model_idx", 0),
        "deep_model_idx": st.session_state.get("deep_model_idx", 0),
        "llm_base_url": st.session_state.get("llm_base_url", ""),
        "subscription_scope": st.session_state.get("subscription_scope", "off"),
        "codex_cli_auth_mode": st.session_state.get("codex_cli_auth_mode", "chatgpt"),
        "codex_cli_path": st.session_state.get("codex_cli_path", ""),
        "codex_cli_quick_model": st.session_state.get("codex_cli_quick_model", ""),
        "codex_cli_deep_model": st.session_state.get("codex_cli_deep_model", ""),
        "codex_cli_reasoning_effort": st.session_state.get("codex_cli_reasoning_effort"),
    }
    if st.session_state.get("agent_sdk_model"):
        cfg["agent_sdk_model"] = st.session_state["agent_sdk_model"]
    for key in ("custom_quick_model", "custom_deep_model"):
        val = st.session_state.get(key)
        if val:
            cfg[key] = val
    # 持久化失败（目录只读 / 磁盘满）只记 warning，不得打断「开始分析」主流程
    try:
        _LLM_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LLM_CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))
    except OSError as exc:
        logger.warning("LLM 配置持久化失败（不影响本次分析）: %s", exc)


# Provider display names in recommended order
_PROVIDERS: list[tuple[str, str]] = [
    ("MiniMax（推荐·国内直连）", "minimax"),
    ("DeepSeek", "deepseek"),
    ("通义千问 Qwen", "qwen"),
    ("智谱 GLM", "glm"),
    ("OpenAI", "openai"),
    ("Codex CLI（本机 Codex 登录）", "codex_cli"),
    ("Anthropic", "anthropic"),
    ("Google Gemini", "google"),
    ("xAI Grok", "xai"),
    ("OpenRouter（聚合·填 vendor/model 形式 ID）", "openrouter"),
    ("OpenAI 兼容（自定义 base_url·9Router/AI Router/自建代理）", "openai_compatible"),
    ("Ollama（本地）", "ollama"),
]

_PROVIDER_DISPLAY = [name for name, _ in _PROVIDERS]
_PROVIDER_KEYS = [key for _, key in _PROVIDERS]


def _setting_widget_key(setting: str, default="") -> str:
    """Keep conditional widget values when Streamlit removes hidden widget keys."""
    widget_key = f"_llm_widget_{setting}"
    st.session_state.setdefault(widget_key, st.session_state.get(setting, default))
    return widget_key


def _text_setting(label: str, setting: str, **kwargs) -> str:
    value = st.text_input(label, key=_setting_widget_key(setting), **kwargs)
    st.session_state[setting] = value
    return value


def _codex_model_options() -> list[str]:
    """Offer visible model IDs from the local Codex cache when available."""
    codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    try:
        cache = json.loads((codex_home / "models_cache.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    models = cache.get("models", []) if isinstance(cache, dict) else []
    if not isinstance(models, list):
        return []
    return list(dict.fromkeys(
        model["slug"] for model in models
        if isinstance(model, dict)
        and model.get("visibility") == "list"
        and isinstance(model.get("slug"), str)
        and model["slug"].strip()
    ))


def _codex_model_setting(tier: str, label: str, options: list[str]) -> str:
    setting = f"codex_cli_{tier}_model"
    current = str(st.session_state.get(setting) or "").strip()
    custom = "__custom__"
    choice_setting = f"{setting}_choice"
    initial = current if current in options else custom if current else ""
    choices = ["", *options, custom]
    widget_key = _setting_widget_key(choice_setting, initial)
    if st.session_state[widget_key] not in choices:
        # Codex can refresh its cache while the Web session is open.
        st.session_state[widget_key] = custom if current else ""
    choice = st.selectbox(
        label,
        options=choices,
        format_func=lambda value: (
            "CLI 默认（实际 ID 未知）" if value == "" else
            "自定义模型 ID" if value == custom else value
        ),
        key=widget_key,
        help="本机 Codex 缓存中的模型 ID 可能过期，实际可用性由 CLI 在运行时校验。",
    )
    st.session_state[choice_setting] = choice
    if choice == custom:
        model = _text_setting("自定义模型 ID", setting, placeholder="例如 gpt-6-sol")
    else:
        model = choice
        st.session_state[setting] = model
    return model.strip()


def _model_index_widget_key(provider: str, tier: str, count: int,
                            previous_provider: str | None) -> str:
    # Distinct widget keys also prevent one provider's index from being out of
    # range or replacing another provider's choice when the selector changes.
    setting = f"{provider}_{tier}_model_idx"
    if setting not in st.session_state:
        initial = st.session_state.get(f"{tier}_model_idx", 0) if previous_provider == provider else 0
        st.session_state[setting] = initial if isinstance(initial, int) and 0 <= initial < count else 0
    widget_key = _setting_widget_key(setting, 0)
    value = st.session_state[widget_key]
    if not isinstance(value, int) or not 0 <= value < count:
        st.session_state[widget_key] = 0
    return widget_key


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

    previous_provider = st.session_state.get("llm_provider")
    provider_idx = st.selectbox(
        "LLM 供应商",
        range(len(_PROVIDERS)),
        format_func=lambda i: _PROVIDER_DISPLAY[i],
        key="llm_provider_idx",
        help="选择你配置了 API Key 的供应商",
    )
    provider_key = _PROVIDER_KEYS[provider_idx]
    st.session_state["llm_provider"] = provider_key

    if provider_key == "codex_cli":
        codex_models = _codex_model_options()
        quick_model = _codex_model_setting("quick", "快速思考 Codex 模型", codex_models)
        deep_model = _codex_model_setting("deep", "深度思考 Codex 模型", codex_models)
        st.session_state["quick_think_llm"] = quick_model
        st.session_state["deep_think_llm"] = deep_model
        effort_choice = st.selectbox(
            "Codex 推理强度（快速/深度共用）",
            options=["default", "low", "medium", "high", "xhigh"],
            format_func=lambda value: {
                "default": "CLI 默认（强度未指定）",
                "low": "低 · low", "medium": "中 · medium",
                "high": "高 · high", "xhigh": "很高 · xhigh",
            }[value],
            key=_setting_widget_key(
                "codex_cli_reasoning_effort_choice",
                st.session_state.get("codex_cli_reasoning_effort") or "default",
            ),
            help="传给 Codex CLI 的 model_reasoning_effort；具体可用强度取决于模型。",
        )
        st.session_state["codex_cli_reasoning_effort_choice"] = effort_choice
        effort = None if effort_choice == "default" else effort_choice
        st.session_state["codex_cli_reasoning_effort"] = effort
        if not quick_model.strip() or not deep_model.strip():
            st.caption("留空的模型会由 Codex CLI 自行选默认值；当前实现无法确认该默认值的实际模型 ID。若要明确知道本次使用的模型，请填写模型 ID。")
        st.caption(
            f"将使用：快速 {quick_model.strip() or 'CLI 默认（ID 未知）'} · "
            f"深度 {deep_model.strip() or 'CLI 默认（ID 未知）'} · "
            f"推理强度 {effort or 'CLI 默认'}"
        )
    elif provider_key in MODEL_OPTIONS:
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
            key=_model_index_widget_key(provider_key, "quick", len(quick_options), previous_provider),
            help="用于常规分析任务，速度优先",
        )
        st.session_state[f"{provider_key}_quick_model_idx"] = quick_idx
        st.session_state["quick_model_idx"] = quick_idx
        st.session_state["quick_think_llm"] = quick_values[quick_idx]

        deep_idx = st.selectbox(
            "深度思考模型",
            range(len(deep_options)),
            format_func=lambda i: deep_labels[i],
            key=_model_index_widget_key(provider_key, "deep", len(deep_options), previous_provider),
            help="用于辩论/决策等需要深度推理的任务",
        )
        st.session_state[f"{provider_key}_deep_model_idx"] = deep_idx
        st.session_state["deep_model_idx"] = deep_idx
        st.session_state["deep_think_llm"] = deep_values[deep_idx]
    else:
        custom_quick = _text_setting("快速思考模型 ID", "custom_quick_model")
        custom_deep = _text_setting("深度思考模型 ID", "custom_deep_model")
        st.session_state["quick_think_llm"] = custom_quick
        st.session_state["deep_think_llm"] = custom_deep

    if provider_key != "codex_cli":
        base_url_required = provider_key == "openai_compatible"
        _text_setting(
            "API Base URL（第三方/代理" + ("·必填" if base_url_required else "，可选") + "）",
            "llm_base_url",
            placeholder="例: https://your-relay.example/v1",
            help=(
                "通过第三方中转/代理访问模型时填写网关地址；留空则用所选供应商的官方地址。"
                "API Key 仍从 .env 读取，每个供应商用各自的环境变量——"
                "OpenAI=OPENAI_API_KEY、DeepSeek=DEEPSEEK_API_KEY、"
                "通义=DASHSCOPE_API_KEY、智谱=ZHIPU_API_KEY、MiniMax=MINIMAX_API_KEY、"
                "Claude=ANTHROPIC_API_KEY、OpenRouter=OPENROUTER_API_KEY、xAI=XAI_API_KEY、"
                "OpenAI 兼容（自定义）=OPENAI_COMPATIBLE_API_KEY（也接受 OPENAI_API_KEY）。"
                "也可在 .env 里设 BACKEND_URL 代替此处。"
            ),
        )
        if base_url_required:
            st.caption(
                "已选「OpenAI 兼容（自定义）」：**Base URL 必填**（你的网关，走标准 Chat "
                "Completions），模型 ID 手动填写，Key 在 .env 设 `OPENAI_COMPATIBLE_API_KEY`。"
            )
    else:
        auth_widget_key = _setting_widget_key("codex_cli_auth_mode", "chatgpt")
        auth_mode = st.selectbox(
            "Codex CLI 认证方式",
            options=["chatgpt", "api_key"],
            format_func=lambda value: (
                "ChatGPT 登录 / 订阅额度" if value == "chatgpt"
                else "OpenAI API Key / 按 API 用量计费"
            ),
            key=auth_widget_key,
            help="ChatGPT 模式使用本机 `codex login` 会话。API Key 模式只在明确选择后读取 CODEX_API_KEY 或 OPENAI_API_KEY，并按 API 计费。",
        )
        st.session_state["codex_cli_auth_mode"] = auth_mode
        if auth_mode == "chatgpt":
            st.caption("运行前核验 `codex login status` 必须显示 ChatGPT 登录；认证失败时停止，不会改用 OpenAI API。")
        else:
            st.caption("此模式会产生 OpenAI API 费用。请在环境变量 `CODEX_API_KEY` 或 `OPENAI_API_KEY` 中配置 Key；Key 不会写入配置文件。")
        _text_setting("Codex CLI 可执行文件（留空则查找 PATH）", "codex_cli_path", placeholder="codex")

    # ── 个人 Claude 订阅额度（可选，仅个人自用）────────────────────────
    _scope_labels = [
        "关闭（走上面选的供应商）",
        "仅深度节点（Research/Portfolio）",
        "所有节点（含 7 个工具分析师）",
    ]
    scope_idx = st.selectbox(
        "个人 Claude 订阅覆盖 (Agent SDK)",
        range(len(_scope_labels)),
        format_func=lambda i: _scope_labels[i],
        key="subscription_scope_idx",
        help=(
            "让部分/全部节点经 Claude Agent SDK 走你个人 Pro/Max 订阅额度，"
            "而非按 token 计费。「所有节点」含 7 个工具分析师（其工具调用已桥接到订阅）。"
            "需装 [agentsdk] 依赖，且本机 claude 已登录（或设 CLAUDE_CODE_OAUTH_TOKEN）。"
        ),
    )
    scope = _SCOPE_VALUES[scope_idx]
    st.session_state["subscription_scope"] = scope
    if scope != "off":
        # 用别名而非写死版本号：claude CLI 的 opus/sonnet 恒指向最新模型。
        st.session_state.setdefault("agent_sdk_model", "opus")
        _text_setting(
            "订阅使用的 Claude 模型",
            "agent_sdk_model",
            help=(
                "填别名 opus / sonnet（恒指向最新模型，推荐）或完整模型 id。"
                "撞额度/失败时自动降级到上面选的供应商 + 对应模型。"
            ),
        )
        if scope == "all":
            st.caption(
                "⚠️ 「所有节点」会把 7 个分析师 + 多空/交易员/风险辩手全部压到订阅上，"
                "订阅是按额度限流的，跑几轮就可能撞上限。可在 config 里把 "
                "`agent_sdk_quick_model` 设为 `sonnet` 降低消耗（默认已是）。"
            )
        if os.getenv("ANTHROPIC_API_KEY"):
            st.info(
                "检测到 ANTHROPIC_API_KEY。它**不会**泄进 Agent SDK 子进程"
                "（已在子进程环境显式置空），所以订阅额度照常生效；"
                "父进程保留它，是为了让 `anthropic` 仍能作为撞额度后的降级 provider。"
                "如果你并不打算保留付费降级，可在 .env 里清掉它。"
            )


def render_sidebar() -> None:
    """Render the sidebar with input controls and history."""
    # Restore saved LLM config on every render so selectboxes start at the user's last selection.
    _load_saved_llm_config()

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

    codex_selected = st.session_state.get("llm_provider_idx") == _PROVIDER_KEYS.index("codex_cli")
    with st.expander("⚙️ 模型配置", expanded=codex_selected):
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
        _save_llm_config()  # persist model choice before running
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
