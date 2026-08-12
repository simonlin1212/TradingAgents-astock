<p align="center"><a href="README.md">简体中文</a> | <b>English</b></p>

<h1 align="center">TradingAgents-Astock</h1>

<p align="center">
  A China A-share deep-specialization fork of <a href="https://github.com/TauricResearch/TradingAgents">TauricResearch/TradingAgents</a> (65K ⭐)<br>
  Fully Apache 2.0 open source · <code>pip install</code> and run · zero external service dependencies
</p>

<p align="center">
  <b>⚠️ This project is an engineering implementation and research reproduction of the <a href="https://arxiv.org/abs/2412.20138">TradingAgents paper</a>, intended for research and educational use.<br>
  It does not constitute investment advice, nor does it provide any investment service.</b>
</p>

<p align="center">
  <a href="https://github.com/simonlin1212/tradingagents-astock/stargazers"><img alt="Stars" src="https://img.shields.io/github/stars/simonlin1212/tradingagents-astock?style=social"/></a>
  <a href="https://github.com/simonlin1212/tradingagents-astock/network/members"><img alt="Forks" src="https://img.shields.io/github/forks/simonlin1212/tradingagents-astock?style=social"/></a>
  <a href="https://arxiv.org/abs/2412.20138"><img alt="Paper" src="https://img.shields.io/badge/paper-arXiv_2412.20138-B31B1B?logo=arxiv"/></a>
  <a href="./LICENSE"><img alt="License" src="https://img.shields.io/badge/License-Apache_2.0-blue"/></a>
  <a href="./CHANGES_FROM_UPSTREAM.md"><img alt="Changes" src="https://img.shields.io/badge/changes-CHANGES-orange"/></a>
</p>

<p align="center">
  <a href="#why-this-fork">Why This Fork</a> ·
  <a href="#comparison-with-upstream">Comparison</a> ·
  <a href="#architecture-overview">Architecture</a> ·
  <a href="#7-analyst-roles">Analyst Roles</a> ·
  <a href="#data-sources">Data Sources</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#web-ui">Web UI</a> ·
  <a href="#common-troubleshooting">Troubleshooting</a>
</p>

---

## Why This Fork

The original TradingAgents is an excellent multi-agent research framework, but it's designed for the US stock market: data comes from Yahoo Finance / Alpha Vantage, analysts don't understand the A-share system, and the debates and decision-making are entirely geared toward the US market.

**Goal of this Fork**: To truly adapt TradingAgents' multi-agent debate architecture to the A-share market. This is not a simple translation, but a deep specialization across three dimensions: data layer, agent roles, and trading rules.

### Core Modifications

| Dimension | Original | This Fork |
|-----------|----------|-----------|
| **Data Source** | Yahoo Finance / Alpha Vantage | mootdx + Eastmoney + Sina + Tonghuashun (all free direct connections) |
| **Analyst Roles** | 4 (Market / Sentiment / News / Fundamentals) | **7** (+Policy Analyst / Hot Money Tracker / Lock-up Expiry Monitor) |
| **Trading Rules** | US Market (T+0, no price limits) | A-share Market (T+1, price limits, minimum lot size, trading hours) |
| **Output Language** | English | Chinese reports (internal debates remain in English to maintain reasoning quality) |
| **Alpha Benchmark** | SPY | CSI 300 (沪深300) |

---
## Comparison with Upstream

