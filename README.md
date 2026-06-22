<h1 align="center">TradingAgents-Astock</h1>

<p align="center">
  基于 <a href="https://github.com/TauricResearch/TradingAgents">TauricResearch/TradingAgents</a>（65K ⭐）的 A 股深度特化 fork<br>
  全 Apache 2.0 开源 · pip install 即跑 · 零外部服务依赖
</p>

<p align="center">
  <b>⚠️ 免责声明：本项目仅供学习研究与技术演示，不构成任何投资建议。投资决策请咨询持牌专业机构。</b>
</p>

<p align="center">
  <a href="https://github.com/simonlin1212/tradingagents-astock/stargazers"><img alt="Stars" src="https://img.shields.io/github/stars/simonlin1212/tradingagents-astock?style=social"/></a>
  <a href="https://github.com/simonlin1212/tradingagents-astock/network/members"><img alt="Forks" src="https://img.shields.io/github/forks/simonlin1212/tradingagents-astock?style=social"/></a>
  <a href="https://arxiv.org/abs/2412.20138"><img alt="论文" src="https://img.shields.io/badge/论文-arXiv_2412.20138-B31B1B?logo=arxiv"/></a>
  <a href="./LICENSE"><img alt="License" src="https://img.shields.io/badge/License-Apache_2.0-blue"/></a>
  <a href="./CHANGES_FROM_UPSTREAM.md"><img alt="改动记录" src="https://img.shields.io/badge/改动记录-CHANGES-orange"/></a>
</p>

---

## 目录

