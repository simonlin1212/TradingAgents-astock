"""TradingAgents A股分析 — Streamlit Web UI."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

load_dotenv(_PROJECT_ROOT / ".env")

from tradingagents.default_config import DEFAULT_CONFIG  # noqa: E402

from web.components.progress_panel import render_progress  # noqa: E402
from web.components.report_viewer import render_report  # noqa: E402
from web.components.sidebar import render_sidebar  # noqa: E402
from web.history import extract_signal, load_analysis  # noqa: E402
from web.progress import ProgressTracker  # noqa: E402
from web.runner import run_analysis_in_thread  # noqa: E402

# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="TradingAgents-Astock A股分析",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Theme ────────────────────────────────────────────────────────────────────
if st.session_state.get("theme_choice", "暗黑模式") == "明亮模式":
    bg_main = "#f5f5f5"
    bg_sidebar = "#ffffff"
    text_color = "#1a1a1a"
    border_color = "#e0e0e0"
    input_bg = "#ffffff"
    secondary_bg = "#f0f0f0"
    secondary_hover = "#e0e0e0"
    dim_text = "#666"
    card_border = "#e0e0e0"
    metric_label = "#555"
else:
    bg_main = "#0a0a0a"
    bg_sidebar = "#0f0f0f"
    text_color = "#f5f1eb"
    border_color = "#1a1a1a"
    input_bg = "#161616"
    secondary_bg = "#161616"
    secondary_hover = "#1e1e1e"
    dim_text = "#888"
    card_border = "#222"
    metric_label = "#888"

# ── Custom CSS ───────────────────────────────────────────────────────────────

st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&display=swap');

    button[data-testid="collapsedControl"] {{ display: flex !important; }}

    html, body, [class*="css"] {{
        font-family: 'Inter', -apple-system, sans-serif;
        color: {text_color};
    }}
    .stApp {{
        background: {bg_main};
    }}
    section[data-testid="stSidebar"] {{
        background: {bg_sidebar};
        border-right: 1px solid {border_color};
    }}
    .stMetric label {{ color: {metric_label} !important; font-size: 0.8rem !important; }}
    .stMetric [data-testid="stMetricValue"] {{
        color: #ff5a1f !important;
        font-weight: 700 !important;
    }}
    .stProgress > div > div > div {{
        background: linear-gradient(90deg, #ff5a1f, #ff8c42) !important;
    }}
    button[kind="primary"] {{
        background: linear-gradient(135deg, #ff5a1f, #ff8c42) !important;
        border: none !important;
        font-weight: 700 !important;
        letter-spacing: 0.05em !important;
        box-shadow: 0 4px 15px rgba(255,90,31,0.3) !important;
        transition: all 0.2s ease !important;
    }}
    button[kind="primary"]:hover {{
        background: linear-gradient(135deg, #e04d15, #ff5a1f) !important;
        box-shadow: 0 6px 20px rgba(255,90,31,0.4) !important;
        transform: translateY(-1px) !important;
    }}
    button[kind="secondary"] {{
        background: {secondary_bg} !important;
        border: 1px solid {border_color} !important;
        color: {text_color} !important;
        transition: all 0.2s ease !important;
    }}
    button[kind="secondary"]:hover {{
        background: {secondary_hover} !important;
        border-color: #ff5a1f !important;
        color: #ff5a1f !important;
    }}
    .stExpander {{
        border: 1px solid {card_border} !important;
        border-radius: 8px !important;
    }}
    .stTabs [data-baseweb="tab"] {{ color: {dim_text} !important; }}
    .stTabs [aria-selected="true"] {{
        color: #ff5a1f !important;
        border-bottom-color: #ff5a1f !important;
    }}
    div[data-testid="stDownloadButton"] button {{
        background: #1a1a2e !important;
        border: 1px solid #ff5a1f !important;
        color: #ff5a1f !important;
    }}
    input[data-testid="stTextInputRootElement"] input,
    .stTextInput input {{
        background: {input_bg} !important;
        border-color: {border_color} !important;
        color: {text_color} !important;
    }}
    .stTextInput input:focus {{
        border-color: #ff5a1f !important;
        box-shadow: 0 0 0 1px #ff5a1f !important;
    }}
    .stDateInput input {{
        background: {input_bg} !important;
        border-color: {border_color} !important;
        color: {text_color} !important;
    }}
    /* Labels and captions */
    .stCaption, .stMarkdown p, .stMarkdown span {{
        color: {text_color} !important;
    }}
    section[data-testid="stSidebar"] input {{
        color: {text_color} !important;
    }}
    section[data-testid="stSidebar"] input::placeholder {{
        color: {dim_text} !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Build config ─────────────────────────────────────────────────────────────

def _build_config() -> dict:
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "deepseek"
    config["deep_think_llm"] = "deepseek-chat"
    config["quick_think_llm"] = "deepseek-chat"
    config["data_vendors"] = {
        "core_stock_apis": "a_stock",
        "technical_indicators": "a_stock",
        "fundamental_data": "a_stock",
        "news_data": "a_stock",
        "signal_data": "a_stock",
    }
    config["max_debate_rounds"] = 1
    config["max_risk_discuss_rounds"] = 1
    config["output_language"] = "Chinese"
    return config


# ── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    render_sidebar()


# ── Handle "Start Analysis" trigger ──────────────────────────────────────────

start_req = st.session_state.pop("start_analysis", None)
if start_req:
    tracker = ProgressTracker(
        ticker=start_req["ticker"],
        trade_date=start_req["trade_date"],
    )
    st.session_state["tracker"] = tracker
    run_analysis_in_thread(
        ticker=start_req["ticker"],
        trade_date=start_req["trade_date"],
        start_date=start_req.get("start_date", start_req["trade_date"]),
        config=_build_config(),
        tracker=tracker,
    ) #起始日期


# ── Main area state machine ─────────────────────────────────────────────────

tracker: ProgressTracker | None = st.session_state.get("tracker")
viewing_history: str | None = st.session_state.get("viewing_history")

# State 1: Viewing a historical analysis
if viewing_history:
    try:
        state = load_analysis(viewing_history)
        signal = extract_signal(state)
        ticker = Path(viewing_history).parent.parent.name
        trade_date = Path(viewing_history).stem.replace("full_states_log_", "")
        render_report(state, ticker, trade_date, signal)
    except Exception as exc:
        st.error(f"加载失败: {exc}")

# State 2: Analysis running
elif tracker and tracker.is_running:
    render_progress(tracker)
    time.sleep(2)
    st.rerun()

# State 3: Analysis complete
elif tracker and tracker.is_complete:
    render_report(
        tracker.final_state,
        tracker.ticker,
        tracker.trade_date,
        tracker.signal,
        elapsed=tracker.elapsed,
    )

# State 4: Analysis errored
elif tracker and tracker.error:
    st.error(f"分析失败: {tracker.error}")
    if st.button("重试"):
        st.session_state.pop("tracker", None)
        st.rerun()

# State 0: Idle — welcome screen
else:
    st.markdown(
        f"""
        <div style="
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 60vh;
            text-align: center;
        ">
            <div style="font-size: 4rem; margin-bottom: 1rem;">📈</div>
            <div style="
                font-size: 2.5rem;
                font-weight: 900;
                margin-bottom: 0.5rem;
            ">
 <span style="text-shadow: 0 0 0 #ff5a1f; -webkit-text-fill-color: #ff5a1f;">Trading</span><span style="text-shadow: 0 0 0 {text_color}; -webkit-text-fill-color: {text_color};">Agents</span>          </div>
            <div style="color: {dim_text}; font-size: 1.1rem; max-width: 500px; line-height: 1.6;">
                A股多Agent投研分析系统<br>
                7位AI分析师 → 质量门控 → 多空辩论 → 风控评估 → 最终决策
            </div>
            <div style="
                margin-top: 2rem;
                padding: 1rem 2rem;
                border: 1px solid {card_border};
                border-radius: 12px;
                color: {dim_text};
                font-size: 0.9rem;
            ">
                ← 在左侧输入股票代码，开始分析
            </div>
            <div style="
                margin-top: 2.5rem;
                padding: 0.8rem 1.5rem;
                color: {dim_text};
                font-size: 0.75rem;
                max-width: 500px;
                line-height: 1.6;
                border-top: 1px solid {border_color};
            ">
                ⚠️ 本项目仅供学习研究与技术演示，不构成任何投资建议。<br>
                投资决策请咨询持牌专业机构。作者不对使用本工具产生的任何损失承担责任。
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
