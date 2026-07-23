# Changelog

All notable changes to TradingAgents are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Breaking changes within the 0.x line are called out explicitly.

## [0.2.21] — 2026-07-23

新增可配置的技术分析回溯窗口 / 按月分析（#16）。无破坏性变更、无新依赖。

### 新增
- **自定义数据起始日期 / 按月分析（#16）**：此前技术分析的回溯天数由模型自行决定（工具默认 ~30 天），用户无法控制分析区间。现在：
  - **Web 侧栏新增「数据起始日期」**（默认本月第一天）——分析区间 = 起始日期 → 分析日期，用于「按月」或自定义时段分析。
  - **CLI 新增 Step 2b「Data Start Date」**——交互式输入起始日期（默认分析月首日）。
  - 两端都据「起始日期 → 分析日期」算出 `market_lookback_days`（下限 5 天），写入 config。
  - **market_analyst 读取并注入 prompt**：显式要求调用 `get_stock_data` / `get_indicators` 时 `look_back_days` 传该值，「必采清单」的「近 N 日累计涨跌幅」也随之联动。
  - 新增 config 键 `market_lookback_days`（`default_config.py`，默认 `None` = 保持原行为，模型自选 ~30）。
  - 感谢 @hejingchi 定位到 `get_indicators` 的 `look_back_days` 参数并提交 PR #18 的相关思路（本实现单独干净落地，未夹带 PR #18 的字体/主题改动）。

### 测试
- 新增 `tests/test_market_lookback.py`：`DEFAULT_CONFIG` 含键且默认 None、config 读取逻辑（配置 15 → 15 / None → 默认 30）、天数派生 clamp（本月首日→今日=22、起始≥分析→5、跨月=60）。
- 独立验证（py3.12）：config set/get 流 + 派生逻辑 7 条断言全过；5 改动文件 + 测试文件 py_compile 全过；market_analyst f-string 注入渲染正确（无杂散括号）。

## [0.2.20] — 2026-07-23

新增通用「OpenAI 兼容（自定义 base_url）」provider，接任意 OpenAI 兼容网关（#77 / #81）。无破坏性变更、无新依赖。

### 新增
- **`openai_compatible` 通用 provider（#77 / #81）**：面向任意讲 OpenAI Chat Completions 协议的中继 / 网关（9Router、AI Router、自建代理）——用户自填 `base_url` + `model` + 通用 Key，无厂商写死默认值。此前只能通过"借用 OpenRouter 档 + 覆盖 backend_url"这种不直观的方式实现，现在是一等公民。
  - `llm_clients/factory.py`：`openai_compatible` 加入 OpenAI 兼容路由。
  - `llm_clients/openai_client.py`：新分支——`base_url` 必填（缺失给明确报错），Key 从 `OPENAI_COMPATIBLE_API_KEY` 读取（回退 `OPENAI_API_KEY`），走标准 Chat Completions（**非** OpenAI Responses API，兼容性最好），model 名自由填。
  - `llm_clients/validators.py`：`openai_compatible` 与 ollama/openrouter 一样接受任意 model 名、不告警。
  - **Web UI**（`web/components/sidebar.py`）：供应商下拉新增「OpenAI 兼容（自定义 base_url·9Router/AI Router/自建代理）」，自动走自定义 model ID 输入 + Base URL 必填提示。
  - **CLI**（`cli/utils.py`）：Provider 列表新增 `OpenAI-Compatible`，选中后交互式提示输入 Base URL，模型 ID 手动填写。
  - README 新增 `.env` 方案 H + FAQ「如何接第三方 OpenAI 兼容网关」+ 供应商计数更新。

### 测试
- 新增 `tests/test_openai_compatible_provider.py`：factory 路由、`base_url` 缺失报错、Key 缺失报错、`OPENAI_COMPATIBLE_API_KEY` 优先与 `OPENAI_API_KEY` 回退、自定义 model 不告警。
- `tests/test_model_validation.py` 的自定义 model 免告警用例扩展含 `openai_compatible`。
- 独立验证（py3.12）：validators 免告警、factory 路由、`get_llm` 的 base_url 必填 + Key 解析分支逻辑全通过；5 改动文件 + 2 测试文件 py_compile 全过。

## [0.2.19] — 2026-07-23

TRADING SIGNAL 恒为 HOLD 的真 bug 修复（#78 / #80）。无破坏性变更、无新依赖。

### 修复
- **中文输出时 TRADING SIGNAL 恒为 HOLD，与最终评级不一致（#78 / #80）**：信号提取器 `parse_rating`（`tradingagents/agents/utils/rating.py`）此前只识别英文五档词（Buy/Overweight/Hold/Underweight/Sell）。当 `output_language` 设为中文、且模型（DeepSeek/MiniMax/Qwen 或 OpenAI 兼容中继等）的结构化输出**回退到自由文本**时（见 `agents/utils/structured.py` 的 `invoke_structured_or_freetext`），最终决策是**中文散文**（如「最终评级：卖出」），没有英文 `Rating:` 头 → `parse_rating` 一个词都匹配不到 → **静默返回默认值 Hold**。即使研究经理明确给出「卖出/增持」，顶部 TRADING SIGNAL 也永远显示 HOLD。
  - `parse_rating` 现同时识别中文五档词（买入/增持/持有(中性)/减持/卖出，含强烈买入/清仓等变体）与中文标签（最终评级/评级/投资建议/推荐评级 等 + `：` + 评级）。四段解析：英文标签 → 中文标签 → 英文裸词 → 中文裸词，显式标签优先于裸词，最长匹配优先（强烈买入 胜过 买入）。英文路径行为不变。
  - **一并修 `web/history.py` 的 `extract_signal`**（历史重载展示走的第二个提取器）：原本也是英文 `BUY/SELL/HOLD` 裸扫、仅三档、默认 N/A，对中文同样失效。改为委托 `parse_rating`，并优先读 `final_trade_decision`，使历史重载信号与实时 `process_signal` 一致。
  - CLI（`cli/main.py`）、Web 实时展示、Web 历史重载、以及 memory 日志的评级标签（`agents/utils/memory.py` 同走 `parse_rating`）四处同时修复——`parse_rating` 是唯一咽喉。