| Feature | Original TradingAgents | **This Fork** |
|---------|------------------------|---------------|
| License | Apache 2.0 | **Full Apache 2.0** |
| Deployment Dependency | pip install | **Ready to use** |
| A-share Data | ❌ | **mootdx + East Money + Sina + Tonghuashun (direct HTTP)** |
| A-share Specialized Roles | ❌ | **3 deep roles: Policy / Hot Money / Lockup Expiry** |
| A-share Trading Constraints | ❌ | **Full coverage: T+1 / Price Limits / Lot Size / ST** |
## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    7 Analyst Research Report Generation  │
│  Market → Social → News → Fundamentals                   │
│  → Policy → Hot Money → Lockup                           │
│         (Each Analyst has tool loop)                     │
├─────────────────────────────────────────────────────────┤
│               Bull vs Bear Investment Research Debate    │
│         Bull Researcher ←→ Bear Researcher               │
│               (Up to N rounds of debate)                 │
├─────────────────────────────────────────────────────────┤
│              Research Manager Comprehensive Assessment   │
│         (Deep thinking LLM, outputs investment plan)    │
├─────────────────────────────────────────────────────────┤
│                  Trader Trading Plan                     │
│         (A-share constraints: T+1/price limit/lot size) │
├─────────────────────────────────────────────────────────┤
│        Aggressive ←→ Conservative ←→ Neutral             │
│               Three-way Risk Debate                      │
├─────────────────────────────────────────────────────────┤
│            Portfolio Manager Final Decision              │
│     (Deep thinking LLM, outputs rating + rationale)     │
└─────────────────────────────────────────────────────────┘
```

**Dual LLM Design**:
- `quick_think_llm`: All Analysts, Researchers, Traders, Risk Debaters
- `deep_think_llm`: Research Manager and Portfolio Manager (requires comprehensive global information for decision making)

---
## 7 Analyst Roles

### Original 4 Roles (A-share Adapted)

| Role | Responsibilities | Data Tools |
|------|----------------|------------|
| 🏪 Market Analyst | K-line patterns, technical indicators, volume-price analysis | `get_stock_data`, `get_indicators` |
| 💬 Sentiment Analyst | Social media sentiment, retail investor discussion heat | `get_news` |
| 📰 News Analyst | Industry news, announcements, macro events | `get_news`, `get_global_news`, `get_insider_transactions` |
| 📊 Fundamental Analyst | Financial statement triad, profitability, valuation | `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement` |

### A-share Specific 3 Roles (New)

| Role | Responsibilities | Data Tools | Why It's Needed |
|------|----------------|------------|-----------------|
| 🏛️ Policy Analyst | Regulatory policy, industrial policy, window guidance | `get_news`, `get_global_news` | A-share is a policy-driven market, policy changes directly impact sector rotation |
| 🔥 Hot Money Tracker | Dragon-Tiger lists, large order flow, main force capital dynamics | `get_stock_data`, `get_news`, `get_insider_transactions` | Hot money is the core force behind short-term A-share pricing |
| 🔓 Lock-up Monitor | Restricted share unlocks, major shareholder reductions, equity pledges | `get_insider_transactions`, `get_news`, `get_fundamentals` | Lock-up expiration is a unique, major supply shock factor for A-shares |

The reports from all 7 analysts will feed into subsequent Bull/Bear debates and three-way risk debates, ensuring A-share specific factors are integrated throughout the entire decision-making chain.
## Data Sources

All free, no API key, no point wall:

| Source | Protocol | Content Provided |
|------|---------|---------|
| **mootdx** | TCP 7709 | OHLCV K-lines, financial snapshots, F10 text |
| **Tencent Finance** | HTTP (`qt.gtimg.cn`) | PE / PB / Market Cap / Turnover Rate (real-time) |
| **East Money** | HTTP (datacenter / push2) | Dragon & Tiger List, Restricted Share Unlocking, Sector Quotes, Individual Stock Info |
| **Sina Finance** | HTTP | K-line history, Financial Statements (3 tables) |
| **Tonghuashun** | HTTP (10jqka) | EPS Consensus Estimates |
| **Cailianshe** | HTTP (cls.cn) | Global Financial News Flash |
| **Baidu Stock Market** | HTTP (finance.pae.baidu) | Concept Sector Classification, Capital Flow |

> Completely independent of Tushare (point wall), Alpha Vantage (overseas API), Yahoo Finance (does not support A-shares).

---

> **Data Source Priority & East Money Anti-blocking (v0.2.11)**: If quotes / K-lines / market cap / financials can be obtained from mootdx (Tongdaxin TCP, IP not blocked) or Tencent, always use them; East Money is only used for its unique data (Dragon & Tiger List / Unlocking / Capital Flow / Sector / Individual Stock News, etc.). All East Money requests go through the built-in throttling entry `_em_get()`: serial rate limiting (default interval ≥1s + 0.1~0.5s random jitter) + reusing Keep-Alive sessions. Multiple agents running batch analysis will no longer trigger temporary IP blocking (East Money risk control tested: >5 requests per second / concurrency ≥10 / ≥200 requests in 1 minute triggers blocking). For batch scenarios, set the environment variable `EM_MIN_INTERVAL=1.5~2` to further reduce speed. **Only East Money is rate-limited; mootdx / Tencent / Sina / Tonghuashun / Cailianshe / Baidu are unaffected.**
## Quick Start

### 1. Environment Setup

```bash
# Python >= 3.10
git clone https://github.com/simonlin1212/tradingagents-astock.git
cd tradingagents-astock
pip install -e .

