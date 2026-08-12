<p align="center"><b>简体中文</b> | <a href="README_en.md">English</a></p>

<h1 align="center">TradingAgents-Astock</h1>

<p align="center">
  基于 <a href="https://github.com/TauricResearch/TradingAgents">TauricResearch/TradingAgents</a>（65K ⭐）的 A 股深度特化 fork<br>
  全 Apache 2.0 开源 · pip install 即跑 · 零外部服务依赖
</p>

<p align="center">
  <b>⚠️ 本项目是 <a href="https://arxiv.org/abs/2412.20138">TradingAgents 论文</a>框架的工程实现与研究复现，面向研究与教学。<br>
  不构成任何投资建议，也不提供任何投资服务。</b>
</p>

<p align="center">
  <a href="https://github.com/simonlin1212/tradingagents-astock/stargazers"><img alt="Stars" src="https://img.shields.io/github/stars/simonlin1212/tradingagents-astock?style=social"/></a>
  <a href="https://github.com/simonlin1212/tradingagents-astock/network/members"><img alt="Forks" src="https://img.shields.io/github/forks/simonlin1212/tradingagents-astock?style=social"/></a>
  <a href="https://arxiv.org/abs/2412.20138"><img alt="论文" src="https://img.shields.io/badge/论文-arXiv_2412.20138-B31B1B?logo=arxiv"/></a>
  <a href="./LICENSE"><img alt="License" src="https://img.shields.io/badge/License-Apache_2.0-blue"/></a>
  <a href="./CHANGES_FROM_UPSTREAM.md"><img alt="改动记录" src="https://img.shields.io/badge/改动记录-CHANGES-orange"/></a>
</p>

<p align="center">
  <a href="#为什么做这个-fork">为什么做这个 Fork</a> ·
  <a href="#与上游对比">与上游对比</a> ·
  <a href="#架构概览">架构概览</a> ·
  <a href="#7-个-analyst-角色">Analyst 角色</a> ·
  <a href="#数据源">数据源</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="#web-ui">Web UI</a> ·
  <a href="#常见问题排错">排错</a>
</p>

---

## 为什么做这个 Fork

原版 TradingAgents 是一个出色的多 Agent 投研框架，但它针对美股设计：数据走 Yahoo Finance / Alpha Vantage，分析师不懂 A 股制度，辩论和决策完全面向美股市场。

**本 Fork 的目标**：把 TradingAgents 的多 Agent 辩论架构真正落地到 A 股，不是简单翻译，而是从数据层、Agent 角色、交易规则三个维度做深度特化。

### 核心改造

| 维度 | 原版 | 本 Fork |
|------|------|---------|
| **数据源** | Yahoo Finance / Alpha Vantage | mootdx + 东财 + 新浪 + 同花顺（全免费直连） |
| **Analyst 角色** | 4 个（市场/情绪/新闻/基本面） | **7 个**（+政策分析师/游资追踪/解禁监控） |
| **交易规则** | 美股（T+0、无涨跌停） | A 股（T+1、涨跌停、最小手数、交易时段） |
| **输出语言** | 英文 | 中文报告（内部辩论保持英文以保证推理质量） |
| **Alpha 基准** | SPY | 沪深 300（CSI 300） |

---

## 与上游对比

| 特性 | 原版 TradingAgents | **本 Fork** |
|------|-------------------|-------------|
| 许可证 | Apache 2.0 | **全 Apache 2.0** |
| 部署依赖 | pip install | **开箱即用** |
| A 股数据 | ❌ | **mootdx + 东财 + 新浪 + 同花顺（直连 HTTP）** |
| A 股特化角色 | ❌ | **政策/游资/解禁 3 个深度角色** |
| A 股交易约束 | ❌ | **T+1/涨跌停/手数/ST 全覆盖** |

---

## 架构概览

```
┌─────────────────────────────────────────────────────────┐
│                    7 Analyst 研报生成                      │
│  Market → Social → News → Fundamentals                   │
│  → Policy → Hot Money → Lockup                           │
│         （每个 Analyst 带工具循环）                          │
├─────────────────────────────────────────────────────────┤
│               Bull vs Bear 投研辩论                       │
│         Bull Researcher ←→ Bear Researcher               │
│               （最多 N 轮辩论）                             │
├─────────────────────────────────────────────────────────┤
│              Research Manager 综合研判                     │
│         （深度思考 LLM，输出投资计划）                       │
├─────────────────────────────────────────────────────────┤
│                  Trader 交易方案                          │
│         （A 股约束：T+1/涨跌停/手数）                       │
├─────────────────────────────────────────────────────────┤
│        Aggressive ←→ Conservative ←→ Neutral             │
│               三方风险辩论                                 │
├─────────────────────────────────────────────────────────┤
│            Portfolio Manager 最终决策                      │
│     （深度思考 LLM，输出评级 + 理由）                       │
└─────────────────────────────────────────────────────────┘
```