### 测试
- `tests/test_signal_processing.py` 新增 `TestParseRatingChinese`（含 #78 原样决策文本 → Sell、五档中文标签、强烈/清仓变体、「标签压过散文里的减持」、中文裸词兜底、中英混排英文标签仍优先）。
- `tests/test_web_history.py` 新增 4 项 `extract_signal` 回归（中文最终决策→真实评级、优先 final_trade_decision、英文仍可用、无法识别→N/A）。
- 独立验证（py3.12）：`parse_rating` 16/16、`extract_signal` 6/6 全通过，含 #78 原样场景；改动文件 py_compile 全过。

## [0.2.18] — 2026-07-10

合并社区 PR #75（致谢 @wangyuxun6699），与 v0.2.17 的 #76 修复同属一类问题：LLM 工具调用把非股票标识当 `ticker` 传入。

### 合并社区 PR
- **#75 新闻工具校验 ticker 防概念词中断分析（@wangyuxun6699）**：运行 000629 分析时部分 Agent 把概念词「钒电池」当 `ticker` 传给 `get_news`，底层解析抛 ValueError 中断分析。三层修复：① `get_news` / `get_insider_transactions` 增加 6 位代码校验，误传时**返回可恢复的错误提示**（不抛异常、不中断 LangGraph）；② 修正 5 个分析师提示词里误导性的 `get_news(query, ...)` 描述 → `get_news(ticker, ...)`（**这是模型传概念词的提示词层根因**）；③ 强化 `instrument_context`，明确「参数名为 ticker 时只传目标股票代码」。
- 与 v0.2.17 的 `resolve_ticker` 报错改进形成互补防线：提示词预防 → 工具层校验软着陆 → 解析层报错可自纠。

### 测试
- PR 新增 `tests/test_news_data_tools.py` 3 项（概念词拦截不进 vendor 层 / 合法 6 位码正常路由）通过。
- 全量回归：Python 3.12 干净 venv 下 `pytest tests/` **135 passed + 44 subtests**（仅 test_google_api_key 因未装可选依赖 `[google]` 跳过）。

## [0.2.17] — 2026-07-10

两个健壮性修复，无破坏性变更、无新依赖。

### 修复
- **fpdf 包损坏导致 Web UI 启动即崩（#72）**：`web/pdf_export.py` 顶部的 `from fpdf import FPDF` 一旦失败（fpdf2 卸载不干净留下 namespace 残包、或 pyfpdf 1.x 没有 `fpdf.enums`），`web/app.py` 在 import 链上直接崩溃、整个应用起不来。现改为守卫式导入：fpdf 坏了只禁用 PDF 导出（Markdown 导出照常），点击 PDF 按钮时给出确切修复命令 `pip uninstall -y fpdf fpdf2 && pip install "fpdf2>=2.8.0"`。
- **LLM 把行业名当股票代码时报错信息不可自纠（#76）**：弱模型做工具调用时偶尔把行业/概念名（如 002174 游族网络所属行业「游戏」）当 `ticker` 传入，旧报错「找不到股票 '游戏'，请检查名称是否正确」让用户困惑（自己输入的明明是 002174）、也无法引导模型纠正。新报错写明「ticker 只接受 6 位代码或完整股票名称，行业/概念/板块名无效」，模型读到 ToolMessage 后可在下一次调用自我纠正。

### 测试
- 实测模拟损坏 fpdf（`sys.modules` 注入空 namespace 包，复现 #72 同款 `cannot import name 'FPDF' from 'fpdf' (unknown location)`）：`web.pdf_export` import 成功、`generate_markdown` 正常出稿、`generate_pdf` 抛带修复指引的 `PDFExportError`。
- `resolve_ticker` 回归：`002174`/`600519.SH`/`贵州茅台` 正常解析；`游戏` 触发新报错文案。
- `tests/test_pdf_export.py` + `test_safe_ticker_component.py` + `test_stock_display.py` + `test_web_history.py` + `test_astock_sina_supplement.py` 共 25 项通过（2 项 pdf 字体用例在本机因 fpdf2 2.8.4 < 2.8.6 环境原因失败，HEAD 上同样失败，与本次改动无关）。

## [0.2.16] — 2026-06-28

本版采纳一个社区贡献的批量样例脚本 + 文档补充，无核心代码改动。