# (Optional) Google Gemini — there is no [google] extra; install it explicitly (see FAQ):
pip install --no-deps "langchain-google-genai>=4.0.0"
pip install "google-genai>=1.53.0" "httpx>=0.28.1"
```

> **Ready to use after installation, no Docker required.** After installing, run `streamlit run web/app.py` (Web UI) or `tradingagents` (CLI) directly. See the "Web UI" and "CLI" sections below. Docker is only an optional deployment method and not needed for local development.

### 2. Configure LLM

> **API Key is required.** Subscription-based plans like Claude or ChatGPT cannot be used. Each analysis requires 30-50 LLM calls, which only the API mode supports.

Create a `.env` file in the project root and configure it based on your chosen provider:

```bash
# ── Option A: MiniMax (Recommended for direct China access, cost-effective) ──
MINIMAX_API_KEY=sk-xxx
# Apply at: https://platform.minimaxi.com/

# ── Option B: DeepSeek ─────────────────────────────────────────────────────
DEEPSEEK_API_KEY=sk-xxx
# Apply at: https://platform.deepseek.com/

# ── Option C: Zhipu GLM ────────────────────────────────────────────────────
ZHIPU_API_KEY=xxx
# Apply at: https://open.bigmodel.cn/

# ── Option D: Tongyi Qianwen Qwen ──────────────────────────────────────────
DASHSCOPE_API_KEY=sk-xxx
# Apply at: https://dashscope.console.aliyun.com/

# ── Option E: OpenAI ───────────────────────────────────────────────────────
OPENAI_API_KEY=sk-xxx

# ── Option F: Anthropic ────────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-xxx

# ── Option G: Kimi (Anthropic-compatible API) ───────────────────────────────
ANTHROPIC_API_KEY=your-kimi-token
ANTHROPIC_BASE_URL=https://api.kimi.com/coding/
# ⚠️ Both are required. With the key but no endpoint, requests go to Anthropic
#    itself and fail with "401 invalid x-api-key". The endpoint can also be set
#    as `backend_url` in the config (see below).
# ⚠️ Do not use ANTHROPIC_AUTH_TOKEN — that is the Claude Code CLI convention.
#    This project runs on langchain, which only reads ANTHROPIC_API_KEY.

# ── Option H: Any OpenAI-compatible gateway (9Router / AI Router / self-hosted proxy) ──
OPENAI_COMPATIBLE_API_KEY=sk-xxx     # Also accepts OPENAI_API_KEY
BACKEND_URL=https://your-relay.example/v1   # Your gateway URL (can also be set in the Web sidebar "API Base URL")
```

### 3. Run Analysis

Modify the configuration based on your chosen provider:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph

# ── MiniMax Example (Recommended) ──────────────────────────────────────────
config = {
    "llm_provider": "minimax",
    "deep_think_llm": "MiniMax-M2.7",
    "quick_think_llm": "MiniMax-M2.7-highspeed",
    "output_language": "Chinese",
}

# ── DeepSeek Example ───────────────────────────────────────────────────────
# config = {
#     "llm_provider": "deepseek",
#     "deep_think_llm": "deepseek-chat",
#     "quick_think_llm": "deepseek-chat",
#     "output_language": "Chinese",
# }

# ── Anthropic + Kimi Example ───────────────────────────────────────────────
# config = {
#     "llm_provider": "anthropic",
#     "deep_think_llm": "claude-sonnet-4-6",
#     "quick_think_llm": "claude-sonnet-4-6",
#     "backend_url": "https://api.kimi.com/coding/",
#     "output_language": "Chinese",
# }

ta = TradingAgentsGraph(debug=True, config=config)
final_state, decision = ta.propagate("688017", "2026-05-12")
print(decision)
```