**双 LLM 设计**：
- `quick_think_llm`：所有 Analyst、Researcher、Trader、Risk Debater
- `deep_think_llm`：Research Manager 和 Portfolio Manager（需要综合全局信息做决策）

---

## 7 个 Analyst 角色

### 原版 4 角色（A 股适配）

| 角色 | 职责 | 数据工具 |
|------|------|---------|
| 🏪 市场分析师 | K 线形态、技术指标、量价分析 | `get_stock_data`, `get_indicators` |
| 💬 舆情分析师 | 社交媒体情绪、散户讨论热度 | `get_news` |
| 📰 新闻分析师 | 行业新闻、公告、宏观事件 | `get_news`, `get_global_news`, `get_insider_transactions` |
| 📊 基本面分析师 | 财报三表、盈利能力、估值 | `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement` |

### A 股特化 3 角色（新增）

| 角色 | 职责 | 数据工具 | 为什么需要 |
|------|------|---------|-----------|
| 🏛️ 政策分析师 | 监管政策、产业政策、窗口指导 | `get_news`, `get_global_news` | A 股是政策市，政策变化直接影响板块轮动 |
| 🔥 游资追踪师 | 龙虎榜、大单流向、主力资金动态 | `get_stock_data`, `get_news`, `get_insider_transactions` | 游资是 A 股短线定价的核心力量 |
| 🔓 解禁监控师 | 限售股解禁、大股东减持、股权质押 | `get_insider_transactions`, `get_news`, `get_fundamentals` | 解禁是 A 股特有的重大供给冲击因素 |

所有 7 个 Analyst 的报告会流入后续的 Bull/Bear 辩论和三方风险辩论，确保 A 股特色因素贯穿整条决策链。

---

## 数据源

全部免费，无需 API Key，无积分墙：

| 来源 | 协议 | 提供内容 |
|------|------|---------|
| **mootdx** | TCP 7709 | OHLCV K 线、财务快照、F10 文本 |
| **腾讯财经** | HTTP (`qt.gtimg.cn`) | PE / PB / 市值 / 换手率（实时） |
| **东方财富** | HTTP (datacenter / push2) | 龙虎榜、限售解禁、板块行情、个股信息 |
| **新浪财经** | HTTP | K 线历史、财报三表 |
| **同花顺** | HTTP (10jqka) | EPS 一致预期 |
| **财联社** | HTTP (cls.cn) | 全球财经快讯 |
| **百度股市通** | HTTP (finance.pae.baidu) | 概念板块分类、资金流向 |

> 完全不依赖 Tushare（积分墙）、Alpha Vantage（海外 API）、Yahoo Finance（不支持 A 股）。

---

> **数据源优先级 & 东财防封（v0.2.11）**：行情 / K线 / 市值 / 财务能从 mootdx（通达信 TCP，不封 IP）或腾讯拿到的，一律走它们；东财只用于它独有的数据（龙虎榜 / 解禁 / 资金流 / 板块 / 个股新闻等）。所有东财请求统一走内置节流入口 `_em_get()`：串行限流（默认间隔 ≥1s + 0.1~0.5s 随机抖动）+ 复用 Keep-Alive 会话，多 Agent 跑批量分析不再触发临时封 IP（东财风控实测：每秒 >5 / 并发 ≥10 / 1 分钟 ≥200 触发封禁）。批量场景可设环境变量 `EM_MIN_INTERVAL=1.5~2` 进一步降速。**仅东财限流，mootdx / 腾讯 / 新浪 / 同花顺 / 财联社 / 百度 不受影响。**

## 快速开始

### 1. 环境准备

```bash
# Python >= 3.10
git clone https://github.com/simonlin1212/tradingagents-astock.git
cd tradingagents-astock
pip install -e .

# 如需使用 Google Gemini 模型（无 [google] extra，需显式装，见下方 FAQ）：
pip install --no-deps "langchain-google-genai>=4.0.0"
pip install "google-genai>=1.53.0" "httpx>=0.28.1"

# 如需让节点走你个人 Claude Pro/Max 订阅额度而非 API 计费（可选）：
pip install -e ".[agentsdk]"
```

> **装完即可用，无需 Docker。** 安装后直接跑 `streamlit run web/app.py`（Web UI）或 `tradingagents`（CLI）即可，详见下方「Web UI」「CLI 方式」两节。Docker 仅是可选的部署方式，本地开发不需要。