### 采纳社区贡献
- **`examples/run_cases.py` 升级（采纳 #68 @zcc2xj）**：旧版批量脚本只把 `final_trade_decision` 手写进简易 `.md`。新版复用 CLI 的 `save_report_to_disk()`，每只标的输出与 CLI **完全一致**的 `complete_report.md`（分析师 / 研究 / 交易 / 风险 / 组合五个分区子目录 + 合并报告），并落一份字段齐全的 `summary.json`（10 个顶层报告 + Bull/Bear 辩论 + 三方风险辩论历史）。解决 #68「example 脚本如何拿到 CLI 那样的 complete_report.md」。

### 文档
- **README 常见问题新增 httpx 依赖冲突说明（#70）**：澄清 **litellm / mcp 不是本项目依赖**（用户报错里这两条来自其环境的其它包）；核心安装 `pip install -e .` 默认不冲突，仅装 `[google]` 用 Gemini 时 mootdx（`httpx<0.26`）与 google-genai（`httpx>=0.28`）互斥。给出解法：mootdx 走 TCP、运行时不调 httpx（实测 0.11.7 在 httpx 0.28.1 下取数正常，可放心升 httpx）/ 分 venv / 用国内直连模型不装 `[google]`。
- README 常见问题新增「不进 CLI 怎么批量跑、拿完整报告」条目，指向 `examples/run_cases.py`。

### 测试
- `examples/run_cases.py` py_compile 语法通过；静态核对 `save_report_to_disk(final_state, ticker, save_path)` 签名匹配、`complete_report.md` 路径返回值正确（`cli/main.py:738-739`），脚本引用的 10 个顶层 state 字段 + debate 子状态字段全部匹配 `agent_states.py` 真实定义（含 policy/hot_money/lockup 三个 A 股特化字段）。端到端运行需用户自备 LLM key。
- httpx 解法复用 a-stock-data 同源实测：净 venv 装 mootdx 0.11.7 后 `--no-deps` 升 httpx 0.28.1，`bars()` 取日线 / 1 分钟均正常。

## [0.2.15] — 2026-06-20

本版合并 4 个社区 PR + 一批针对性修复，主线集中在「数据可靠性 + 模型可用性 + 全新安装体验」。

### 合并社区 PR（致谢贡献者）
- **#64（@wikinl）**：A 股日 K 数据滞后时未触发新浪补齐 → 修复（mootdx 返回非空但最新日期早于目标日时强制走新浪补最新交易日，并把 `15:00:00` 时间戳压到自然日，避免被 `Date <= cutoff` 误过滤）。直接缓解 #60「数据缺失」。
- **#57（@zhanghang02）**：Web 支持中断续跑 + 侧边栏暂停/停止控制（LangGraph checkpoint resume）。缓解 #27「页面刷新丢数据」。
- **#56（@zhanghang02）**：中文 PDF 字体发现 + 排版稳定性增强（`fc-match`/WQY 优先、字体环境变量覆盖、TTC 字面选择）。
- **#55（@zhanghang02）**：报告标的统一显示为「代码 + 名称」。合并时解决与 #57 在 `web/runner.py` 的冲突（#57 的 `finalize_graph_run` 已含 `graph.ticker`/`_log_state`，仅保留归一化调用挪到落盘前）。

### 修复
- **mootdx 0.11.x 全新安装 BESTIP 空串崩溃 → 中文股票名解析失败（#46/#66 根因之一）**：`_get_mootdx_client()` 升级为健壮版——TCP 探测内置可用通达信服务器列表，用显式 `server=(ip,port)` 绕过 `BESTIP.HQ` 空串 bug，三级 fallback（bestip 测速 → 裸 factory → 明确报错）。`_build_name_code_map()` 改走该 client 并加 try/except，解析失败时给出「请重试或直接输入 6 位代码」而非冒泡成风马牛不相及的报错。实测 mootdx 0.11.7：10/10 服务器可达，`贵州茅台→600519`、`宁德时代→300750` 正常。
- **`.env` 未优先于残留环境变量（#66）**：`web/app.py` 的 `load_dotenv` 改为 `override=True`，让 `.env` 的值优先；并注明启动后改 `.env` 需重启 Web 服务。
- **fpdf2 版本下限过低导致 #56 在旧版崩溃**：`collection_font_number`（TTC 字面选择）是 fpdf2 **2.8.6**（2026-02-18）才引入的参数，旧约束 `fpdf2>=2.8.0` 下用户若缓存 2.8.0~2.8.5 会在中文 PDF 导出时抛 `TypeError` → 收紧为 `fpdf2>=2.8.6`，错排提示同步更新。

### 新增
- **OpenRouter 进入 Web 侧栏模型选择器（摘自 #32，缓解 #45/#62）**：`factory`/`_PROVIDER_CONFIG` 早已支持 OpenRouter，但侧栏 `_PROVIDERS` 未列 → 补上「OpenRouter（聚合）」一项，选中后填 `vendor/model` 形式的模型 ID（如 `deepseek/deepseek-chat`）即可。凭证池/profile 体系（#32 其余部分）超出「加个模型」范围，另行评估。

### 文档
- README「快速开始」明确「装完即可用、无需 Docker」（直接 `streamlit run web/app.py` 或 `tradingagents`），缓解 #46 安装说明困惑。

