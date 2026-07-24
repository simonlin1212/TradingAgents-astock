# Changes from Upstream TradingAgents

本文件记录本 Fork 相对于 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) 上游 commit `7e9e7b8`（2026-05-04）的所有改动。

---

## Week 1 — 数据层 A 股落地

### 新增文件

| 文件 | 说明 |
|------|------|
| `tradingagents/dataflows/a_stock.py` | A 股数据 vendor，~400 行，9 个接口方法 |
| `test_astock.py` | E2E 集成测试脚本 |
| `.env` | 环境变量模板（已加入 .gitignore） |

### 修改文件

| 文件 | 改动 |
|------|------|
| `tradingagents/dataflows/interface.py` | 注册 `a_stock` vendor，9 个方法路由到 `a_stock.py` |
| `tradingagents/default_config.py` | `data_vendors` 全部默认改为 `"a_stock"`；新增 `output_language` 配置项 |

### 数据源架构

| 来源 | 协议 | 数据内容 |
|------|------|---------|
| mootdx | TCP 7709 | OHLCV K 线、财务快照、F10 文本 |
| 腾讯财经 | HTTP (`qt.gtimg.cn`) | PE / PB / 市值 / 换手率 |
| akshare | Python 库 | 新闻、财报三表（sina 源）、股票信息 |

### 踩坑记录

- mootdx `datetime` 列冲突：需先 `drop` 再 `reset_index`
- akshare eastmoney 财报接口崩溃：改用 sina 源
- Kimi API 用 `ANTHROPIC_AUTH_TOKEN`（Bearer），非 `ANTHROPIC_API_KEY`

---

## Week 2 — Agent 特化与新角色

### P0：中文输出切换

| 文件 | 改动 |
|------|------|
| `tradingagents/default_config.py` | 新增 `output_language: "Chinese"` |
| `tradingagents/agents/utils/agent_utils.py` | 新增 `get_language_instruction()` 函数 |

当 `output_language` 为 `"Chinese"` 时，所有用户面向的 Agent 输出中文报告；Bull/Bear 辩论和三方风险辩论保持英文（推理质量 > 输出语言一致性）。

### P1：4 个原版 Analyst A 股中文化

| 文件 | 改动 |
|------|------|
| `tradingagents/agents/analysts/market_analyst.py` | prompt 加入 A 股技术分析上下文 + 中文指令 |
| `tradingagents/agents/analysts/social_media_analyst.py` | prompt 改为 A 股舆情分析 + 中文指令 |
| `tradingagents/agents/analysts/news_analyst.py` | prompt 加入 A 股新闻解读 + 中文指令 |
| `tradingagents/agents/analysts/fundamentals_analyst.py` | prompt 加入 A 股财报分析 + 中文指令 |

### P2：3 个 A 股特化角色（新增）

每个新角色需修改 6 个文件（analyst 本体 + agent_states + __init__ + conditional_logic + trading_graph + setup）。

| 新文件 | 角色 | 职责 |
|--------|------|------|
| `tradingagents/agents/analysts/policy_analyst.py` | 政策分析师 | 监管政策、产业政策、窗口指导 |
| `tradingagents/agents/analysts/hot_money_tracker.py` | 游资追踪师 | 龙虎榜、大单流向、主力资金动态 |
| `tradingagents/agents/analysts/lockup_watcher.py` | 解禁监控师 | 限售股解禁、大股东减持、股权质押 |

配套修改：

| 文件 | 改动 |
|------|------|
| `tradingagents/agents/utils/agent_states.py` | `AgentState` 新增 `policy_report` / `hot_money_report` / `lockup_report` 字段 |
| `tradingagents/agents/__init__.py` | 导出 3 个新的 `create_*` 工厂函数 |
| `tradingagents/graph/conditional_logic.py` | 新增 3 个 analyst 的 tool call 路由函数 |
| `tradingagents/graph/trading_graph.py` | 将 3 个新 analyst 加入默认 analyst 列表 |
| `tradingagents/graph/setup.py` | 为 3 个新 analyst 创建节点、工具节点、边和条件路由 |

### P3：下游 Agent 接入 3 个新报告

**问题**：原版的 Bull/Bear Researcher 和 3 个 Risk Debater 只读 4 个 report 字段，新增的 policy/hot_money/lockup 不会自动流入辩论。