### 2. 配置 LLM

> **默认走 API Key 计费**。每次分析需 30-50 次 LLM 调用。
>
> **例外（v0.4.0 新增）**：装 `[agentsdk]` 后可让部分或全部节点经 Claude Agent SDK 走你**个人 Claude Pro/Max 订阅额度**，不产生 API 账单。见下方「用个人 Claude 订阅额度」。

在项目根目录创建 `.env` 文件，按你选择的供应商配置：

```bash
# ── 方案 A：MiniMax（推荐，国内直连，性价比高）──────────
MINIMAX_API_KEY=sk-xxx
# 申请地址：https://platform.minimaxi.com/

# ── 方案 B：DeepSeek ─────────────────────────────────
DEEPSEEK_API_KEY=sk-xxx
# 申请地址：https://platform.deepseek.com/

# ── 方案 C：智谱 GLM ─────────────────────────────────
ZHIPU_API_KEY=xxx
# 申请地址：https://open.bigmodel.cn/

# ── 方案 D：通义千问 Qwen ────────────────────────────
DASHSCOPE_API_KEY=sk-xxx
# 申请地址：https://dashscope.console.aliyun.com/

# ── 方案 E：OpenAI ───────────────────────────────────
OPENAI_API_KEY=sk-xxx

# ── 方案 F：Anthropic ────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-xxx

# ── 方案 G：Kimi（Anthropic 兼容 API）────────────────
ANTHROPIC_API_KEY=your-kimi-token
ANTHROPIC_BASE_URL=https://api.kimi.com/coding/
# ⚠️ 两个都要设。只给 key 不给端点，请求会发到 Anthropic 官方并报
#    「401 invalid x-api-key」。端点也可以写在 config 的 backend_url 里（见下）。
# ⚠️ 别用 ANTHROPIC_AUTH_TOKEN——那是 Claude Code CLI 的写法，本项目走 langchain，
#    只认 ANTHROPIC_API_KEY。

# ── 方案 H：任意 OpenAI 兼容网关（9Router / AI Router / 自建代理）──
OPENAI_COMPATIBLE_API_KEY=sk-xxx     # 也接受 OPENAI_API_KEY
BACKEND_URL=https://your-relay.example/v1   # 你的网关地址（也可在 Web 侧栏「API Base URL」填）
```

### 3. 运行分析

根据你选择的供应商修改 config：

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph

# ── MiniMax 示例（推荐）─────────────────────────────
config = {
    "llm_provider": "minimax",
    "deep_think_llm": "MiniMax-M2.7",
    "quick_think_llm": "MiniMax-M2.7-highspeed",
    "output_language": "Chinese",
}

# ── DeepSeek 示例 ───────────────────────────────────
# config = {
#     "llm_provider": "deepseek",
#     "deep_think_llm": "deepseek-chat",
#     "quick_think_llm": "deepseek-chat",
#     "output_language": "Chinese",
# }

# ── Anthropic + Kimi 示例 ───────────────────────────
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

### 4. CLI 方式

```bash
tradingagents                 # 交互式 CLI
tradingagents analyze         # 同上（默认命令）
tradingagents performance     # 决策绩效统计（见下）
tradingagents --help          # 查看所有选项
```

### 5. 决策绩效统计（v0.5.2 新增）

想知道**这套流程过往的判断准不准**，跑：

```bash
tradingagents performance            # 人读的报告
tradingagents performance --json     # 机器读的 JSON
```

数据来自记忆日志：每次分析会落一条决策，下次分析同一只股票时自动拉真实行情回填收益与 alpha（对沪深 300）。**统计本身零 LLM 调用**，只读已经落盘的结果。

输出的核心指标是 **`direction_accuracy`（方向正确率）**——**只有它衡量判断准不准**：看多要跑赢、看空要跑输才算对，Hold 不表态不计入。另外给出 `up_rate`（标的上涨占比）与 `outperform_rate`（跑赢沪深300占比），这两个只描述标的怎么走，**与判断对错无关**：给出卖出评级后股价下跌是判断正确，但它不会计入「上涨占比」。

还有按评级、按标的分组，以及一项**评级区分度检验**——五档评级从 Buy 到 Sell，平均 alpha 是否真的单调递减。评级不单调，说明这套流程的评级没有实际区分能力。

几点务必注意：