### 测试
- 4 个 PR 自带测试在隔离环境实测：`test_stock_display`(11)/`test_progress_pause`(4)/`test_web_history`(3)/`test_astock_sina_supplement`(2) 全通过（PDF 测试在 Python 3.9 + 旧 fpdf2 环境因版本特性跳过，真实 ≥3.10 + fpdf2≥2.8.6 环境正常）。
- mootdx 健壮 client + 中文名解析在 mootdx 0.11.7 真实环境实测通过。

## [0.2.14] — 2026-06-18

### 修复

- **Docker 命名卷权限崩溃（#46，感谢 @tyraanTao 等报告）**：`docker compose up` 后容器内进程以
  `appuser` 运行，但 `docker-compose.yml` 的命名卷 `tradingagents_data` 挂到
  `/home/appuser/.tradingagents` 时，由于镜像里没有预建该目录，Docker 把挂载点建成了
  `root:root`，导致应用写缓存被拒：`[Errno 13] Permission denied: /home/appuser/.tradingagents/cache`。
  Dockerfile 现在在 `USER appuser` 之后**预建** `/home/appuser/.tradingagents`（含 `cache` /
  `logs` / `memory` 三个子目录）——Docker 对空命名卷会继承镜像挂载点目录的属主，于是卷归属 appuser，
  容器可正常写入。
  - 升级：`git pull` 后 `docker compose build --no-cache` 重建镜像；旧数据卷可先
    `docker run --rm -v tradingagents_data:/d alpine chown -R 1000:1000 /d` 修正属主，
    或 `docker volume rm tradingagents_data` 后重建。

### 说明

- 仅 Dockerfile 改动（预建数据目录），Python 代码 / 数据层 / Agent 逻辑零改动。
- 同批排查的 #59（PDF `latin-1` 崩溃）与 #66（`OPENAI_API_KEY` 报错）经复现确认已分别在
  v0.2.12 修复（`_ensure_fpdf2()` 守卫 + Markdown 兜底 / 各供应商独立 Key 提示），升级即可，无需改动。

## [0.2.13] — 2026-06-04

### Security

- **CLI 路径穿越加固（#51，感谢 @mituxunzhi 报告并给出修复方向）**：CLI 是唯一未对 ticker 做
  路径组件校验的入口（Web UI / `a_stock.py` / `checkpointer.py` / `stockstats_utils.py` 早已统一走
  `safe_ticker_component`）。ticker 会被拼进 `results_dir / <ticker> / <date>` 和报告保存路径，
  形如 `../../tmp/evil` 的输入可写到目标目录之外。三处加固：
  - `cli/utils.py:normalize_ticker_symbol()` — 现在委托 `safe_ticker_component()` 校验（拒绝
    `/`、`..`、`~`、`\0`、绝对路径、纯点等），并返回校验/解析后的安全值（中文名自动解析为 6 位代码）；
  - `cli/main.py:get_ticker()` — 输入后即校验，非法则提示并**重新询问**（而非崩溃），返回安全值；
  - `cli/main.py` 报告保存 — 保存路径先 `.resolve()`，若落在当前目录之外则**提示并要求确认**，
    拒绝则取消保存。
  - 实测：`../../tmp/evil`、`/etc/passwd`、`~/secret`、`a/../../b`、`\x00evil`、`.` 等 11 个穿越载荷
    全部被拒；`SPY` / `600519` / `0700.HK` / `^GSPC` / `BRK.B` 等正常代码全部通过且保留交易所后缀。

### 说明

- 纯 CLI 入口安全加固，复用既有 `safe_ticker_component` 校验器，数据层 / Agent 逻辑零改动。

## [0.2.12] — 2026-06-03

### Fixed

- **PDF 导出中文崩溃（#54）**：项目依赖 `fpdf2`，但它和早已废弃的 `pyfpdf`（1.x）**都以 `fpdf`
  名称导入**，二者共存时谁后装谁生效。用户环境里若残留 pyfpdf，导出中文报告会在库内部抛出晦涩的
  `UnicodeEncodeError: 'latin-1' codec can't encode`（pyfpdf 用 latin-1 编码每一页）。
  `web/pdf_export.py` 新增 `_ensure_fpdf2()`：导出前检测 fpdf 版本，若是旧库则抛出**可操作**的中文
  提示（`pip uninstall -y fpdf && pip install "fpdf2>=2.8.0"`），不再让 PDF 渲染到一半崩溃。
- **Docker 内无法导出 PDF（#48）**：运行镜像基于 `python:3.12-slim`，不含任何中文字体，
  `_find_cjk_font()` 返回 None → 抛「未找到中文字体」。Dockerfile 运行阶段新增
  `apt-get install fonts-noto-cjk`，容器内 PDF 导出开箱即用。
- **DeepSeek/通义/智谱等报 `OPENAI_API_KEY must be set`（#42）**：这些 OpenAI 兼容供应商各自需要
  **专属环境变量**（DeepSeek=`DEEPSEEK_API_KEY`、通义=`DASHSCOPE_API_KEY`、智谱=`ZHIPU_API_KEY`、
  MiniMax=`MINIMAX_API_KEY` 等），但 key 缺失时 ChatOpenAI 只会抛出令人误解的 `OPENAI_API_KEY` 错误。
  `openai_client.py` 现在在缺 key 时**明确指出该供应商对应的环境变量名**；Web 侧边栏 help 文案也补齐了
  每个供应商的 key 变量对照，避免用户设错。

### 说明