**修复**：5 个文件手动添加 `state.get("policy_report", "")` 等读取 + prompt 注入：

| 文件 | 改动 |
|------|------|
| `tradingagents/agents/researchers/bull_researcher.py` | 读取 3 个新报告 + 注入 prompt 的 Resources 段 |
| `tradingagents/agents/researchers/bear_researcher.py` | 同上 |
| `tradingagents/agents/risk_mgmt/aggressive_debator.py` | 读取 3 个新报告 + 注入 prompt |
| `tradingagents/agents/risk_mgmt/conservative_debator.py` | 同上 |
| `tradingagents/agents/risk_mgmt/neutral_debator.py` | 同上 |

### P3-C：Portfolio Manager A 股约束

| 文件 | 改动 |
|------|------|
| `tradingagents/agents/managers/portfolio_manager.py` | prompt 新增 A-Stock Trading Constraints 块：T+1 / 涨跌停 / 手数 / 交易时段 / ST / 融资融券 |

---

## Week 2.5 — 间隙修补

| 文件 | 改动 | 分类 |
|------|------|------|
| `tradingagents/graph/propagation.py` | `create_initial_state()` 新增 3 个缺失字段初始化 | 关键 Bug 修复 |
| `tradingagents/agents/trader/trader.py` | 完全重写为 A 股特化 — 读取 3 个新报告 + T+1/涨跌停约束 | 功能增强 |
| `tradingagents/graph/reflection.py` | Alpha 基准从 `SPY` 改为 `CSI 300（沪深300）` | A 股适配 |
| `tradingagents/agents/managers/research_manager.py` | prompt 加入 A 股分析维度提示 | A 股适配 |

---

## 改动文件汇总

共计 **22 个文件**改动（Week 1 + Week 2 + Week 2.5）：

### 新增（4 个）
- `tradingagents/dataflows/a_stock.py`
- `tradingagents/agents/analysts/policy_analyst.py`
- `tradingagents/agents/analysts/hot_money_tracker.py`
- `tradingagents/agents/analysts/lockup_watcher.py`

### 修改（18 个）
- `tradingagents/dataflows/interface.py`
- `tradingagents/default_config.py`
- `tradingagents/agents/analysts/market_analyst.py`
- `tradingagents/agents/analysts/social_media_analyst.py`
- `tradingagents/agents/analysts/news_analyst.py`
- `tradingagents/agents/analysts/fundamentals_analyst.py`
- `tradingagents/agents/utils/agent_states.py`
- `tradingagents/agents/__init__.py`
- `tradingagents/graph/conditional_logic.py`
- `tradingagents/graph/trading_graph.py`
- `tradingagents/graph/setup.py`
- `tradingagents/graph/propagation.py`
- `tradingagents/graph/reflection.py`
- `tradingagents/agents/researchers/bull_researcher.py`
- `tradingagents/agents/researchers/bear_researcher.py`
- `tradingagents/agents/risk_mgmt/aggressive_debator.py`
- `tradingagents/agents/risk_mgmt/conservative_debator.py`
- `tradingagents/agents/risk_mgmt/neutral_debator.py`
- `tradingagents/agents/managers/portfolio_manager.py`
- `tradingagents/agents/managers/research_manager.py`
- `tradingagents/agents/trader/trader.py`

### 设计决策

1. **辩论层保持英文**：Bull/Bear 辩论和三方风险辩论使用英文，因为 LLM 的英文推理能力更强。只有用户面向的报告和最终决策输出中文。

2. **`state.get()` 模式**：所有新增 report 字段使用 `state.get("field", "")` 而非 `state["field"]`，确保在部分 Analyst 被跳过时不会 KeyError。

3. **6 文件管线**：新增任何 Analyst 需同时修改 6 个文件（analyst 本体 + agent_states + __init__ + conditional_logic + trading_graph + setup），漏改任何一个都会导致该 Analyst 不被执行或数据不流通。

4. **数据源选择**：拒绝 Tushare（积分墙限制新用户）、不用 MongoDB/Redis（增加部署复杂度），使用 mootdx + 腾讯财经 + akshare 三个完全免费无门槛的数据源。

---

