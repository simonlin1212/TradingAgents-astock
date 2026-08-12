# TradingAgents-Astock

## 项目概述
基于 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)（65K Stars）的 A 股深度特化 fork。多 Agent 投研框架，7 个 Analyst 角色通过 Bull/Bear 辩论 + 三方风险辩论生成投资报告。

- **仓库**: https://github.com/simonlin1212/TradingAgents-astock
- **协议**: Apache 2.0
- **Python**: >=3.10
- **当前版本**: 0.5.14（2026-08-09 发布，经 codex 九轮审计）
  ⚠️ 改版本号时**三处要一起改**：`pyproject.toml` / `CHANGELOG.md` / 这一行。漏了这行会让后续 agent 和发版流程读到旧版本（`tests/test_version_consistency.py` 会拦）。

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
- `web/` — Streamlit Web UI
- `cli/` — CLI 入口

### 中文股票名解析链路
用户/LLM 输入 → `safe_ticker_component` 检测中文 → `resolve_ticker()` → `_build_name_code_map()`（mootdx 全市场映射，缓存）→ 返回 6 位代码

## 已知问题与注意事项

### 依赖冲突（v0.2.6 已缓解）
mootdx 钉死 `httpx>=0.25,<0.26`，与 langchain-google-genai 所需的 `httpx>=0.28.1` **结构性冲突**（该区间内每个 google-genai 版本都要 0.28.1，无解）。

**v0.3.1 起 `[google]` extra 已移除**（#87）：uv 构建覆盖所有 extra 的 universal lock，extra 存在就让**所有人**的 `uv sync` 失败。留空更糟（`pip install .[google]` 静默装空）。需要 Gemini 时显式装 `pip install --no-deps "langchain-google-genai>=4.0.0"` + `pip install "google-genai>=1.53.0" "httpx>=0.28.1"`；`google_client.py` 导入失败会打印这两条命令。⚠️ 新增依赖后务必跑 `uv lock --dry-run` 验证——**pip 能装通不代表 uv 能锁**。

### akshare 已移除（v0.2.5）
v0.2.5 起完全移除 akshare 依赖，所有数据通过直连 HTTP API 获取。

### 百度 PAE 资金流接口已下线（v0.2.7 已修复）
`fundsortlist` 和 `fundflow` 两个接口返回空（2026-05-19 确认）。v0.2.7 已替换为东财 push2 资金流 API。同时修复了 `RPT_ORGANIZATION_BUSSINESS`（改用席位筛选机构）和东财全球资讯 `req_trace` 参数。

### 东财接口防封限流（v0.2.11 新增，移植自 a-stock-data v3.2）
`a_stock.py` 里所有指向 `eastmoney.com` 的请求（push2 / push2his / datacenter-web / search-api / np-weblist 共 7 个调用点）统一走节流入口 `_em_get()`：模块级时间戳串行限流（默认间隔 `EM_MIN_INTERVAL=1.0s`，可用同名环境变量覆盖）+ 0.1~0.5s 随机抖动 + 复用 `requests.Session`（Keep-Alive）+ 默认 UA。多 Agent 跑批量分析不再触发东财临时封 IP。**仅东财限流**——mootdx(TCP) / 腾讯 / 新浪 / 同花顺 / 财联社 / 百度 等非东财源不受影响。批量场景可设 `EM_MIN_INTERVAL=1.5~2` 进一步降速。新增东财端点时务必走 `_em_get` 而非裸 `requests.get`。

### 未来函数防护（v0.5.1 新增，改数据层必读）
历史日期上跑分析时，数据层**不得**把"今天"的数据当成分析日当天的事实——报告里完全
看不出来，属于静默失败。`a_stock.py` 提供 `_is_historical(curr_date)` 与
`_snapshot_notice()` 两个共用工具：能做时点截断的就截断（如 `get_fund_flow` 按
curr_date 过滤历史行、复盘时整段不取实时分钟数据）；数据源根本没有历史时点值的
（腾讯实时估值、同花顺当前一致预期）就在正文顶部**明确告警**并指示模型不得当作当天
事实。**新增任何收 `curr_date` 的接口，必须处理这两种情况之一，不能收了不用。**

### 非 A 股代码防护（v0.5.3 新增，v0.5.5 补全）
`_normalize_ticker()` 会拒绝港股（4~5 位数字 / `.HK`）与美股代码。**新增任何 vendor
方法都必须走它，不要直接调 `safe_ticker_component`**——后者只做路径安全校验，不认市场。
mootdx/腾讯/东财对不存在的代码常返回空值或僵尸报价而非报错，绕过就等于让模型拿别的
市场的数据写报告。

⚠️ v0.5.3 曾声称"一个卡点覆盖 15 个接口"，**实际漏了 3 个**（龙虎榜/解禁/行业对比直接
调了 `safe_ticker_component`），拿 `00700` 调用会返回"近30日未上龙虎榜"这种看起来完全
正常的报告。v0.5.5 补全。**改完这类防护要枚举所有 vendor 逐个实测，别从设计推断覆盖面。**

### 截断告警要覆盖每种 provider 形状（v0.5.5）
`warn_if_truncated` 必须认全四种：Anthropic `stop_reason=max_tokens`、OpenAI 兼容
`finish_reason=length`、Gemini `finish_reason=MAX_TOKENS`（大写）、**OpenAI Responses
API `status=incomplete` + `incomplete_details.reason=max_output_tokens`**。最后一种最
要紧——`openai` 是默认 provider 且走 Responses API，v0.5.1 漏掉它导致这个告警在默认
配置下一次都不会触发。新增 provider 时必须补对应形状 + 一个会触发的样本测试。