- 三项均为环境/配置类问题的健壮性修复，数据层与 Agent 逻辑无改动。PDF 修复经 fpdf2 实测生成
  中文报告通过 + 旧库检测单测通过；#42 经 api_key 解析分支单测全用例通过。

## [0.2.11] — 2026-05-30

### Changed

- **东财接口统一限流防封（移植自 a-stock-data v3.2）**：数据层 `a_stock.py` 里所有指向
  `eastmoney.com` 的请求（push2 / push2his / datacenter-web / search-api / np-weblist
  共 7 个调用点）统一收口到新的节流入口 `_em_get()`，多 Agent 投研跑批量分析时不再触发
  临时封 IP（社区实测东财风控：每秒 >5 / 并发 ≥10 / 1 分钟 ≥200 / 5 分钟 ≥300 触发封禁，
  多位用户反馈过）。具体：
  - 模块级 last-call 时间戳 + 最小间隔 `EM_MIN_INTERVAL`（默认 1.0s，可用同名环境变量覆盖）
    + 0.1~0.5s 随机抖动，串行限流，QPS ≤ 1；
  - 复用 `requests.Session`（Keep-Alive）+ 默认 UA；各端点保留自己的 Referer/Origin header；
  - **仅东财接口限流**——mootdx(TCP) / 腾讯 / 新浪 / 同花顺 / 财联社 / 百度 等非东财源
    不受影响（实测不封 IP）。批量场景可设 `EM_MIN_INTERVAL=1.5~2` 进一步降速。

### Tested

- 实测 4 次连续 `_em_get` 请求东财 push2（600519 = 贵州茅台），HTTP 200 返回真实数据；
  相邻调用间隔 1.47 / 1.18 / 1.42s 均 ≥1.0s，限流生效。
- `get_industry_comparison` / `get_fund_flow` / `get_dragon_tiger_board` 三个东财公共函数
  端到端跑通（走同一已验证的 `_em_get` 通道）；`py_compile` 通过；grep 复核：7 个 `_em_get`
  调用点 + 0 个残留 `_req.` + 8 个非东财源（mootdx/腾讯/新浪/同花顺/财联社/百度）未被误伤。

---

## [0.2.10] — 2026-05-30

### Added

- **Web UI 支持第三方 / 代理 API 网关（#35）**：侧边栏新增「API Base URL」输入框，
  也可在 `.env` 设 `BACKEND_URL`。方便国内用户通过中转网关访问 Claude / OpenAI 等模型
  （API Key 仍从 `.env` 读取，如 `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`）。
  侧边栏输入优先于环境变量，留空则用所选供应商官方地址。

---

## [0.2.9] — 2026-05-30

### Added

- **Markdown 报告导出**：分析结果页新增「下载 Markdown」按钮。MD 导出零字体依赖、
  跨平台永远可用，是 PDF 之外的稳妥兜底（#17 多位用户请求）。

### Fixed

- **PDF 中文字体跨平台崩溃（#22 / #30 / #31）**：原 `_FONT_CANDIDATES` 只列了
  macOS/Linux 字体，Windows 用户找不到中文字体 → fpdf 回退 Helvetica → 渲染中文时
  抛 `FPDFUnicodeEncodingException` / `Character "股" ... outside the range`。
  现改为**按操作系统排序的字体候选**（Windows 微软雅黑/黑体/宋体、macOS 苹方、
  Linux Noto/文泉驿）+ 递归扫描字体目录兜底。
- **PDF 失败拖垮整个结果页**：`generate_pdf` 原先在结果页渲染时被 eager 调用，一旦
  报错整页崩成 traceback，用户连分析结果都看不到。现改为 **try/except 包裹 + 懒生成**，
  PDF 失败只禁用 PDF 按钮并提示改用 Markdown，分析报告照常显示。
- **长串中文表格/段落渲染报错（#31）**：`multi_cell` 遇到无空格的长中文串抛
  `Not enough horizontal space to render a single character`。已为内容 `multi_cell`
  加 `wrapmode="CHAR"` 并复位左边距，中文按字符正确换行。
- **缺字体时优雅降级**：系统无任何中文字体时，`generate_pdf` 抛出清晰中文报错
  （指引安装字体或改用 Markdown），不再是深层 fpdf traceback。

### Tested

- Streamlit 1.50 环境用 fpdf2 2.8.4 实测：含中文标题、表格、列表、200 字无空格长串的
  报告成功生成 7 页 PDF（目视确认中文渲染无乱码、长串正确换行）；Markdown 导出正常；
  无字体路径正确抛 RuntimeError。

---

## [0.2.8] — 2026-05-30

### Fixed

- **Web UI 侧边栏收起后无法展开（#36）**：为录视频清爽化界面的自定义 CSS 把整个
  顶栏 `stHeader` 和工具栏 `stToolbar` 都 `display:none` 掉了。但 Streamlit ≥1.36 的
  「展开侧边栏」按钮 `stExpandSidebarButton` 正好嵌在工具栏内部，于是侧边栏一旦收起
  ——无论是手动点收起箭头，还是**页面缩放 / 窄屏时 Streamlit 自动收起**——展开按钮
  跟着被隐藏，再也调不出来，刷新、重启都没用。原先那行兜底的 `collapsedControl`
  选择器是旧版 DOM，在 1.45+ 已不存在，等于没写。
  修复：不再整个隐藏顶栏/工具栏，改为**保留二者、将 header 透明化、只精准隐藏
  Deploy 按钮 / 主菜单 / 状态条 / 装饰条**，侧边栏展开按钮恢复可见可点，录屏依旧干净。
  已用 Streamlit 1.50 + headless Chrome 在收起/展开两种状态下实测验证。