- [为什么做这个 Fork](#为什么做这个-fork)
- [与上游对比](#与上游对比)
- [架构概览](#架构概览)
- [7 个 Analyst 角色](#7-个-analyst-角色)
- [数据源](#数据源)
- [快速开始](#快速开始)
- [Web UI](#web-ui)
- [配置说明](#配置说明)
- [项目结构](#项目结构)
- [致谢](#致谢)
- [Donate](#donate)
- [许可证](#许可证)

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
┌───────────────────────────────────────────────────────────┐
│              Analyst Report Generation                    │
│     Market → Social → News → Fundamentals                 │
│          → Policy → Hot Money → Lockup                    │
│           (Each Analyst loops with tools)                 │
├───────────────────────────────────────────────────────────┤
│                Bull vs Bear Debate                        │
│          Bull Researcher ↔ Bear Researcher                │
│                    (Up to N rounds)                       │
├───────────────────────────────────────────────────────────┤
│              Research Manager Synthesis                   │
│          (Deep-thinking LLM, outputs plan)                │
├───────────────────────────────────────────────────────────┤
│                 Trader Execution Plan                     │
│        (A-share: T+1 / Price Limit / Lot Size)            │
├───────────────────────────────────────────────────────────┤
│                  Triple Risk Debate                       │
│         Aggressive ↔ Conservative ↔ Neutral               │
├───────────────────────────────────────────────────────────┤
│           Portfolio Manager Final Decision                │
│   (Deep-thinking LLM, outputs Buy/Hold/Sell + Position)   │
└───────────────────────────────────────────────────────────┘
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

> **前提条件**：Python >= 3.10。必须使用 LLM API Key（不能用 Claude/ChatGPT 订阅版），每次分析需 30-50 次 LLM 调用。

### 第一步：克隆项目并创建虚拟环境

```bash
git clone https://github.com/simonlin1212/tradingagents-astock.git
cd tradingagents-astock

# 创建并激活虚拟环境（推荐，避免污染全局 Python）
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# Windows CMD
.\.venv\Scripts\activate.bat
# macOS / Linux
source .venv/bin/activate
```

> **为什么要用虚拟环境？** 虚拟环境让每个项目的依赖互相隔离，不会影响系统 Python 或其他项目。激活后终端提示符前会出现 `(.venv)` 字样。

### 第二步：安装依赖

```bash
pip install -e .

# 如需使用 Google Gemini 模型（可选）：
pip install -e ".[google]"
```

> **装完即可用，无需 Docker。** Docker 仅是可选的部署方式，本地开发不需要。

### 第三步：配置 LLM API Key

在项目根目录创建 `.env` 文件（已提供 `.env.enterprise.example` 可参考），**只填你用的那个供应商的 Key**，其他留空即可：

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
ANTHROPIC_AUTH_TOKEN=your-kimi-token
```

> **注意**：每个供应商用各自的环境变量名，不是 `OPENAI_API_KEY`。DeepSeek 用 `DEEPSEEK_API_KEY`，通义用 `DASHSCOPE_API_KEY`，智谱用 `ZHIPU_API_KEY`。

### 第四步：运行分析

**方式一：代码运行（推荐新手先体验）**

编辑项目根目录的 `main.py`，选择你的供应商配置：

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from dotenv import load_dotenv

load_dotenv()

# 从默认配置继承所有字段，再覆盖自定义部分（推荐做法）
config = DEFAULT_CONFIG.copy()
config.update({
    "llm_provider": "deepseek",           # 改成你的供应商
    "deep_think_llm": "deepseek-chat",    # 改成你的模型
    "quick_think_llm": "deepseek-chat",   # 改成你的模型
    "output_language": "Chinese",
})

# A 股数据源（免费直连，无需额外配置）
config["data_vendors"] = {
    "core_stock_apis": "a_stock",
    "technical_indicators": "a_stock",
    "fundamental_data": "a_stock",
    "news_data": "a_stock",
    "signal_data": "a_stock",
}

ta = TradingAgentsGraph(debug=True, config=config)

# 传入 6 位 A 股股票代码 + 日期，运行分析
_, decision = ta.propagate("600519", "2026-06-15")
print(decision)
```

然后运行：

```bash
python main.py
```

**其他供应商配置示例**（只需改 `config.update(...)` 里的内容）：

```python
# ── MiniMax（推荐）─────────────────────────────
config.update({
    "llm_provider": "minimax",
    "deep_think_llm": "MiniMax-M2.7",
    "quick_think_llm": "MiniMax-M2.7-highspeed",
    "output_language": "Chinese",
})

# ── 通义千问 Qwen ──────────────────────────────
config.update({
    "llm_provider": "qwen",
    "deep_think_llm": "qwen-max",
    "quick_think_llm": "qwen-turbo",
    "output_language": "Chinese",
})

# ── Anthropic + Kimi 中转 ──────────────────────
config.update({
    "llm_provider": "anthropic",
    "deep_think_llm": "claude-sonnet-4-6",
    "quick_think_llm": "claude-sonnet-4-6",
    "backend_url": "https://api.kimi.com/coding/",
    "output_language": "Chinese",
})
```

**方式二：Web UI（图形界面，不写代码）**

```bash
streamlit run web/app.py
```

打开浏览器访问 `http://localhost:8501`，在侧边栏选择模型、输入股票代码即可。

**方式三：CLI 交互式**

```bash
tradingagents            # 交互式命令行
tradingagents --help     # 查看所有选项
```

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

- **模型自选**：侧边栏支持 9 个 LLM 供应商切换（MiniMax/DeepSeek/Qwen/GLM/OpenAI/Anthropic/Google/xAI/Ollama）
- **一键分析**：输入 6 位 A 股代码 + 日期，点击「开始分析」
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
| `output_language` | `"Chinese"` | 报告输出语言（内部辩论始终英文） |
| `max_debate_rounds` | `1` | Bull vs Bear 辩论轮数 |
| `max_risk_discuss_rounds` | `1` | 风险三方辩论轮数 |
| `data_vendors` | 全部 `"a_stock"` | 数据供应商路由 |
| `checkpoint_enabled` | `False` | 启用 SQLite 断点续跑 |
| `memory_log_max_entries` | `None` | 交易记忆最大条目数 |

---

## 常见问题排错

**Q: 用 DeepSeek/通义/智谱，却报 `OpenAIError: The api_key client option must be set ... OPENAI_API_KEY`？**
每个供应商用**各自的环境变量**，不是 OPENAI_API_KEY：DeepSeek=`DEEPSEEK_API_KEY`、通义=`DASHSCOPE_API_KEY`、智谱=`ZHIPU_API_KEY`、MiniMax=`MINIMAX_API_KEY`、xAI=`XAI_API_KEY`、OpenRouter=`OPENROUTER_API_KEY`。在项目根目录 `.env` 里设置对应变量后**重启**程序。（v0.2.12 起缺 key 会直接提示该用哪个变量名。）

**Q: 导出 PDF 报 `UnicodeEncodeError: 'latin-1' codec can't encode`？**
你的环境里装了**旧版 `fpdf`（pyfpdf）**，它和本项目用的 `fpdf2` 都以 `fpdf` 名称导入、互相冲突。执行：`pip uninstall -y fpdf && pip install "fpdf2>=2.8.6"`。实在不行可改用「下载 Markdown」导出（零依赖，永远可用）。

**Q: Docker 里导出 PDF 报「未找到中文字体」？**
v0.2.12 起 Dockerfile 已内置 `fonts-noto-cjk`，重新 `docker build` 即可。旧镜像可临时 `apt install fonts-noto-cjk`，或改用 Markdown 导出。

**Q: Docker 启动报 `[Errno 13] Permission denied: /home/appuser/.tradingagents/cache`？**
旧版镜像里没预建数据目录，`docker-compose` 的命名卷挂上来时被 Docker 建成 `root` 属主，而容器内进程以 `appuser` 运行、写不进去。v0.2.14 起 Dockerfile 已预建 `/home/appuser/.tradingagents`（cache/logs/memory）并归属 appuser，命名卷会继承该属主。**升级方式**：`git pull` 后 `docker compose build --no-cache` 重建镜像；若想保留旧数据卷可先 `docker run --rm -v tradingagents_data:/d alpine chown -R 1000:1000 /d` 修正属主，否则 `docker volume rm tradingagents_data` 后重建即可。

**Q: 部分分析师报告（情绪/新闻/基本面/政策/游资/解禁）空白不显示？**
这些报告由对应 Analyst 调用数据工具后生成，**空报告会被自动跳过不显示**。数据源本身是健康的（腾讯/mootdx/同花顺/东财实测出数）；报告为空通常是**所选模型 tool-call 能力弱**（如部分 deepseek/minimax 轻量模型不稳定地调用工具）。建议换用 tool-call 更稳的模型（deepseek-chat / 通义 / GLM-4 / Claude / GPT 等），或重试。

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

## 许可证

[Apache License 2.0](./LICENSE)

本项目是 TauricResearch/TradingAgents 的 fork，继承 Apache 2.0 许可证。详见 [NOTICE](./NOTICE)。

## Sponsor

如果这个工具帮到了你的投研工作流，欢迎请作者喝杯咖啡 ☕

<p align="center">
  <img src="./assets/wechat-sponsor.jpg" width="240" alt="微信赞赏码">
</p>
<p align="center">
  <a href="https://ifdian.net/a/simonlin">爱发电</a> ·
  <a href="https://buymeacoffee.com/simonlin1212">Buy Me a Coffee</a>
</p>

> 想要什么功能？欢迎开 [Issue](https://github.com/simonlin1212/tradingagents-astock/issues) 提需求，赞助者的 Issue 优先处理。

---

## 免责声明

> **本项目仅供学习研究与技术演示，不构成任何投资建议。**
>
> - 本系统产出的所有分析报告和交易信号均由 AI 自动生成，可能存在错误或偏差
> - 投资决策请咨询持有中国证监会颁发资质的专业机构
> - 作者不对使用本工具产生的任何投资损失承担责任
> - 股市有风险，投资需谨慎
