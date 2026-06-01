# Changelog

All notable changes to TradingAgents are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Breaking changes within the 0.x line are called out explicitly.

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