## Week 3.5 — 信号层 + SKILL V2 数据升级（2026-05-11）

### 新增文件

| 文件 | 说明 |
|------|------|
| `tradingagents/agents/utils/signal_data_tools.py` | 信号层 5 个 `@tool` 包装（get_profit_forecast / get_hot_stocks / get_northbound_flow / get_concept_blocks / get_fund_flow） |

### 修改文件

| 文件 | 改动 |
|------|------|
| `tradingagents/dataflows/a_stock.py` | 735→1277 行：增强 `get_fundamentals()` 内联一致预期EPS + forward PE/PEG；新增 5 个方法：`get_profit_forecast()` / `get_hot_stocks()` / `get_northbound_flow()` / `get_concept_blocks()` / `get_fund_flow()`；修复 ResultCode str/int 类型比较 bug |
| `tradingagents/dataflows/interface.py` | 导入 5 个新 a_stock 函数；新增 `signal_data` 类别到 `TOOLS_CATEGORIES`；5 个新 entry 到 `VENDOR_METHODS` |
| `tradingagents/default_config.py` | `data_vendors` 新增 `signal_data: "a_stock"` |
| `tradingagents/agents/utils/agent_utils.py` | re-export 5 个新工具（get_profit_forecast / get_hot_stocks / get_northbound_flow / get_concept_blocks / get_fund_flow） |
| `tradingagents/agents/analysts/hot_money_tracker.py` | tools 列表加 `get_hot_stocks` + `get_northbound_flow` + `get_concept_blocks` + `get_fund_flow`；prompt 新增工具说明和分析步骤 4-6 |
| `tradingagents/agents/analysts/fundamentals_analyst.py` | tools 列表加 `get_profit_forecast`；prompt 新增估值工具说明 |

### 新增数据源

| 来源 | 协议 | 数据内容 |
|------|------|---------|
| 同花顺热点 | HTTP (`zx.10jqka.com.cn`) | 当日强势股 + 题材归因 reason tags（零鉴权，73ms） |
| 同花顺 hsgtApi | HTTP (`data.hexin.cn`) | 北向资金分钟级实时流向 + 历史日级（零鉴权） |
| akshare 同花顺 | Python 库 | `stock_profit_forecast_ths` 机构一致预期 EPS |
| 百度股市通 PAE | HTTP (`finance.pae.baidu.com`) | 概念板块/行业/地域 + 个股资金流向（零鉴权） |

---

## Week 4 — 辩论层 A 股特化（2026-05-12）

### 修改文件

| 文件 | 改动 |
|------|------|
| `tradingagents/agents/researchers/bull_researcher.py` | prompt 注入 A-Share Bull Framework：政策顺风、北向确认、游资接力、PE 消化叙事、解禁出清 |
| `tradingagents/agents/researchers/bear_researcher.py` | prompt 注入 A-Share Bear Framework：政策反转、解禁压力、游资撤退、T+1 锁仓、估值泡沫、北向撤退 |
| `tradingagents/agents/risk_mgmt/aggressive_debator.py` | prompt 注入 A-Share Aggressive Framework：涨停动量、政策底、PE 扩张、散户放大、游资确认 |
| `tradingagents/agents/risk_mgmt/conservative_debator.py` | prompt 注入 A-Share Conservative Framework：T+1 不可逃逸、跌停陷阱、解禁悬顶、政策反转、ST/退市 |
| `tradingagents/agents/risk_mgmt/neutral_debator.py` | prompt 注入 A-Share Neutral Framework：T+1 双刃剑、政策分级、估值区间、轮动周期、仓位优先 |

### 设计决策

5. **辩论层保持英文但注入 A 股框架**：prompt 语言维持英文（推理质量），但论据框架从美股通用替换为 A 股特有机制（T+1/涨跌停/政策市/游资/北向/解禁）。同一机制在三方风控中呈现对立观点。

---

## Week 5 — 数据质量门控实测（2026-05-12）

### 修改文件