- **这不是回测，也不是策略业绩。** 每条记录是「某天做出的判断在固定持有期后的表现」：持有窗口互相重叠、没有仓位管理、未计交易成本与冲击成本，样本还可能有选择偏差。
- **A 股 beta 很强**，跟着大盘涨不代表判断对，所以方向正确率用 alpha 口径判定，看绝对收益容易高估判断力。
- **样本量分开算**：方向正确率只统计有方向的评级，已结算总数够、但有方向的不足 20 条时，报告会单独提示这个指标仍是噪音。
- **样本少于 20 条时报告会自己标注「这些比率基本是噪音」**，不要拿三五条记录下结论。
- 收益解析不出来的记录会被**跳过**而不是当成 0%——后者会把统计悄悄拉向中性。

---

## Web UI

内置 Streamlit 可视化界面，支持在侧边栏选择 LLM 供应商和模型，输入股票代码即可一键分析，适合不写代码的用户。

### 启动

```bash
# 方式一：命令行启动（推荐）
tradingagents-web

# 方式二：直接运行
streamlit run web/app.py
```

打开浏览器访问 `http://localhost:8501`。

### 功能

- **模型自选**：侧边栏支持 10 个 LLM 供应商切换（MiniMax/DeepSeek/Qwen/GLM/OpenAI/Anthropic/Google/xAI/OpenRouter/Ollama），外加 **「OpenAI 兼容（自定义 base_url）」** 一档可接任意 OpenAI 兼容网关（9Router / AI Router / 自建代理）
- **一键分析**：输入 6 位 A 股代码 + 分析日期 +「数据起始日期」（默认本月第一天，可自定义技术分析回溯区间，支持按月/自定义时段分析），点击「开始分析」
- **实时进度**：12 阶段 pipeline 实时显示（7 分析师 → 质量门控 → 辩论 → 风控 → 决策），所有已完成阶段的报告均可展开查看
- **完整报告**：信号卡片（Buy/Hold/Sell）、7 份分析师报告、多空辩论、风控评估
- **报告导出**：一键下载 **Markdown**（零依赖，永远可用）或 **PDF** 完整分析报告（PDF 自动适配 Windows/macOS/Linux 中文字体）
- **历史记录**：自动保存并展示所有历史分析

### 截图

<p align="center">
  <img src="assets/web-ui-welcome.png" width="80%" alt="Web UI 欢迎页"/>
</p>

---

## 配置说明

所有配置通过 `config` 字典传入，完整选项：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `llm_provider` | `"minimax"` | LLM 提供商：`minimax` / `deepseek` / `qwen` / `glm` / `openai` / `anthropic` / `google` / `xai` / `ollama` |
| `deep_think_llm` | `"MiniMax-M2.7"` | Research Manager + Portfolio Manager 用的模型 |
| `quick_think_llm` | `"MiniMax-M2.7-highspeed"` | 所有 Analyst / Researcher / Trader 用的模型 |
| `backend_url` | `None` | 自定义 API 端点 / 第三方中转网关。可在 Web UI 侧边栏填写，或用 `.env` 的 `BACKEND_URL`；方便国内通过代理访问 Claude / OpenAI |
| `role_llms` | `{}` | **可选**：给单个角色指定另一家模型（如多空辩手用不同厂商），留空 = 全部沿用 quick/deep 两档，行为不变。见下方「分角色模型」 #39 |
| `max_tokens` | `None` | 单次回复的最大输出 token 数。`None` = 用 provider 默认值。**报告写到一半就断，先调这里**（不是上下文超长）；也可用环境变量 `TRADINGAGENTS_MAX_TOKENS`。#91 |
| `output_language` | `"Chinese"` | 报告输出语言（内部辩论始终英文） |
| `market_lookback_days` | `None` | 技术分析回溯天数（分析区间 = 起始日期 → 分析日期）。Web/CLI 由「数据起始日期」自动算出；`None` = 模型自选（约 30 天）。#16 |
| `max_debate_rounds` | `1` | Bull vs Bear 辩论轮数 |
| `max_risk_discuss_rounds` | `1` | 风险三方辩论轮数 |
| `data_vendors` | 全部 `"a_stock"` | 数据供应商路由 |
| `checkpoint_enabled` | `False` | 启用 SQLite 断点续跑 |
| `memory_log_max_entries` | `None` | 交易记忆最大条目数 |

---

### 分角色模型（可选，v0.5.0 新增）

默认所有角色共用 `quick_think_llm` / `deep_think_llm` 两档——**大多数人只有一家模型，不需要碰这一项**。

如果你手上有多家模型，可以给单个角色单独指定。最典型的用法是**让多空辩手用不同厂商的模型**：同一个模型分饰多角时倾向于互相附和，换成不同底座才会真的出现反驳。