---

## [0.2.7] — 2026-05-19

### Fixed

- **百度 PAE 资金流下线**：`fundflow` + `fundsortlist` 接口已返回空，
  `get_fund_flow()` 全部替换为东财 push2 资金流 API（分钟级 + 日级 20 天）
- **龙虎榜机构动向**：`RPT_ORGANIZATION_BUSSINESS` 报表配置已下线，
  改用 BUY/SELL 席位明细筛选 `OPERATEDEPT_CODE="0"`（机构专用席位）
- **东财全球资讯**：新增必填参数 `req_trace`（UUID），否则返回 403

---

## [0.2.6] — 2026-05-19

### Fixed

- **依赖冲突**：`langchain-google-genai` 移至可选依赖组 `[google]`，
  消除与 mootdx 的 httpx 版本冲突。`pip install -e .` 开箱即用，
  需要 Google Gemini 时 `pip install -e ".[google]"`。
- **WebUI 模型写死 minimax**：侧边栏新增 LLM 供应商和模型选择器，
  支持 9 个供应商（MiniMax/DeepSeek/Qwen/GLM/OpenAI/Anthropic/Google/xAI/Ollama），
  默认仍为 MiniMax 但用户可自由切换。
- **阶段分析内容消失**：进度面板现在展示所有已完成阶段的报告（按时间倒序），
  不再只显示最新的一个。最新阶段自动展开，历史阶段可点击展开。

### Changed

- `.env.example` 补充 `MINIMAX_API_KEY=` 条目
- README 快速开始增加 Google 可选依赖安装说明
- README Web UI 功能列表更新

## [0.2.5] — 2026-05-17

### Breaking Changes

- **移除 akshare 依赖** — `akshare>=1.18.0` 从 `pyproject.toml` 中删除。
  所有原 akshare 调用已替换为直接 HTTP API（东财 datacenter、新浪财经、
  同花顺 10jqka、财联社 cls.cn、百度股市通）。

### Changed

- `tradingagents/dataflows/a_stock.py` 全面重构数据获取层：
  - `get_stock_data()` → 新浪 JSON K线 API + push2.eastmoney 实时行情
  - `get_stock_info()` → push2.eastmoney 个股基本信息
  - `get_stock_news()` → 东财 np-weblist 滚动新闻（已有，无变化）
  - `get_financial_data()` → 新浪财经财报三表 API
  - `get_market_news()` → 财联社 cls.cn 快讯 + 东财 np-weblist
  - `get_analyst_forecast()` → 同花顺 10jqka EPS 一致预期
  - `get_dragon_tiger_board()` → 东财 datacenter RPT_DAILYBILLBOARD
  - `get_restricted_release()` → 东财 datacenter RPT_LIFT_STAGE
  - `get_industry_overview()` → push2.eastmoney 板块行情
- 新增内部 helper：`_eastmoney_datacenter()`、`_ths_eps_forecast()`、`_sina_kline_fallback()`
- 所有函数签名和返回格式保持不变，对上层 Agent 透明

### Fixed

- 彻底消除 akshare + pandas 3.0 + pyarrow 的 `ArrowInvalid` 崩溃问题
- 消除 akshare 与 mootdx 的 httpx 版本冲突

## [0.2.4] — 2026-04-25

### Added