| 文件 | 改动 |
|------|------|
| `tradingagents/dataflows/a_stock.py` | **get_northbound_flow 重写**：删除不可用的 hsgtData 历史 API（返回 2024 年旧数据），改为实时数据 + 本地 CSV 自缓存（`northbound_daily.csv`）+ 趋势对比（today vs N-day avg）。新增 3 个私有函数：`_northbound_cache_path` / `_save_northbound_snapshot` / `_load_northbound_history`。**get_insider_transactions 截断**：F10 股东研究【4.股东变化】只保留最新一期（-70% token，19969→5906 chars） |

### 新增文件

| 文件 | 说明 |
|------|------|
| `test_data_quality.py` | 14 接口数据质量回归测试脚本（000858 五粮液） |

### 根因记录

eastmoney 全系北向资金接口（含 akshare `stock_hsgt_hist_em`、datacenter API、push2his kamt.kline）自 2024-08-16 后净买额字段全部返回 NaN/None/0。同花顺 `hsgtData` chart 数据也是 2024 年旧缓存。属上游行业性数据断供。解决方案：自建本地缓存。

### 设计决策

6. **北向资金历史自缓存**：上游 API 全面断供后，采用"实时快照 + 本地 CSV 累积"模式。缺点是新用户首次无历史，但零外部依赖、数据越跑越丰富，且避免了依赖随时可能变的第三方历史 API。

---

---

## Week 5.5 — 数据质量门控 + 数据缺口补齐（2026-05-12）

### P0：数据质量门控架构

**新增文件**

| 文件 | 说明 |
|------|------|
| `tradingagents/agents/quality_gate.py` | 两层数据质量验证节点：Layer 1 硬检查（长度/失败标记/必采清单/表格）→ ABCDF 分级；Layer 2 LLM 复审（4+ 报告硬检查失败时跳过） |

**修改文件**

| 文件 | 改动 |
|------|------|
| `tradingagents/agents/utils/agent_states.py` | `AgentState` 新增 `data_quality_summary` 字段 |
| `tradingagents/agents/__init__.py` | 导出 `create_quality_gate` |
| `tradingagents/graph/setup.py` | 新增 "Quality Gate" 节点，接线：最后一个 analyst Msg Clear → Quality Gate → Bull Researcher |
| 7 个 analyst 文件 | 每个 prompt 末尾新增 📋 必采清单（market 5 项 / social 5 项 / news 5 项 / fundamentals 7 项 / policy 5 项 / hot_money 6 项 / lockup 5 项） |
| `tradingagents/agents/researchers/bull_researcher.py` | 读取 `data_quality_summary` + prompt 注入质量警告 |
| `tradingagents/agents/researchers/bear_researcher.py` | 同上 |

### P1：3 个数据缺口补齐

**新增 a_stock.py 方法**（14→17）

| 方法 | 数据源 | 内容 |
|------|--------|------|
| `get_dragon_tiger_board(ticker, trade_date)` | akshare `stock_lhb_detail_em` + `stock_lhb_stock_detail_em` + `stock_lhb_jgmmtj_em` | 龙虎榜上榜记录 + 买卖席位明细 + 机构参与 |
| `get_lockup_expiry(ticker, trade_date)` | akshare `stock_restricted_release_queue_em` + `stock_restricted_release_detail_em` | 限售解禁日历（历史 + 未来 90 天） |
| `get_industry_comparison(ticker, trade_date)` | akshare `stock_board_industry_summary_ths()` | 全行业横向对比（90 个行业涨跌幅/成交额/净流入排名） |

**修改文件**

| 文件 | 改动 |
|------|------|
| `tradingagents/dataflows/interface.py` | 导入 3 个新方法 + 注册到 `TOOLS_CATEGORIES` 和 `VENDOR_METHODS` |
| `tradingagents/agents/utils/signal_data_tools.py` | 新增 3 个 `@tool` 包装 |
| `tradingagents/agents/utils/agent_utils.py` | re-export 3 个新工具 |
| `tradingagents/agents/analysts/hot_money_tracker.py` | tools 列表加 `get_dragon_tiger_board` + `get_industry_comparison`；prompt 新增工具说明 |
| `tradingagents/agents/analysts/lockup_watcher.py` | tools 列表加 `get_lockup_expiry`；prompt 新增工具说明 |
| `tradingagents/agents/analysts/fundamentals_analyst.py` | tools 列表加 `get_industry_comparison`；prompt 新增工具说明 |

### 关键 Bug 修复：ToolNode 工具缺失