### 分角色模型 role_llms（v0.5.0 新增）
可选，默认空表＝完全维持 quick/deep 两档原行为。合法角色名在 `graph/setup.py` 的
`ROLE_KEYS`；`GraphSetup.llm_for(role)` 是取模型的唯一入口。**新增 agent 节点时用
`self.llm_for("<角色名>")`，别直接引用 `self.quick_thinking_llm`**，否则该角色无法被
单独配置。

### 决策绩效统计（v0.5.2 新增）
`tradingagents performance` 读记忆日志里已结算的决策算指标，零 LLM 调用。
**改 `TradingMemoryLog` 的标签格式会直接打断它**（依赖 `[日期 | 代码 | 评级 | raw |
alpha | holding]` 结构，且 holding 带 `d` 后缀）。

⚠️ **指标命名即口径**：`direction_accuracy`（方向正确率）是唯一衡量判断准不准的——
看多要跑赢、看空要跑输才算对，Hold 不计入。`up_rate` / `outperform_rate` 只描述标的
怎么走，**与判断对错无关**。v0.5.2 曾把前者叫"胜率"，导致给 Sell 之后股价下跌（判断
正确）被记成失败，v0.5.5 改正。

### 模型兼容性
deepseek-v4-flash 等模型在 tool call 时可能返回中文股票名而非 6 位代码。`safe_ticker_component` 已加兜底自动转码，但不同模型表现仍有差异。

### 测试
**干净 clone（`pip install -e .` 不带 `[agentsdk]`）跑 `pytest tests/` 应当是
361 passed / 13 skipped / **0 failed**。出现 failed 就是真回归。**
需要可选依赖的用例用 `requires_sdk` 标记跳过——⚠️ **占位类型绝不要用 `Exception`
基类**：`ClaudeSDKError` 曾被占位成 `Exception`，进 `_FALLBACK_ERRORS` 后让"订阅凭据
失效不得降级到计费 provider"这条护栏彻底失效（v0.5.4 修）。

### CLI 必须保住裸跑（v0.5.9 血的教训）
`cli/main.py` 里的 `@app.callback(invoke_without_command=True)` **不能删**。Typer 只
注册一个命令时是"单命令模式"，裸跑 `tradingagents` 等于跑那个命令；一旦注册第二个
子命令就切换成"命令组模式"，裸跑直接报 `Missing command` 退出——而 README 和所有文档
写的都是裸跑，等于**每个现有用户升级后第一条命令就失败**。加子命令时务必先跑
`tests/test_cli_default_command.py`。

### 评级边界规则：改之前先跑整张矩阵（v0.5.12）
`rating.py` 里「中文标签 + 英文评级词」的边界判据是
**「后面不能延续成更长的词」**（`(?![A-Za-z0-9_-])`），不是"枚举允许的标点"。
这条规则前后被修了三轮才收敛——每轮都是往白名单加字符、每轮都漏：
无边界→`Buyer interest`判 Buy；`(?![A-Za-z])`→`Sell-off`判 Sell；枚举收尾标点
→`Buy（基于风险收益比）`**反被判成 Hold**。

⚠️ **动这条规则必须整张跑 `test_rating_value_boundary_matrix`（22 例）**，
只补自己想到的一两个用例正是前三轮反复的成因。误判会静默改写决策评级，
一路污染记忆日志与绩效统计。

### 探测 mootdx 不能覆写用户配置（v0.5.10，v0.5.12 重构）
`StdQuotes.__init__` 里有 `config.set('BESTIP', {'HQ': self.server})`——**每建一次带
`server` 的 client 都会持久化写进 mootdx 配置文件**。逐台探测会把用户原本配好的服务器
一路覆写，最后留下一台死的，还会连累同机其它用 mootdx 的程序。

用 `with _preserve_mootdx_bestip() as keep:` 包住探测：选出可用服务器时调 `keep()`
表示"这次覆写是想要的"，其余每条退出路径（**含异常**）自动还原。
⚠️ **别改回手动调还原函数**——那样再加一条提前返回就会漏掉一处，而漏掉的后果是
静默给用户留下一台死服务器。另外快照**必须在 `config.setup()` 之后**取，否则拿到的是
模块默认空值，"还原"反而把用户真实配置抹成空。

### 待处理 PR
- PR #18（hejingchi）：start_date 功能 + 主题切换 + Windows 字体。不建议直接 merge（与 v0.2.6 冲突），start_date 功能值得后续自行实现。

## Issue 归档
所有 GitHub Issue 的详细记录在 `issues/` 文件夹中，包含问题描述、根因分析、修复方案和当前状态。

## 开发规范
- 改动前先跑 `python -m pytest tests/ -v` 确保不破坏现有测试
- `safe_ticker_component` 是安全边界，任何绕过路径校验的改动必须慎重评估
- 数据层新增接口遵循 `tradingagents/dataflows/interface.py` 的 vendor 路由模式
- Web UI 改动在 `web/` 目录，用 `streamlit run web/launch.py` 本地测试

## 相关项目
- [a-stock-data](https://github.com/simonlin1212/a-stock-data) — A 股 MCP 数据服务（Claude Code 用的 skill）
- 上游 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) — 原版框架