```python
config = {
    "llm_provider": "deepseek",          # 未单独配置的角色仍走这里
    "deep_think_llm": "deepseek-chat",
    "quick_think_llm": "deepseek-chat",
    "role_llms": {
        "bull": {"provider": "qwen",    "model": "qwen-plus"},
        "bear": {"provider": "glm",     "model": "glm-4.6"},
        # provider 省略则沿用 llm_provider，只换模型：
        "portfolio_manager": {"model": "deepseek-reasoner"},
    },
}
```

合法角色名（其余角色自动沿用两档默认）：

| 分组 | 角色名 |
|------|--------|
| 7 个分析师 | `market` `social` `news` `fundamentals` `policy` `hot_money` `lockup` |
| 辩论与决策 | `bull` `bear` `research_manager` `trader` |
| 风险三方 | `risk_aggressive` `risk_neutral` `risk_conservative` |
| 其他 | `quality_gate` `portfolio_manager` |

几点说明：

- **角色名写错会直接报错**，不会静默忽略——否则你会以为配置生效了，实际没有。
- **相同的 provider + model 只建一个实例**，写 7 个角色不会开 7 条连接。
- 每家 provider 用**自己的** API Key 环境变量（`DEEPSEEK_API_KEY` / `DASHSCOPE_API_KEY` / `ZHIPU_API_KEY` …），缺哪个会指名报出来。
- 换了 provider 时**不会**把 `backend_url` 带过去（那是给主 provider 配的端点），需要的话在该角色里单独写 `backend_url`。
- 同时开着 `claude_agent_sdk` 订阅覆盖时，`role_llms` 里配的角色会**绕开订阅按 token 计费**，启动时会点名警告是哪几个。

---

## 常见问题排错

**Q: 用 DeepSeek/通义/智谱，却报 `OpenAIError: The api_key client option must be set ... OPENAI_API_KEY`？**
每个供应商用**各自的环境变量**，不是 OPENAI_API_KEY：DeepSeek=`DEEPSEEK_API_KEY`、通义=`DASHSCOPE_API_KEY`、智谱=`ZHIPU_API_KEY`、MiniMax=`MINIMAX_API_KEY`、xAI=`XAI_API_KEY`、OpenRouter=`OPENROUTER_API_KEY`、OpenAI 兼容（自定义）=`OPENAI_COMPATIBLE_API_KEY`。在项目根目录 `.env` 里设置对应变量后**重启**程序。（v0.2.12 起缺 key 会直接提示该用哪个变量名。）

**Q: 想接一个 OpenAI 兼容的第三方网关/中继（9Router、AI Router、自建代理），自定义 base_url + model？**
用 **「OpenAI 兼容（自定义 base_url）」** 这一档（v0.2.20 新增）。Web 侧栏「LLM 供应商」选它 →「快速/深度思考模型 ID」手动填你网关支持的 model 名 →「API Base URL」填你的网关地址（如 `https://your-relay.example/v1`）→ `.env` 里设 `OPENAI_COMPATIBLE_API_KEY=你的key`（也接受 `OPENAI_API_KEY`）。CLI 方式选 `OpenAI-Compatible` 后会提示输入 Base URL。它走标准 Chat Completions（非 OpenAI Responses API，兼容性最好），model 名自由填、不受内置清单限制。配置方式等价：`llm_provider="openai_compatible"` + `backend_url="<你的网关>"` + `deep_think_llm/quick_think_llm="<你的model>"`。

**Q: 明明装了 Python 3.12/3.14，`pip install -e .` 却报 `requires a different Python: 3.9.6 not in '>=3.10'`？**
报错里的 **3.9.6 就是当前这个 `pip` 绑定的解释器版本**——你装的新版本没被它用上（macOS 自带的 `pip3` 常指向系统 3.9）。先确认是哪个解释器在跑：

```bash
pip3 -V                    # 末尾括号里就是它绑定的 Python
python3.12 -m pip -V       # 换成你想用的版本再看
```

用 `python -m pip` 的写法就不会认错人，推荐配合虚拟环境：

```bash
python3.12 -m venv .venv && source .venv/bin/activate
python -m pip install -e .
```

Windows 用 `py -3.12 -m venv .venv` + `.venv\Scripts\activate`。（#92）

**Q: 报告写到一半就结束了，上下文明明没超长？**
撞的是**输出**上限，不是上下文上限——模型一次回复能吐多少 token 是另一个限制。v0.4.1 起，这种截断会在日志里明确告诉你（`因为达到输出上限被截断`），不再是默默给你半篇报告。调大即可：config 里设 `max_tokens`（例如 `"max_tokens": 16000`），或设环境变量 `TRADINGAGENTS_MAX_TOKENS=16000`。