**`tradingagents/graph/trading_graph.py`**：`_create_tool_nodes()` 的 ToolNode 定义只包含基础工具（get_stock_data / get_news 等），缺少信号层工具（get_hot_stocks / get_northbound_flow / get_concept_blocks / get_fund_flow / get_profit_forecast / get_dragon_tiger_board / get_lockup_expiry / get_industry_comparison）。导致 analyst 的 `llm.bind_tools()` 引用的工具在 ToolNode 执行时找不到，任何信号工具调用都会运行时失败。

修复：为 fundamentals / hot_money / lockup 三个 ToolNode 补全所有信号工具的导入和注册。

### P2：边界测试结果

| 股票 | 类型 | OK | WARN | FAIL | 备注 |
|------|------|----|----|------|------|
| 600696 *ST岩石 | ST（退市中） | 16 | 1 | 0 | WARN: profit_forecast 无分析师覆盖（预期行为） |
| 688981 中芯国际 | 科创板 688 | 17 | 0 | 0 | 20% 涨跌停正确识别 |
| 002475 立讯精密 | 中小板 002 | 17 | 0 | 0 | 全部数据正常 |

### 设计决策

7. **单一质量门控节点**：选择在所有 analyst 完成后设一个质量门（Option B），而非每个 analyst 后各设一个（Option A）。理由：更简单（1 个节点 vs 7 个）、所有报告可一次性评估、质量摘要可被 researcher 整体消费。

8. **两层验证**：Layer 1 硬检查（代码逻辑）覆盖明确的失败模式（空报告、太短、失败标记、缺项过多）；Layer 2 LLM 复审捕获硬检查漏掉的语义问题。当 4+ 报告硬检查失败时跳过 LLM 复审（省 token）。

---

## Week 6：MiniMax 集成 + E2E 实战验证（2026-05-12）

### MiniMax LLM 供应商集成

**目的：** 接入国内直连、OpenAI 兼容的 MiniMax 作为推荐 LLM 供应商。TradingAgents 每次分析需 30-50 次 API 调用，Claude/ChatGPT 订阅版无法使用。

**新增/修改文件：**

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `tradingagents/llm_clients/factory.py` | 修改 | `_OPENAI_COMPATIBLE` tuple 增加 `"minimax"` |
| `tradingagents/llm_clients/openai_client.py` | 修改 | `_PROVIDER_CONFIG` 增加 MiniMax base_url + env var |
| `tradingagents/llm_clients/model_catalog.py` | 修改 | 新增 `"minimax"` 模型目录（M2.7/M2.5 + highspeed） |
| `README.md` | 修改 | 重写 LLM 配置章节：7 供应商 + 3 套示例 |
| `examples/run_cases.py` | 修改 | 默认改为 MiniMax-M2.7 / M2.7-highspeed |

**技术要点：** MiniMax 走 `provider="minimax"` 而非 `provider="openai"`，因为 OpenAI 路径启用 `use_responses_api=True`（指向 `/v1/responses`），MiniMax 不实现该端点。

### E2E 实战结果

| 样本 | 板块 | 耗时 | 说明 |
|------|------|------|------|
| 样本 A | 创业板 | 977s (16.3 min) | 7 analyst 全通过，解禁评估 10 章完整报告结构正常 |
| 样本 B | 主板 | 890s (14.8 min) | 销量/北向资金字段解析正常，极端值处理正常 |

全链路：7 Analysts → Quality Gate → Bull/Bear Debate → Trader → Risk Panel → PM ✅

### 设计决策

9. **MiniMax 作为推荐供应商**：国内直连零代理、OpenAI 兼容、M2.7 旗舰 + highspeed 双模型配置、价格合理。相比 DeepSeek（高峰限流）、OpenAI（需代理 + 成本高）、Kimi（需额外 backend_url），MiniMax 综合体验最优。

---

---

## Week 7：Web UI — Streamlit 可视化界面（2026-05-12）

**目的：** 提供浏览器操作界面，让不写代码的用户也能用。输入股票代码 → 一键分析 → 实时进度 → 查看报告 → PDF 下载。同时提升 GitHub 仓库的视觉吸引力。

**新增文件（12 个）：**