### 4. CLI Mode

```bash
tradingagents                 # Interactive CLI
tradingagents analyze         # Same as above (default command)
tradingagents performance     # Decision performance report (see below)
tradingagents --help          # Show all options
```

### 5. Decision performance report (added in v0.5.2)

To find out **how well the pipeline's past calls actually held up**:

```bash
tradingagents performance            # Human-readable report
tradingagents performance --json     # Machine-readable JSON
```

The data comes from the memory log: every analysis records a decision, and the next analysis of the same ticker resolves it by fetching real prices and filling in the return and the alpha (against CSI 300). **The report itself makes zero LLM calls** — it only reads results already on disk.

The headline metric is **`direction_accuracy`** — **the only one that measures whether the calls were right**: a bullish rating must outperform and a bearish one must underperform; Hold takes no position and is excluded. It also reports `up_rate` (how often the instrument rose) and `outperform_rate` (how often it beat CSI 300); **those two describe the instrument, not the decision** — a Sell followed by a decline is a *correct* call, yet it does not count toward `up_rate`.

Plus breakdowns by rating and by ticker, and a **rating-discrimination check**: across the five tiers from Buy to Sell, does average alpha actually decrease monotonically? A non-monotonic result means the ratings carry no real discriminating power.

Important caveats:

- **This is not a backtest, and not strategy performance.** Each record is "how one judgement made on one day looked after a fixed holding window": the windows overlap, there is no position sizing, no transaction or impact costs, and the sample may be selection-biased.
- **A-share beta is strong** — rising with the index is not the same as being right, so direction accuracy is judged on alpha; raw return would overstate skill.
- **Significance is counted per metric**: direction accuracy only uses directional ratings, so when the resolved total is large enough but the directional count is under 20, the report flags that metric separately.
- **Below 20 resolved records the report says so itself** ("these ratios are mostly noise"). Do not draw conclusions from a handful of entries.
- Records whose return cannot be parsed are **skipped, not counted as 0%** — counting them would quietly drag every statistic toward neutral.

---
## Web UI

Built-in Streamlit visualization interface allows selecting LLM providers and models in the sidebar. Enter a stock code to perform one-click analysis, ideal for users who prefer not to write code.

### Startup

```bash
# Option 1: Start via command line (recommended)
tradingagents-web

# Option 2: Run directly
streamlit run web/app.py
```

Open your browser and navigate to `http://localhost:8501`.

### Features

- **Model Selection**: Sidebar supports switching between 10 LLM providers (MiniMax/DeepSeek/Qwen/GLM/OpenAI/Anthropic/Google/xAI/OpenRouter/Ollama), plus **"OpenAI Compatible (custom base_url)"** for connecting to any OpenAI-compatible gateway (9Router / AI Router / self-hosted proxy)
- **One-Click Analysis**: Enter a 6-digit A-share stock code + analysis date + "Data Start Date" (defaults to the first day of the current month, allows customizing the technical analysis lookback period, supports monthly/custom period analysis), then click "Start Analysis"
- **Real-Time Progress**: 12-stage pipeline displayed in real-time (7 Analysts → Quality Gate → Debate → Risk Control → Decision), with expandable reports for all completed stages
- **Complete Report**: Signal cards (Buy/Hold/Sell), 7 analyst reports, bull-bear debate, risk control assessment
- **Report Export**: One-click download of **Markdown** (zero dependencies, always available) or **PDF** full analysis reports (PDF automatically adapts to Chinese fonts on Windows/macOS/Linux)
- **History**: Automatically saves and displays all historical analyses

### Screenshot

<p align="center">
  <img src="assets/web-ui-welcome.png" width="80%" alt="Web UI Welcome Page"/>
</p>

---
## Configuration

All configuration is passed in through the `config` dictionary. Complete options:

| Parameter | Default Value | Description |
|------|--------|------|
| `llm_provider` | `"minimax"` | LLM provider: `minimax` / `deepseek` / `qwen` / `glm` / `openai` / `anthropic` / `google` / `xai` / `ollama` |
| `deep_think_llm` | `"MiniMax-M2.7"` | Model used by the Research Manager + Portfolio Manager |
| `quick_think_llm` | `"MiniMax-M2.7-highspeed"` | Model used by all Analysts / Researchers / Traders |
| `backend_url` | `None` | Custom API endpoint / third-party relay gateway. Can be filled in via the Web UI sidebar or the `.env` file's `BACKEND_URL`; useful for accessing Claude / OpenAI from within China via a proxy |
| `role_llms` | `{}` | **Optional**: give individual roles a different model (e.g. bull vs bear from different vendors). Empty = every role uses the quick/deep pair as before. See "Per-role models" below. #39 |
| `max_tokens` | `None` | Max output tokens per reply. `None` = the provider's own default. **If a report stops mid-sentence, raise this first** (it is the output cap, not the context window); also settable via `TRADINGAGENTS_MAX_TOKENS`. #91 |
| `output_language` | `"Chinese"` | Language for report output (internal debates are always in English) |
| `market_lookback_days` | `None` | Lookback period in days for technical analysis (analysis range = start date → analysis date). Automatically calculated from the "data start date" in Web/CLI; `None` = model chooses (~30 days). #16 |
| `max_debate_rounds` | `1` | Number of Bull vs Bear debate rounds |
| `max_risk_discuss_rounds` | `1` | Number of risk three-way debate rounds |
| `data_vendors` | All `"a_stock"` | Data vendor routing |
| `checkpoint_enabled` | `False` | Enable SQLite checkpoint/resume |
| `memory_log_max_entries` | `None` | Maximum number of entries in trading memory |

### Per-role models (optional, added in v0.5.0)

By default every role shares the `quick_think_llm` / `deep_think_llm` pair — **most people run a single vendor and never need this**.

If you do have several models available, you can assign one to a specific role. The motivating case is **giving the bull and bear researchers models from different vendors**: one model playing both sides tends to agree with itself, and real rebuttals only show up once the underlying models differ.

```python
config = {
    "llm_provider": "deepseek",          # roles you do not list still use this
    "deep_think_llm": "deepseek-chat",
    "quick_think_llm": "deepseek-chat",
    "role_llms": {
        "bull": {"provider": "qwen", "model": "qwen-plus"},
        "bear": {"provider": "glm",  "model": "glm-4.6"},
        # omit provider to keep llm_provider and only swap the model:
        "portfolio_manager": {"model": "deepseek-reasoner"},
    },
}
```

Valid role names (anything you omit keeps the quick/deep default):

| Group | Roles |
|-------|-------|
| 7 analysts | `market` `social` `news` `fundamentals` `policy` `hot_money` `lockup` |
| Debate & decision | `bull` `bear` `research_manager` `trader` |
| Risk trio | `risk_aggressive` `risk_neutral` `risk_conservative` |
| Other | `quality_gate` `portfolio_manager` |

Notes:

- **A misspelled role name raises immediately** rather than being ignored — otherwise you would believe the config took effect when it did not.
- **Identical provider + model share one instance**, so listing seven roles does not open seven connections.
- Each provider uses **its own** API key variable (`DEEPSEEK_API_KEY` / `DASHSCOPE_API_KEY` / `ZHIPU_API_KEY` …); a missing one is reported by name.
- `backend_url` is **not** carried across vendors (it belongs to the main provider); set `backend_url` inside the role entry if you need one.
- With the `claude_agent_sdk` subscription override on, roles listed in `role_llms` **bypass the subscription and bill per token**; the affected roles are named in a startup warning.

---

## Common Troubleshooting

**Q: Using DeepSeek/Tongyi/Zhipu but getting `OpenAIError: The api_key client option must be set ... OPENAI_API_KEY`?**
Each provider uses **its own environment variable**, not `OPENAI_API_KEY`: DeepSeek=`DEEPSEEK_API_KEY`, Tongyi=`DASHSCOPE_API_KEY`, Zhipu=`ZHIPU_API_KEY`, MiniMax=`MINIMAX_API_KEY`, xAI=`XAI_API_KEY`, OpenRouter=`OPENROUTER_API_KEY`, OpenAI-Compatible (Custom)=`OPENAI_COMPATIBLE_API_KEY`. Set the corresponding variable in the `.env` file at the project root and **restart** the program. (Starting from v0.2.12, if the key is missing, it will directly prompt which variable name to use.)