另外，用 **Kimi 等第三方模型名走 `anthropic` 通道**时，langchain 认不出模型名，会默认一个很小的输出上限（旧版本表现为报告普遍偏短）。v0.4.1 起这种情况会自动放宽到 8192，仍不够就显式配 `max_tokens`。#91

**Q: 接 Kimi 报 `401 invalid x-api-key`？**
说明请求发到了 **Anthropic 官方**而不是 Kimi——光给 key 没给端点。两个都要给：

```bash
ANTHROPIC_API_KEY=你的kimi-token
ANTHROPIC_BASE_URL=https://api.kimi.com/coding/   # 或在 config 里写 backend_url
```

注意 **`ANTHROPIC_AUTH_TOKEN` 在本项目里不生效**（那是 Claude Code CLI 的写法），本项目走 langchain，只读 `ANTHROPIC_API_KEY`。v0.4.1 起，用非 Claude 模型名却没配端点会**在启动时**直接告诉你缺什么，而不是等 Anthropic 回一句看不懂的 401。#89

**Q: 导出 PDF 报 `UnicodeEncodeError: 'latin-1' codec can't encode`？**
你的环境里装了**旧版 `fpdf`（pyfpdf）**，它和本项目用的 `fpdf2` 都以 `fpdf` 名称导入、互相冲突。执行：`pip uninstall -y fpdf && pip install "fpdf2>=2.8.6"`。实在不行可改用「下载 Markdown」导出（零依赖，永远可用）。

**Q: Docker 里怎么跑 Web UI？容器启动报 `Invalid value: File does not exist: web/app.py`？**
用 compose 里的 `web` 服务：`docker compose up web`，然后开 http://localhost:8501 。

报这个错通常是因为命令写成了 `streamlit run web/app.py`——这条**依赖当前工作目录**，工作目录不对就找不到文件。正确的入口是 `tradingagents-web`（即 `web.launch:main`），它按 `__file__` 解析 `app.py` 的绝对路径，跟工作目录无关。本地跑同理，装完后直接 `tradingagents-web` 最稳。

**Q: Docker 里导出 PDF 报「未找到中文字体」？**
v0.2.12 起 Dockerfile 已内置 `fonts-noto-cjk`，重新 `docker build` 即可。旧镜像可临时 `apt install fonts-noto-cjk`，或改用 Markdown 导出。

**Q: Docker 启动报 `[Errno 13] Permission denied: /home/appuser/.tradingagents/cache`？**
旧版镜像里没预建数据目录，`docker-compose` 的命名卷挂上来时被 Docker 建成 `root` 属主，而容器内进程以 `appuser` 运行、写不进去。v0.2.14 起 Dockerfile 已预建 `/home/appuser/.tradingagents`（cache/logs/memory）并归属 appuser，命名卷会继承该属主。**升级方式**：`git pull` 后 `docker compose build --no-cache` 重建镜像；若想保留旧数据卷可先 `docker run --rm -v tradingagents_data:/d alpine chown -R 1000:1000 /d` 修正属主，否则 `docker volume rm tradingagents_data` 后重建即可。

**Q: 部分分析师报告（情绪/新闻/基本面/政策/游资/解禁）空白不显示？**
这些报告由对应 Analyst 调用数据工具后生成，**空报告会被自动跳过不显示**。数据源本身是健康的（腾讯/mootdx/同花顺/东财实测出数）；报告为空通常是**所选模型 tool-call 能力弱**（如部分 deepseek/minimax 轻量模型不稳定地调用工具）。建议换用 tool-call 更稳的模型（deepseek-chat / 通义 / GLM-4 / Claude / GPT 等），或重试。