| 文件 | 说明 |
|------|------|
| `web/app.py` | Streamlit 主入口：暗色 CSS 主题、5 态状态机 |
| `web/runner.py` | 后台线程运行分析、流式检测 12 阶段完成 |
| `web/progress.py` | 线程安全 ProgressTracker，12 阶段定义 |
| `web/history.py` | 扫描 `~/.tradingagents/logs/` 历史 JSON |
| `web/pdf_export.py` | fpdf2 PDF 报告生成（CJK 字体自检测） |
| `web/launch.py` | CLI 启动器（`tradingagents-web` 命令） |
| `web/components/sidebar.py` | 侧边栏：Logo + 股票输入 + 历史列表 |
| `web/components/progress_panel.py` | 实时进度面板 + 彩色状态徽章 |
| `web/components/report_viewer.py` | 信号卡片 + 7 报告 + 辩论 Tabs + PDF 下载 |
| `web/__init__.py` | 包标记 |
| `web/components/__init__.py` | 包标记 |
| `.streamlit/config.toml` | Streamlit 暗色主题配置 |

**修改文件：**

| 文件 | 说明 |
|------|------|
| `pyproject.toml` | 新增 streamlit/fpdf2/python-dotenv 依赖 + tradingagents-web 脚本 |
| `README.md` | 新增 Web UI 章节 + 项目结构更新 |
| `assets/web-ui-welcome.png` | 欢迎页截图 |

### 设计决策

10. **Streamlit 而非 Gradio/自研前端**：Python 生态内闭环，无需 Node.js/npm；分析任务 15 分钟长跑，Streamlit 的 session_state + rerun 轮询模式天然适配；新手友好 `pip install -e . && tradingagents-web` 即用。

---

### 改动文件汇总（累计）

Week 1-7 共 **47 个文件**受影响（含 22 原有修改 + 22 新增 + 3 配置）：

**tradingagents/ 核心改动（22 原有 + 9 新增）：**
- `tradingagents/dataflows/a_stock.py` (新增)
- `tradingagents/dataflows/interface.py`
- `tradingagents/default_config.py`
- `tradingagents/agents/quality_gate.py` (新增 — Week 5.5)
- `tradingagents/agents/utils/agent_utils.py`
- `tradingagents/agents/utils/signal_data_tools.py` (新增)
- `tradingagents/agents/utils/agent_states.py`
- `tradingagents/agents/__init__.py`
- `tradingagents/agents/analysts/market_analyst.py`
- `tradingagents/agents/analysts/fundamentals_analyst.py`
- `tradingagents/agents/analysts/news_analyst.py`
- `tradingagents/agents/analysts/social_media_analyst.py`
- `tradingagents/agents/analysts/policy_analyst.py` (新增)
- `tradingagents/agents/analysts/hot_money_tracker.py` (新增)
- `tradingagents/agents/analysts/lockup_watcher.py` (新增)
- `tradingagents/agents/conditional_logic.py`
- `tradingagents/graph/trading_graph.py`
- `tradingagents/graph/setup.py`
- `tradingagents/agents/researchers/bull_researcher.py`
- `tradingagents/agents/researchers/bear_researcher.py`
- `tradingagents/agents/risk_mgmt/aggressive_debator.py`
- `tradingagents/agents/risk_mgmt/conservative_debator.py`
- `tradingagents/agents/risk_mgmt/neutral_debator.py`
- `tradingagents/agents/managers/portfolio_manager.py`
- `tradingagents/agents/managers/research_manager.py`
- `tradingagents/agents/trader/trader.py`
- `tradingagents/llm_clients/factory.py` (Week 6)
- `tradingagents/llm_clients/openai_client.py` (Week 6)
- `tradingagents/llm_clients/model_catalog.py` (Week 6)

**Web UI（12 新增 — Week 7）：**
- `web/app.py`, `web/runner.py`, `web/progress.py`, `web/history.py`
- `web/pdf_export.py`, `web/launch.py`
- `web/components/sidebar.py`, `web/components/progress_panel.py`, `web/components/report_viewer.py`
- `web/__init__.py`, `web/components/__init__.py`
- `.streamlit/config.toml`

**项目文件：**
- `README.md`, `examples/run_cases.py`, `pyproject.toml`, `assets/web-ui-welcome.png`
