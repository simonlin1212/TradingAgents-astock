# TradingAgents-Astock

## 项目概述
基于 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)（65K Stars）的 A 股深度特化 fork。多 Agent 投研框架，7 个 Analyst 角色通过 Bull/Bear 辩论 + 三方风险辩论生成投资报告。

- **仓库**: https://github.com/simonlin1212/TradingAgents-astock
- **协议**: Apache 2.0
- **Python**: >=3.10
- **当前版本**: 0.4.0

## 架构

### 数据层（v0.2.5 全部直连 HTTP，零第三方数据库依赖）
| 来源 | 协议 | 数据 |
|------|------|------|
| mootdx | TCP 7709 | OHLCV K线、财务快照、F10 文本 |
| 腾讯财经 | HTTP (qt.gtimg.cn) | PE/PB/市值/换手率 |
| 东方财富 datacenter | HTTP (datacenter-web) | 龙虎榜、限售解禁、板块行情 |
| 东方财富 push2/push2his | HTTP (push2.eastmoney) | 实时行情、个股信息、板块列表、资金流(分钟+日级) |
| 东方财富 np-weblist | HTTP | 滚动新闻 |
| 新浪财经 | HTTP (money.finance.sina) | K线历史、财报三表 |
| 同花顺 10jqka | HTTP | EPS 一致预期、热股题材 |
| 财联社 cls.cn | HTTP | 全球财经快讯 |
| 百度股市通 | HTTP (gushitong.baidu) | 概念板块归属（资金流已迁移至东财push2） |

### Agent 角色（7 个）
原版 4 个（市场/情绪/新闻/基本面）+ A 股特化 3 个（政策分析师/游资追踪/解禁监控）

### 关键路径
- `tradingagents/dataflows/a_stock.py` — A 股数据 vendor，所有数据获取入口
- `tradingagents/dataflows/utils.py` — `safe_ticker_component` 路径安全校验 + 中文 ticker 自动解析
- `tradingagents/agents/` — 7 个 Analyst + Bull/Bear 辩论逻辑
- `tradingagents/graph/trading_graph.py` — `TradingAgentsGraph` 主入口
- `web/` — Streamlit Web UI
- `cli/` — CLI 入口（typer，`cli/main.py`）

### 常用命令
- 安装: `pip install -e .`（Gemini 需显式补装，见下方依赖冲突；可选 `pip install -e ".[agentsdk]"`）
- CLI: `tradingagents`（`tradingagents --help`）
- Web UI: `streamlit run web/app.py`，或 `tradingagents-web`（`web/launch.py`）
- 测试: `python -m pytest tests/ -v`（markers: `unit` / `integration` / `smoke`，`--strict-markers`）
- 改动后务必跑测试，新增依赖后跑 `uv lock --dry-run` 验证

### 中文股票名解析链路
用户/LLM 输入 → `safe_ticker_component` 检测中文 → `resolve_ticker()` → `_build_name_code_map()`（mootdx 全市场映射，缓存）→ 返回 6 位代码

## 已知问题与注意事项

### 依赖冲突（结构性，无解）
mootdx 钉死 `httpx>=0.25,<0.26`，与 langchain-google-genai 链要求的 `httpx>=0.28.1` 冲突，无版本组合可解（详见 pyproject.toml 注释 #87）。因此：
- 无 `[google]` extra；Gemini 需显式补装：`pip install --no-deps "langchain-google-genai>=4.0.0"` + `pip install "google-genai>=1.53.0" "httpx>=0.28.1"`
- 可选 `[agentsdk]` extra（v0.4.0）：`pip install -e ".[agentsdk]"` 走个人 Claude Pro/Max 订阅额度，依赖链 claude-agent-sdk → mcp → httpx2，**不碰 httpx**，无冲突
- ⚠️ 新增任何依赖后跑 `uv lock --dry-run` 验证——**pip 能装通不代表 uv 能锁**

### 东财接口防封限流（v0.2.11 新增，移植自 a-stock-data v3.2）
`a_stock.py` 里所有指向 `eastmoney.com` 的请求（push2 / push2his / datacenter-web / search-api / np-weblist 共 7 个调用点）统一走节流入口 `_em_get()`：模块级时间戳串行限流（默认间隔 `EM_MIN_INTERVAL=1.0s`，可用同名环境变量覆盖）+ 0.1~0.5s 随机抖动 + 复用 `requests.Session`（Keep-Alive）+ 默认 UA。多 Agent 跑批量分析不再触发东财临时封 IP。**仅东财限流**——mootdx(TCP) / 腾讯 / 新浪 / 同花顺 / 财联社 / 百度 等非东财源不受影响。批量场景可设 `EM_MIN_INTERVAL=1.5~2` 进一步降速。新增东财端点时务必走 `_em_get` 而非裸 `requests.get`。

### 模型兼容性
deepseek-v4-flash 等模型在 tool call 时可能返回中文股票名而非 6 位代码。`safe_ticker_component` 已加兜底自动转码，但不同模型表现仍有差异。

## Issue / PR 归档
所有 GitHub Issue 与 PR 的详细记录在 `issues/` 文件夹中（含 #18 归档），包含问题描述、根因分析、修复方案和当前状态。

## 开发规范
- 开发计划文档统一存放于 `dev_plan/`（命名如 `dev_plan/plan-*.md`）
- 改动前先跑 `python -m pytest tests/ -v` 确保不破坏现有测试
- `safe_ticker_component` 是安全边界，任何绕过路径校验的改动必须慎重评估
- 数据层新增接口遵循 `tradingagents/dataflows/interface.py` 的 vendor 路由模式
- Web UI 改动在 `web/` 目录，用 `streamlit run web/launch.py` 本地测试

## 维护红线（Context Budget）
本文件每次会话**全量加载**进上下文，必须保持精简（目标 ≤ 8KB / ~60 行）。分层归档：
- 一次性/时效性事实（版本历史、接口下线、PR 动态）→ 背景记忆（`remember`）或 `issues/` 归档；长文档 → 独立文件 + 本文件留一行指针（`CHANGELOG.md` / `DEV_LOG.md` / `CHANGES_FROM_UPSTREAM.md` / `issues/`）
- 只留**稳定、每行都值钱**的规则；新增内容前先问：这条信息未来每次会话都需要吗？不是 → 走记忆或归档文件
- ⚠️ `@path/to.md` 导入是**全文展开**进上下文，不省 token，仅用于组织/去重

## 相关项目
- [a-stock-data](https://github.com/simonlin1212/a-stock-data) — A 股 MCP 数据服务（Claude Code 用的 skill）
- 上游 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) — 原版框架