**Q: Want to connect to an OpenAI-compatible third-party gateway/relay (9Router, AI Router, self-built proxy) with a custom base_url + model?**
Use the **「OpenAI-Compatible (Custom base_url)」** option (added in v0.2.20). In the Web sidebar, select it under "LLM Provider" → Manually enter the model name supported by your gateway under "Fast/Deep Think Model ID" → Enter your gateway address under "API Base URL" (e.g., `https://your-relay.example/v1`) → Set `OPENAI_COMPATIBLE_API_KEY=your_key` in `.env` (it also accepts `OPENAI_API_KEY`). For CLI, after selecting `OpenAI-Compatible`, it will prompt for the Base URL. It uses standard Chat Completions (not OpenAI Responses API, for best compatibility), and the model name can be freely entered without being restricted by the built-in list. The equivalent configuration is: `llm_provider="openai_compatible"` + `backend_url="<your_gateway>"` + `deep_think_llm/quick_think_llm="<your_model>"`.

**Q: I have Python 3.12/3.14 installed, but `pip install -e .` says `requires a different Python: 3.9.6 not in '>=3.10'`?**
The **3.9.6 in that message is the interpreter your current `pip` is bound to** — the newer version you installed is not the one being used (on macOS, the bundled `pip3` often points at the system 3.9). Check which interpreter is running:

```bash
pip3 -V                    # the path in parentheses is its Python
python3.12 -m pip -V       # same check for the version you want
```

Using `python -m pip` avoids the mix-up; a virtualenv is recommended:

```bash
python3.12 -m venv .venv && source .venv/bin/activate
python -m pip install -e .
```