**Q: 为什么没有 `[google]` extra 了？装 Gemini 报 httpx 冲突怎么办？**
**v0.3.1 起移除了 `[google]` extra**（[#87](https://github.com/simonlin1212/TradingAgents-astock/issues/87)）。原因：`langchain-google-genai>=4.0.0` 要求 `google-genai>=1.53.0`，而该区间内**每一个** google-genai 版本都要求 `httpx>=0.28.1`；mootdx（核心 A 股数据源）钉死 `httpx>=0.25,<0.26`。**没有任何版本组合能同时满足，冲突是结构性的。**

真正的问题是：**uv 构建的是覆盖所有 extra 的 universal lock**，所以只要这个 extra 存在，`uv sync` 就对**所有人**失败——包括从不用 Gemini 的用户。把 extra 留空更糟（`pip install .[google]` 会静默什么都不装，用户以为装好了）。所以直接移除，并在 `google_client.py` 导入失败时给出可直接执行的安装命令。

需要 Gemini 时显式安装（**mootdx 取行情走 TCP 协议、运行时根本不 import httpx**，所以抬高 httpx 实测不影响取数）：

```bash
pip install --no-deps "langchain-google-genai>=4.0.0"
pip install "google-genai>=1.53.0" "httpx>=0.28.1"
```

或把 Gemini 与数据层分到不同 venv。最省心是用 DeepSeek / MiniMax / 通义 / OpenAI 兼容中继等，完全不涉及这个冲突。

另澄清：**litellm / mcp 不是本项目的依赖**——报错里若提到它们，是你环境里其它包带来的。

**Q: 不进 CLI 交互，怎么批量跑多只标的、拿到和 CLI 一样的完整报告？**
看 `examples/run_cases.py`：它复用 CLI 的 `save_report_to_disk()`，每只标的输出与 CLI 一致的 `complete_report.md`（分析师 / 研究 / 交易 / 风险 / 组合五个分区）+ 一份字段齐全的 `summary.json`。用法：`uv run python examples/run_cases.py`（跑全部）或 `uv run python examples/run_cases.py 688017`（单只）；改 `build_config()` 切换 provider/model。

---

## 项目结构

```
TradingAgents-Astock/
├── tradingagents/
│   ├── agents/
│   │   ├── analysts/          # 7 个分析师
│   │   │   ├── market_analyst.py
│   │   │   ├── social_media_analyst.py
│   │   │   ├── news_analyst.py
│   │   │   ├── fundamentals_analyst.py
│   │   │   ├── policy_analyst.py        # A 股特化
│   │   │   ├── hot_money_tracker.py     # A 股特化
│   │   │   └── lockup_watcher.py        # A 股特化
│   │   ├── researchers/       # Bull / Bear 研究员
│   │   ├── risk_mgmt/         # 激进 / 保守 / 中立 辩手
│   │   ├── managers/          # Research Manager + Portfolio Manager
│   │   ├── trader/            # Trader（A 股交易约束）
│   │   └── utils/             # 状态定义、工具函数
│   ├── dataflows/
│   │   ├── a_stock.py         # A 股数据 vendor（直连 HTTP API，零第三方库）
│   │   ├── interface.py       # 数据接口抽象层
│   │   └── ...
│   └── graph/
│       ├── trading_graph.py   # 主入口：TradingAgentsGraph
│       ├── setup.py           # LangGraph 拓扑定义
│       ├── propagation.py     # 状态初始化与传播
│       ├── reflection.py      # 交易反思（CSI 300 基准）
│       └── conditional_logic.py
├── web/
│   ├── app.py                 # Streamlit 主入口
│   ├── runner.py              # 后台线程运行分析
│   ├── progress.py            # 线程安全进度追踪
│   ├── history.py             # 历史记录扫描
│   ├── pdf_export.py          # PDF 报告生成
│   ├── launch.py              # CLI 启动器
│   └── components/            # UI 组件
│       ├── sidebar.py         # 侧边栏（输入 + 历史）
│       ├── progress_panel.py  # 实时进度面板
│       └── report_viewer.py   # 报告展示
├── test_astock.py             # E2E 集成测试
├── CHANGES_FROM_UPSTREAM.md   # 与上游的完整改动记录
├── NOTICE                     # Apache 2.0 归属声明
├── LICENSE                    # Apache 2.0 许可证
└── pyproject.toml             # 包定义与依赖
```

---

## 致谢

本项目基于 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) 开源项目进行 A 股特化改造。感谢原作者的出色工作和 Apache 2.0 开源精神。