- **Structured-output decision agents.** Research Manager, Trader, and Portfolio
  Manager now use `llm.with_structured_output(Schema)` on their primary call
  and return typed Pydantic instances. Each provider's native structured-output
  mode is used (`json_schema` for OpenAI / xAI, `response_schema` for Gemini,
  tool-use for Anthropic, function-calling for OpenAI-compatible providers).
  Render helpers preserve the existing markdown shape so memory log, CLI
  display, and saved reports keep working unchanged. (#434)
- **LangGraph checkpoint resume** — opt-in via `--checkpoint`. State is saved
  after each node so crashed or interrupted runs resume from the last
  successful step. Per-ticker SQLite databases under
  `~/.tradingagents/cache/checkpoints/`. `--clear-checkpoints` resets them. (#594)
- **Persistent decision log** replacing the per-agent BM25 memory. Decisions
  are stored automatically at the end of `propagate()`; the next same-ticker
  run resolves prior pending entries with realised return, alpha vs SPY, and
  a one-paragraph reflection. Override path with `TRADINGAGENTS_MEMORY_LOG_PATH`.
  Optional `memory_log_max_entries` config caps resolved entries; pending
  entries are never pruned. (#578, #563, #564, #579)
- **DeepSeek, Qwen (Alibaba DashScope), GLM (Zhipu), and Azure OpenAI**
  providers, plus dynamic OpenRouter model selection.
- **Docker support** — multi-stage build with separate dev and runtime images.
- **`scripts/smoke_structured_output.py`** — diagnostic that exercises the
  three structured-output agents against any provider so contributors can
  verify their setup with one command.
- **5-tier rating scale** (Buy / Overweight / Hold / Underweight / Sell) used
  consistently by Research Manager, Portfolio Manager, signal processor, and
  the memory log; Trader keeps 3-tier (Buy / Hold / Sell) since transaction
  direction is naturally ternary.
- **Pytest fixtures** — lazy LLM client imports plus placeholder API keys so
  the test suite runs cleanly without credentials. (#588)

### Changed

- **`backend_url` default is now `None`** rather than the OpenAI URL. Each
  provider client falls back to its native default. The previous default
  leaked the OpenAI URL into non-OpenAI clients (e.g. Gemini), producing
  malformed request URLs for Python users who switched providers without
  overriding `backend_url`. The CLI flow is unaffected.
- All file I/O passes explicit `encoding="utf-8"` so Windows users no longer
  hit `UnicodeEncodeError` with the cp1252 default. (#543, #550, #576)
- Cache and log directories moved to `~/.tradingagents/` to resolve Docker
  permission issues. (#519)
- `SignalProcessor` reads the rating from the Portfolio Manager's rendered
  markdown via a deterministic heuristic — no extra LLM call.
- OpenAI structured-output calls default to `method="function_calling"` to
  avoid noisy `PydanticSerializationUnexpectedValue` warnings emitted by
  langchain-openai's Responses-API parse path. Same typed result, no warnings.

### Fixed

- Empty memory no longer triggers fabricated past-lessons in agent prompts;
  the memory-log redesign makes this structurally impossible since only the
  Portfolio Manager consults memory and only when entries exist. (#572)
- Tool-call logging processes every chunk message, not just the last one, and
  memory score normalization handles empty score arrays. (#534, #531)

### Removed

- `FinancialSituationMemory` (the per-agent BM25 system) and the dead
  `reflect_and_remember()` plumbing; subsumed by the persistent decision log.
- Hardcoded Google endpoint that caused 404 when `langchain-google-genai`
  changed its API path. (#493, #496)

### Contributors

Thanks to everyone who shaped this release through code, design, and reports:

- [@claytonbrown](https://github.com/claytonbrown) — checkpoint resume (#594), test fixtures (#588), design feedback on cost tracking (#582) and structured validation (#583)
- [@Bcardo](https://github.com/Bcardo) — memory-log redesign (#579), empty-memory hallucination report (#572), encoding fix proposal (#570)
- [@voidborne-d](https://github.com/voidborne-d) — memory persistence design (#564), portfolio manager state fix (#503)
- [@mannubaveja007](https://github.com/mannubaveja007) — structured-output feature request (#434)
- [@kelder66](https://github.com/kelder66) — RAM-only memory issue (#563)
- [@Gujiassh](https://github.com/Gujiassh) — tool-call logging fix (#534), test stub PR (#533)
- [@iuyup](https://github.com/iuyup) — memory score normalization fix (#531)
- [@kaihg](https://github.com/kaihg) — Google base_url fix (#496)
- [@32ryh98yfe](https://github.com/32ryh98yfe) — Gemini 404 report (#493)
- [@uppb](https://github.com/uppb) — OpenRouter dynamic model selection (#482)
- [@guoz14](https://github.com/guoz14) — OpenRouter limited-model report (#337)
- [@samchenku](https://github.com/samchenku) — indicator name normalization (#490)
- [@JasonOA888](https://github.com/JasonOA888) — y_finance pandas import fix (#488)
- [@tiffanychum](https://github.com/tiffanychum) — stale import cleanup (#499)
- [@zaizou](https://github.com/zaizou) — Docker permission issue (#519)
- [@Stosman123](https://github.com/Stosman123), [@mauropuga](https://github.com/mauropuga), [@hotwind2015](https://github.com/hotwind2015) — Windows encoding bug reports (#543, #550, #576)
- [@nnishad](https://github.com/nnishad), [@atharvajoshi01](https://github.com/atharvajoshi01) — encoding fix proposals (#568, #549)

## [0.2.3] — 2026-03-29

### Added

- **Multi-language output** for analyst reports and final decisions, with a
  CLI selector. Internal agent debate stays in English for reasoning quality. (#472)
- **GPT-5.4 family models** in the default catalog, with deep/quick model split.
- **Unified model catalog** as a single source of truth for CLI options and
  provider validation.

### Changed

- `base_url` is forwarded to Google and Anthropic clients so corporate proxies
  work consistently across providers. (#427)
- Standardised the Google `api_key` parameter to the unified `api_key` form.

### Fixed

- Backtesting fetchers no longer leak look-ahead data when `curr_date` is in
  the middle of a fetched window. (#475)
- Invalid indicator names from the LLM are caught at the tool boundary instead
  of crashing the run. (#429)
- yfinance news fetchers respect the same exponential-backoff retry as price
  fetchers. (#445)

### Contributors

- [@ahmedk20](https://github.com/ahmedk20) — multi-language output (#472)
- [@CadeYu](https://github.com/CadeYu) — model catalog typing (#464)
- [@javierdejesusda](https://github.com/javierdejesusda) — unified Google API key parameter (#453)
- [@voidborne-d](https://github.com/voidborne-d) — yfinance news retry (#445)
- [@kostakost2](https://github.com/kostakost2) — look-ahead bias report (#475)
- [@lu-zhengda](https://github.com/lu-zhengda) — proxy/base_url support request (#427)
- [@VamsiKrishna2021](https://github.com/VamsiKrishna2021) — invalid indicator crash report (#429)

## [0.2.2] — 2026-03-22

### Added

- **Five-tier rating scale** (Buy / Overweight / Hold / Underweight / Sell)
  introduced for the Portfolio Manager.
- **Anthropic effort level** support for Claude models.
- **OpenAI Responses API** path for native OpenAI models.

### Changed

- `risk_manager` renamed to `portfolio_manager` to match the role description
  shown in the CLI display.
- Exchange-qualified tickers (e.g. `7203.T`, `BRK.B`) preserved across all
  agent prompts and tool calls.
- Process-level UTF-8 default attempted for cross-platform consistency
  (note: this approach did not actually take effect; replaced in v0.2.4 with
  explicit per-call `encoding="utf-8"` arguments).

### Fixed

- yfinance rate-limit errors are retried with exponential backoff. (#426)
- HTTP client SSL customisation is supported for environments that need
  custom certificate bundles. (#379)
- Report-section writes handle list-of-string content gracefully.

### Contributors

- [@CadeYu](https://github.com/CadeYu) — exchange-qualified ticker preservation (#413)
- [@yang1002378395-cmyk](https://github.com/yang1002378395-cmyk) — HTTP client SSL customisation (#379)

## [0.2.1] — 2026-03-15

### Security

- Patched `langchain-core` vulnerability (LangGrinch). (#335)
- Removed `chainlit` dependency affected by CVE-2026-22218.

### Added

- `pyproject.toml` build-system configuration; the project now installs via
  modern packaging tooling.

### Removed

- `setup.py` — dependencies consolidated to `pyproject.toml`.

### Fixed

- Risk manager reads the correct fundamental report source. (#341)
- All `open()` calls receive an explicit UTF-8 encoding (initial pass).
- `get_indicators` tool handles comma-separated indicator names from the LLM. (#368)
- `Propagation` initialises every debate-state field so risk debaters never
  see missing keys.
- Stock data parsing tolerates malformed CSVs and NaN values.
- Conditional debate logic respects the configured round count. (#361)

### Contributors

- [@RinZ27](https://github.com/RinZ27) — `langchain-core` security patch (#335)
- [@Ljx-007](https://github.com/Ljx-007) — risk manager fundamental-report fix (#341)
- [@makk9](https://github.com/makk9) — debate-rounds config issue (#361)

## [0.2.0] — 2026-02-04

This is the largest release since the initial public version. The framework
moved from single-provider to a multi-provider architecture and grew several
production-ready surfaces.

### Added

- **Multi-provider LLM support** (OpenAI, Google, Anthropic, xAI, OpenRouter,
  Ollama) via a factory pattern, with provider-specific thinking configurations.
- **Alpha Vantage** integration as a configurable primary data provider, with
  yfinance as a community-stability fallback.
- **Footer statistics** in the CLI: real-time tracking of LLM calls, tool
  calls, and token usage via LangChain callbacks.
- **Post-analysis report saving** — the framework writes per-section markdown
  files (analyst reports, debate transcripts, final decision) when a run
  completes.
- **Announcements panel** — fetches updates from `api.tauric.ai/v1/announcements`
  for the CLI welcome screen.
- **Tool fallbacks** so a single vendor outage does not stop the pipeline.

### Changed

- Risky / Safe risk debaters renamed to **Aggressive / Conservative** for
  consistency with the displayed agent labels.
- Default data vendor switched to balance reliability and quota across
  community deployments.
- Ollama and OpenRouter model lists updated; default endpoints clarified.

### Fixed

- Analyst status tracking and message deduplication in the live display.
- Infinite-loop guard in the agent loop; reflection and logging hardened.
- Various data-vendor implementation bugs and tool-signature mismatches.

### Contributors

This release is the first with substantial outside contributions; many community
PRs from late 2025 also landed here.

- [@luohy15](https://github.com/luohy15) — Alpha Vantage data-vendor integration (#235)
- [@EdwardoSunny](https://github.com/EdwardoSunny) — yfinance fetching optimisations (#245)
- [@Mirza-Samad-Ahmed-Baig](https://github.com/Mirza-Samad-Ahmed-Baig) — infinite-loop guard, reflection, and logging fixes (#89)
- [@ZeroAct](https://github.com/ZeroAct) — saved results path support (#29)
- [@Zhongyi-Lu](https://github.com/Zhongyi-Lu) — `.env` gitignore (#49)
- [@csoboy](https://github.com/csoboy) — local Ollama setup (#53)
- [@chauhang](https://github.com/chauhang) — initial Docker support attempt (#47, later reverted; the merged Docker support shipped in v0.2.4)

## [0.1.1] — 2025-06-07

### Removed

- Static site assets that had been bundled with v0.1.0; the public site now
  lives separately.

## [0.1.0] — 2025-06-05

### Added

- **Initial public release** of the TradingAgents multi-agent trading
  framework: market / sentiment / news / fundamentals analysts; bull and bear
  researchers; trader; aggressive, conservative, and neutral risk debaters;
  portfolio manager. LangGraph orchestration, yfinance data, per-agent
  BM25 memory, single-provider OpenAI integration, interactive CLI.

[0.2.4]: https://github.com/TauricResearch/TradingAgents/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/TauricResearch/TradingAgents/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/TauricResearch/TradingAgents/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/TauricResearch/TradingAgents/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/TauricResearch/TradingAgents/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/TauricResearch/TradingAgents/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/TauricResearch/TradingAgents/releases/tag/v0.1.0