On Windows use `py -3.12 -m venv .venv` + `.venv\Scripts\activate`. (#92)

**Q: The report stops halfway through, but the context window was nowhere near full?**
You are hitting the **output** cap, not the context cap — how many tokens a model may emit in one reply is a separate limit. Since v0.4.1 this truncation is reported in the logs (`因为达到输出上限被截断` / truncated at the output limit) instead of silently handing you half a report. Raise it with `max_tokens` in the config (e.g. `"max_tokens": 16000`) or the `TRADINGAGENTS_MAX_TOKENS` environment variable.

Also note: when you run a **third-party model name (Kimi and friends) through the `anthropic` provider**, langchain does not recognise the model and applies a very small default output cap, which shows up as uniformly short reports. Since v0.4.1 those models default to 8192; set `max_tokens` explicitly if you need more. #91

**Q: Kimi fails with `401 invalid x-api-key`?**
The request reached **Anthropic itself**, not Kimi — you supplied the key but not the endpoint. Both are required:

```bash
ANTHROPIC_API_KEY=your-kimi-token
ANTHROPIC_BASE_URL=https://api.kimi.com/coding/   # or set backend_url in the config
```

Note that **`ANTHROPIC_AUTH_TOKEN` has no effect here** — that is the Claude Code CLI convention. This project runs on langchain, which only reads `ANTHROPIC_API_KEY`. Since v0.4.1, using a non-Claude model name without an endpoint fails **at startup** with an explanation instead of an opaque 401 from Anthropic. #89

**Q: Exporting PDF gives `UnicodeEncodeError: 'latin-1' codec can't encode`?**
Your environment has **an old version of `fpdf` (pyfpdf)** installed, which conflicts with the `fpdf2` used by this project, as both are imported under the name `fpdf`. Execute: `pip uninstall -y fpdf && pip install "fpdf2>=2.8.6"`. If this doesn't work, you can use the "Download Markdown" export option instead (zero dependencies, always available).

**Q: In Docker, exporting PDF gives "Chinese font not found"?**
Starting from v0.2.12, the Dockerfile includes `fonts-noto-cjk` built-in. Simply rebuild with `docker build`. For older images, you can temporarily run `apt install fonts-noto-cjk`, or switch to Markdown export.

**Q: Docker startup fails with `[Errno 13] Permission denied: /home/appuser/.tradingagents/cache`?**
Older images did not pre-create the data directory. When the `docker-compose` named volume is mounted, Docker creates it as `root`-owned, but the process inside the container runs as `appuser` and cannot write to it. Starting from v0.2.14, the Dockerfile pre-creates `/home/appuser/.tradingagents` (cache/logs/memory) and sets ownership to `appuser`, so named volumes inherit this ownership. **To upgrade**: after `git pull`, rebuild the image with `docker compose build --no-cache`. If you want to keep the old data volume, first run `docker run --rm -v tradingagents_data:/d alpine chown -R 1000:1000 /d` to fix the ownership; otherwise, simply remove the volume with `docker volume rm tradingagents_data` and rebuild.

**Q: Some analyst reports (Sentiment/News/Fundamentals/Policy/Hot Money/Lock-up Expiry) are blank and not displayed?**
These reports are generated after the corresponding Analyst calls data tools. **Empty reports are automatically skipped and not displayed.** The data sources themselves are healthy (Tencent/mootdx/Tonghuashun/Dongcai have been tested and return data). Reports are usually empty because **the selected model has weak tool-call capabilities** (e.g., some lightweight deepseek/minimax models are unstable when calling tools). It is recommended to switch to a model with more stable tool-calls (deepseek-chat / Tongyi / GLM-4 / Claude / GPT, etc.), or retry.

**Q: Why is there no `[google]` extra any more? How do I install Gemini?**
**The `[google]` extra was removed in v0.3.1** ([#87](https://github.com/simonlin1212/TradingAgents-astock/issues/87)). `langchain-google-genai>=4.0.0` requires `google-genai>=1.53.0`, and **every** google-genai release in that range requires `httpx>=0.28.1`, while mootdx (the core A-share data source) pins `httpx>=0.25,<0.26`. **No version combination satisfies both — the conflict is structural, not a bad pin.**

The real damage: **uv builds a universal lock covering all extras**, so merely declaring the extra made `uv sync` fail for **everyone**, including users who never wanted Gemini. Leaving it empty would be worse (`pip install .[google]` would silently install nothing). So it was removed, and `google_client.py` now raises an ImportError containing the exact install commands.

To use Gemini, install it explicitly (**mootdx speaks the TDX protocol over TCP and never imports httpx at runtime**, so raising httpx is safe in practice):

```bash
pip install --no-deps "langchain-google-genai>=4.0.0"
pip install "google-genai>=1.53.0" "httpx>=0.28.1"
```

Or keep Gemini in a separate venv. Simplest of all: use DeepSeek / MiniMax / Qwen / any OpenAI-compatible gateway, which avoids the conflict entirely.

One clarification: **litellm / mcp are not dependencies of this project** — if the error mentions them, they come from other packages in your environment.

**Q: How to batch-run multiple tickers and get the same complete reports as the CLI without entering the CLI interactive mode?**
See `examples/run_cases.py`: It reuses the CLI's `save_report_to_disk()` function, outputting for each ticker the same `complete_report.md` (with Analyst / Research / Trading / Risk / Portfolio five sections) and a fully-fledged `summary.json`. Usage: `uv run python examples/run_cases.py` (run all) or `uv run python examples/run_cases.py 688017` (single ticker); modify `build_config()` to switch providers/models.
## Project Structure

```
TradingAgents-Astock/
├── tradingagents/
│   ├── agents/
│   │   ├── analysts/          # 7 analysts
│   │   │   ├── market_analyst.py
│   │   │   ├── social_media_analyst.py
│   │   │   ├── news_analyst.py
│   │   │   ├── fundamentals_analyst.py
│   │   │   ├── policy_analyst.py        # A-share specialized
│   │   │   ├── hot_money_tracker.py     # A-share specialized
│   │   │   └── lockup_watcher.py        # A-share specialized
│   │   ├── researchers/       # Bull / Bear researchers
│   │   ├── risk_mgmt/         # Aggressive / Conservative / Neutral debaters
│   │   ├── managers/          # Research Manager + Portfolio Manager
│   │   ├── trader/            # Trader (A-share trading constraints)
│   │   └── utils/             # State definitions, utility functions
│   ├── dataflows/
│   │   ├── a_stock.py         # A-share data vendor (direct HTTP API, zero third-party libraries)
│   │   ├── interface.py       # Data interface abstraction layer
│   │   └── ...
│   └── graph/
│       ├── trading_graph.py   # Main entry point: TradingAgentsGraph
│       ├── setup.py           # LangGraph topology definition
│       ├── propagation.py     # State initialization and propagation
│       ├── reflection.py      # Trading reflection (CSI 300 benchmark)
│       └── conditional_logic.py
├── web/
│   ├── app.py                 # Streamlit main entry
│   ├── runner.py              # Backend thread running analysis
│   ├── progress.py            # Thread-safe progress tracking
│   ├── history.py             # History record scanning
│   ├── pdf_export.py          # PDF report generation
│   ├── launch.py              # CLI launcher
│   └── components/            # UI components
│       ├── sidebar.py         # Sidebar (inputs + history)
│       ├── progress_panel.py  # Real-time progress panel
│       └── report_viewer.py   # Report display
├── test_astock.py             # E2E integration tests
├── CHANGES_FROM_UPSTREAM.md   # Complete change log versus upstream
├── NOTICE                     # Apache 2.0 attribution notice
├── LICENSE                    # Apache 2.0 license
└── pyproject.toml             # Package definition and dependencies
```
## Acknowledgments

This project is based on the [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) open-source project, adapted for China's A-share market. We thank the original authors for their outstanding work and the Apache 2.0 open-source spirit.

**Original Paper**: [TradingAgents: Multi-Agents LLM Financial Trading Framework](https://arxiv.org/abs/2412.20138)

---
## Project Positioning

**This is an engineering implementation of a framework, not an investment product.**

- **What it is**: An A-share engineering implementation of the multi-agent architecture from the [TradingAgents paper](https://arxiv.org/abs/2412.20138) (TauricResearch), designed for research and teaching—specifically for studying multi-agent debate behavior on financial texts, how to integrate A-share data sources, and how to realize structured outputs.
- **What it is not**: It is not an investment advisor, not a stock recommendation service, and does not provide any investment services. This repository does not publish analysis reports, ratings, or buy/sell recommendations for specific securities. The `examples/` directory only contains scripts you can run yourself; there are no pre-generated conclusions about individual stocks.
- **Models and data are yours**: You configure your own LLM API keys, run it on your own machine, and the output content belongs to you, is judged by you, and is your responsibility. The project itself does not host services, perform analysis on your behalf, or access your run results.
- **No executable price levels are generated**: The framework **does not** output positions like entry prices, stop-loss levels, position sizes, or target prices—this isn't a default-off feature; it's simply not present in the code. The Trader and Portfolio Manager only provide direction, ratings, and rationale. Users requiring this capability can fork the code and add it themselves (allowed under Apache-2.0), while assuming all related responsibilities and verifying their own jurisdiction's qualification requirements.

> **⚠️ Disclaimer**
>
> - All content generated by this system is automatically produced by AI and may contain errors or biases.
> - This project does not constitute any investment advice. Please consult a professional institution holding qualifications issued by the China Securities Regulatory Commission for investment decisions.
> - The author assumes no responsibility for any investment losses incurred from using this tool.
> - Stock markets are risky. Invest cautiously.

---

## Support

If this tool saved you time, a coffee is appreciated ☕

<p align="center">
  <a href="https://buymeacoffee.com/simonlin1212"><img src="./assets/bmc-qr.png" width="180" alt="Buy Me a Coffee"></a>
</p>

> Want a feature that isn't here? Open an [Issue](https://github.com/simonlin1212/tradingagents-astock/issues); sponsors' issues go first.

---

## License

[Apache License 2.0](./LICENSE)

This project is a fork of TauricResearch/TradingAgents and inherits the Apache 2.0 license. See [NOTICE](./NOTICE).

**Author:** Simon Lin · X [@linsizhen](https://x.com/linsizhen) · Email: [simonlin0423@gmail.com](mailto:simonlin0423@gmail.com)