**原始论文**：[TradingAgents: Multi-Agents LLM Financial Trading Framework](https://arxiv.org/abs/2412.20138)

---

## 项目定位

**这是一个框架的工程实现，不是一个投资产品。**

- **它是什么**：[TradingAgents 论文](https://arxiv.org/abs/2412.20138)（TauricResearch）多 Agent 架构的 A 股工程实现，用于研究与教学——研究多 Agent 辩论在金融文本上的行为、A 股数据源如何接入、结构化输出如何落地。
- **它不是什么**：不是投资顾问、不是荐股软件、不提供任何投资服务。本仓库不发布针对具体证券的分析报告、评级或买卖建议；`examples/` 下只有可自行运行的脚本，没有任何预生成的个股结论。
- **模型和数据都是你自己的**：你配置自己的 LLM API key，在自己的机器上运行，产出的内容归你所有、由你判断、由你负责。项目本身不托管服务、不代为分析、不接触你的运行结果。
- **不产出可执行价位**：框架内**没有**建仓价 / 止损位 / 仓位 / 目标价这类输出——不是默认关闭，是代码里就没有。Trader 与 Portfolio Manager 只给方向、评级与理由。需要这类能力的使用者可以自行 fork 添加（Apache-2.0 允许），并自行承担相应责任、自行确认所在司法辖区的资质要求。

> **⚠️ 免责声明**
>
> - 本系统产出的所有内容均由 AI 自动生成，可能存在错误或偏差
> - 本项目不构成任何投资建议；投资决策请咨询持有中国证监会颁发资质的专业机构
> - 作者不对使用本工具产生的任何投资损失承担责任
> - 股市有风险，投资需谨慎

---

## 赞赏

如果这个工具帮到了你的投研工作流，欢迎请作者喝杯咖啡 ☕

<p align="center">
  <a href="https://buymeacoffee.com/simonlin1212"><img src="./assets/bmc-qr.png" width="180" alt="Buy Me a Coffee"></a>
</p>

> 想要什么功能？欢迎开 [Issue](https://github.com/simonlin1212/tradingagents-astock/issues) 提需求，赞助者的 Issue 优先处理。

---

## License

[Apache License 2.0](./LICENSE)

本项目是 TauricResearch/TradingAgents 的 fork，继承 Apache 2.0 许可证。详见 [NOTICE](./NOTICE)。

**作者：** Simon 林 · X [@linsizhen](https://x.com/linsizhen) · 邮箱：[simonlin0423@gmail.com](mailto:simonlin0423@gmail.com)
### 用个人 Claude 订阅额度（可选，v0.4.0 新增）

让节点经 Claude Agent SDK 走你**个人 Claude Pro/Max 订阅额度**，而不是按 token 计费的 Anthropic API。

> 与内置 `anthropic` provider 的区别：`anthropic` 走 `ANTHROPIC_API_KEY` = **按 token 计费**；本 provider 走本机已登录的 `claude` CLI = **消耗订阅额度，不产生 API 账单**。
>
> 仅供**个人自用**——它消耗的是你自己账号的订阅额度。把它做成给别人用的产品需要 Anthropic 授权，不在本项目范围内。

#### 1. 准备

```bash
pip install -e ".[agentsdk]"

# 本机 claude 已登录即可；headless / CI 环境需要显式 token：
claude setup-token          # 输出的 token 设为 CLAUDE_CODE_OAUTH_TOKEN

# 不打算保留付费降级的话，顺手清掉（可选）
unset ANTHROPIC_API_KEY
```

关于 `ANTHROPIC_API_KEY`：它的优先级高于订阅凭据，**但不会泄进 Agent SDK 子进程**——客户端在子进程环境里已把它显式置空，订阅额度照常生效。父进程保留它是为了让 `anthropic` 仍能作为撞额度后的降级 provider（否则就成死结：留着启动被拦、删掉又在真要降级时认证失败）。启动时只告警不中止。

#### 2. 开启

Web UI 侧栏「个人 Claude 订阅覆盖 (Agent SDK)」三档，或在 config 里设：

```python
config["deep_think_provider_override"]  = "claude_agent_sdk"   # 仅深度节点
config["quick_think_provider_override"] = "claude_agent_sdk"   # 再加这条 = 全节点
config["agent_sdk_model"]       = "opus"      # 深度节点
config["agent_sdk_quick_model"] = "sonnet"    # 分析师节点
```

**模型建议填别名 `opus` / `sonnet`**——`claude` CLI 的别名恒指向最新模型，写死 `claude-opus-4-8` 这类完整 id 会随版本迭代过期。完整 id 同样支持。

#### 3. 两条边界

- **额度而非 token**：订阅是按额度限流的。「所有节点」会把 7 个分析师 + 多空/交易员/风险辩手全压上去，跑几轮就可能撞上限——所以 `agent_sdk_quick_model` 默认给的是更省的 `sonnet`。撞额度会自动降级到你配的付费 provider（可用 `agent_sdk_fallback_provider` / `agent_sdk_fallback_model` 指定）。
- **凭据失效不降级**：OAuth token 过期时**直接报错中止**，不会静默降级到计费 provider——你开订阅模式就是为了避免账单，悄悄开始计费比报错更糟。报错里会给出 `claude setup-token` 的修复步骤。

#### 依赖说明

`[agentsdk]` 的依赖链是 `claude-agent-sdk → mcp → httpx2`，**不碰 httpx**，与 mootdx 的 `httpx<0.26` 无冲突（已 `uv lock` 实测）——和 #87 里被移除的 `[google]` 情况不同，不需要单开 venv。


