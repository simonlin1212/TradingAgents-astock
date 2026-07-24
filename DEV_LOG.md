# TradingAgents-Astock 开发者日志

> 基于 TauricResearch/TradingAgents 的 A 股深度特化 fork
>
> Fork 点:`7e9e7b8` (feat: DeepSeek V4 thinking-mode round-trip via DeepSeekChatOpenAI subclass)
> Fork 时间:2026-05-04
> 上游许可:Apache License 2.0
> 本项目许可:Apache License 2.0(继承上游,完全开源,不做商业闭源)

---

## 项目定位

**这不是又一个中文翻译版 fork。**

定位:**A 股市场深度特化的多 Agent 投研框架** — 行业级、轻量、可商用、配套教学。

目标受众:
- 独立投资研究者
- 中小型私募/券商研究所
- AI Agent 工程从业者
- 想学多 Agent 架构的开发者

差异化锚点(vs 已有方案):

| 对比对象 | 我们的差异 |
|---|---|
| **TauricResearch 原版** | 加 A 股全栈数据源 + Agent 中文化 + A 股交易制度适配 + A 股特化新角色 |
| **hsliuping/TradingAgents-CN** | 全 Apache 2.0 开源(对方混合商业闭源)、轻量化部署(无需 MongoDB/Redis)、数据源用 mootdx 不封 IP(对方 Tushare 积分墙)、A 股特化深度更深(政策/游资/解禁) |
| **微软 Qlib** | LLM 推理范式,补齐 Qlib 的"语义理解"能力,而非替代其因子工程 |

---

## 决策与选型记录

### 决策一:在原版上 fork,不在 CN 版上 fork

**Why**:CN 版的 `app/` (FastAPI) + `frontend/` (Vue) 是商业闭源,我们要做完全 Apache 2.0 开源,基础必须干净。

**How to apply**:从 TauricResearch 原版直接 fork,CN 版作为 `tradingagents/` 部分(Apache 2.0)的"借鉴学习对象",而不是直接合并代码。

### 决策二:数据层用 EP11 的 a-stock-data 组合,不用 Tushare

**Why**:Tushare 核心接口要 2000 积分,免费数据残废;AKShare 高频调用易封 IP。EP11 已经实测验证 mootdx (TCP 不封 IP) + 腾讯财经 (HTTP 公开 API) + akshare (低频研报/新闻) + iwencai (NL 搜索) 这套组合是免费稳定的最优解。

**How to apply**:新建 `tradingagents/dataflows/a_stock.py`,把 EP11 的 Skill 包装成 vendor;保留原版 `interface.py` 的 `route_to_vendor()` dispatch 模式不动。(最终选择了与 `y_finance.py` 同级的扁平结构,而非嵌套目录。)

### 决策三:不引入 MongoDB/Redis

**Why**:CN 版的 git log 反复出现"MongoDB 迁移脚本""数据库隔离"等 fix,数据库依赖是累赘。我们要的是 `pip install + python main.py` 直接能跑。

**How to apply**:配置走环境变量 + JSON;缓存走本地 SQLite 或 CSV;部署 Dockerfile 保持单容器。

### 决策四:A 股特化角色是核心差异化

**Why**:CN 版只做了基础翻译 + 数据源切换,没有 A 股市场特性的 Agent 角色。A 股是政策市,有龙虎榜、解禁/减持等独特信号,这些值得专门角色。

**How to apply**:在原版 4 个分析师之外新增三个 A 股特化角色:
- 政策分析师 (Policy Analyst)
- 游资追踪员 (Hot Money Tracker)
- 解禁/减持监控 (Lock-up Watcher)

### 决策五:T+1 / 涨跌停 / ST / 停牌等交易制度,在风控管理器层落地

**Why**:这些是 A 股交易的硬约束,Agent 的最终建议必须符合这些规则才有可执行性。CN 版未做这层适配。

**How to apply**:在 `tradingagents/agents/managers/risk_manager.py` 增加 A 股交易规则约束;Agent 输出建议时必须检验是否落在合法操作空间。

---

## 改造路线图(三周)

### Week 1 — 数据层落地(2026-05-04 ~ 2026-05-04) ✅ 已完成

**目标:让 TradingAgents 能用 EP11 数据源拉到 A 股真实数据。**

- [x] 新建 `tradingagents/dataflows/a_stock.py`(~400 行),实现 9 个 vendor 方法:
  - `get_stock_data` → mootdx OHLCV (TCP 7709,带 CSV 缓存)
  - `get_indicators` → mootdx OHLCV + stockstats 计算 13 种技术指标
  - `get_fundamentals` → 腾讯财经 PE/PB/市值 + mootdx finance 季报快照 + akshare 个股基本面
  - `get_balance_sheet` → akshare sina 资产负债表
  - `get_cashflow` → akshare sina 现金流量表
  - `get_income_statement` → akshare sina 利润表
  - `get_news` → akshare stock_news_em(东财个股新闻)
  - `get_global_news` → akshare 财联社快讯 + 东财全球资讯
  - `get_insider_transactions` → mootdx F10 股东研究
- [x] 改 `tradingagents/dataflows/interface.py`:注册 `a_stock` 到 `VENDOR_LIST` + 全部 9 个 `VENDOR_METHODS`
- [x] 改 `tradingagents/default_config.py`:四个 `data_vendors` 类别默认切到 `a_stock`
- [x] ticker 格式处理:内置 `_normalize_ticker()` 支持纯代码/SH前缀/.SH后缀三种写法
- [x] 单元测试:688017(绿的谐波)9/9 方法全部通过
- [x] **里程碑**:端到端跑通 `python test_astock.py` — 7 个 Agent 完成完整辩论,输出 HOLD 决策

**实际数据源映射(vs 原版 yfinance):**

| 方法 | 原版 yfinance | A 股版 a_stock |
|---|---|---|
| get_stock_data | Yahoo Finance | mootdx TCP K 线 |
| get_indicators | stockstats + yfinance | stockstats + mootdx |
| get_fundamentals | yf.Ticker.info | 腾讯财经 + mootdx finance + akshare |
| get_balance_sheet | yf.balance_sheet | akshare sina 资产负债表 |
| get_cashflow | yf.cashflow | akshare sina 现金流量表 |
| get_income_statement | yf.income_stmt | akshare sina 利润表 |
| get_news | yf.get_news | akshare stock_news_em |
| get_global_news | yf.Search | akshare 财联社 + 东财全球 |
| get_insider_transactions | yf.insider_transactions | mootdx F10 股东研究 |

**踩坑记录:**
- mootdx `bars()` 返回 DataFrame 的 `datetime` 同时存在于 index 和 column,需先 `drop(columns=["datetime"])` 再 `reset_index()`
- akshare `stock_balance_sheet_by_report_em()` 在 v1.18.54 内部 HTML 解析崩溃(东财页面变动),改用 `stock_financial_report_sina()` 绕过
- Kimi API 鉴权用 `ANTHROPIC_AUTH_TOKEN` 而非 `ANTHROPIC_API_KEY`(Bearer vs X-Api-Key)

### Week 2 — Agent 中文化 + A 股特化角色(2026-05-04) ✅ 全部完成

**目标:让 Agent 真的理解 A 股市场。**

**P0 — 输出语言切换(1 行改动):**
- [x] `default_config.py` 设 `output_language: "Chinese"` — 框架自带 `get_language_instruction()` 钩子,零成本让所有 analyst 输出中文

**P1 — 四个现有 analyst prompt 中文化 + A 股特化:**
- [x] 改写 `market_analyst.py`:全中文 prompt + 涨跌停/T+1/北向资金/换手率/量价关系
- [x] 改写 `fundamentals_analyst.py`:全中文 + CAS 准则/A 股 PE 常态(30-50x)/扣非净利润/财报披露节奏 + 修复原版 trailing comma tuple bug
- [x] 改写 `news_analyst.py`:全中文 + 政策市框架/消息来源权重/行业轮动/事件驱动
- [x] 改写 `social_media_analyst.py`:重定位为「市场情绪分析师」+ 散户情绪/股吧雪球/反向指标/情绪评分体系

**P2 — 新增 2 个 A 股特化角色(六文件管道联动):**
- [x] **新增** `policy_analyst.py`(政策分析师)— 五层政策框架(宏观/监管/产业/地方/国际) + 力度级别评估 + 影响时间窗口
- [x] **新增** `hot_money_tracker.py`(游资/龙虎榜追踪)— 量价异动/连板分析/资金博弈格局判断
- [x] 管道接入:agent_states + __init__ + conditional_logic + trading_graph + setup 五文件联动
- [x] 默认 selected_analysts 从 4 个扩展到 6 个
- [x] **里程碑**:688017 E2E 验证通过 — 6 analyst 中文辩论,Kimi 2.6 驱动,SELL(Underweight)

**P3 — 第 7 角色 + 下游 agent 补报告 + PM A 股约束:**
- [x] **新增** `lockup_watcher.py`(解禁/减持监控)— 限售股类型/解禁规模评估/减持新规约束/减持预披露/减持动力评估
- [x] 六文件管道联动:agent_states + __init__ + conditional_logic + trading_graph + setup + lockup_watcher 本体
- [x] 默认 selected_analysts 从 6 个扩展到 7 个
- [x] **下游 agent 补报告字段**(修复原版设计缺陷):bull_researcher + bear_researcher + aggressive/conservative/neutral_debator 全部读取 policy_report、hot_money_report、lockup_report 并注入 prompt
- [x] **Portfolio Manager A 股交易约束**:T+1 settlement、涨跌停(主板±10%/科创创业板±20%/ST±5%)、最小交易手数、交易时段、ST/退市风险、融资融券提示
- [x] **里程碑**:688017 E2E 验证通过 — 7 analyst 全流程中文辩论,最终 **Underweight**(减持 25-33%)

**设计决策:辩论层保持英文**
- bull/bear researcher + aggressive/conservative/neutral debator 的 prompt 保持英文,不做中文化
- 原因:内部推理质量 > 输出语言一致性;只有面向用户的 analyst 报告和 PM 最终决策走中文

**E2E 对比(688017 绿的谐波):**

| 对比项 | Week 1(数据层) | Week 2 P2(6 analyst) | Week 2 P3(7 analyst) |
|--------|----------------|---------------------|---------------------|
| Analyst 数量 | 4(英文) | 6(中文 + 2 A 股特化) | 7(中文 + 3 A 股特化) |
| 输出语言 | English | Chinese | Chinese |
| 下游报告覆盖 | 4 字段 | 4 字段(gap!) | **7 字段(修复)** |
| PM A 股约束 | 无 | 无 | **T+1/涨跌停/ST** |
| 最终决策 | HOLD | SELL (Underweight) | **Underweight**(减持 25-33%) |
| 报告总行数 | ~600 | ~2000 | ~2100 |

**改判演进**:
- Week 1 → Week 2 P2:游资追踪发现 4月23日天量长阴 + 股东户数激增 81% + 先进制造基金大减持,叠加 250x+ PE 估值风险 → HOLD 改 SELL
- Week 2 P2 → P3:解禁监控发现控股股东 5-7 月减持窗口 + 300x PE 历史高位 + 经营现金流恶化 → 保持 Underweight + 给出具体减仓比例(25-33%)和价位(220-225 逢反弹减)

**踩坑记录:**
- 新增 analyst 需要改 6 个文件(analyst 本体 + agent_states + __init__ + conditional_logic + trading_graph + setup),漏一个就 graph 跑不起来
- 原版 bull/bear researcher 和 3 个 risk debater 只读 4 个 report 字段,新增的 policy/hot_money/lockup 报告不会自动流入 debate 层 — 这是需要手动修复的"隐性 gap"
- fundamentals_analyst 原版有 trailing comma tuple bug:`system_message = ("...",)` 是 tuple 不是 string

### Week 2.5 — 间隙修补(2026-05-04) ✅ 已完成

**目标:修复 Week 2 改造后遗留的管道 gap。**

- [x] `propagation.py`:初始状态缺 3 个新字段 → 新增 `policy_report` / `hot_money_report` / `lockup_report` 初始化
- [x] `trader.py`:完全重写为 A 股特化 — 读取 3 个新报告 + T+1/涨跌停/手数/交易时段约束
- [x] `reflection.py`:Alpha 基准标签从 `SPY` 改为 `CSI 300（沪深300）`
- [x] `research_manager.py`:prompt 加入 A 股分析维度提示
- [x] `trading_graph.py`:`_fetch_returns` 基准从 `yf.Ticker("SPY")` 改为 `yf.Ticker("000300.SS")`（沪深300指数）+ 变量名 `spy` → `benchmark`
- [x] `tests/test_memory_log.py`:4 个 `_fetch_returns` 测试用例同步更新 mock dispatch key 和变量名

### Week 3 — 案例库 + 文档 + 发布(2026-05-04)

**目标:能对外发布的版本。**

- [x] 写中文 README(`README.md`):架构图、7 角色表、数据源、快速开始、配置说明、差异化对比
- [x] 写改造记录(`CHANGES_FROM_UPSTREAM.md`):Week 1/2/2.5 全部改动 + 22 文件清单 + 4 设计决策
- [x] 写 Apache 2.0 NOTICE 文件(`NOTICE`):fork 归属声明
- [x] 修 `_fetch_returns` SPY → CSI 300 实际取数(trading_graph.py + 测试)— 4/4 测试通过
- [x] 创建批量案例运行脚本(`examples/run_cases.py`):10 只跨板块 A 股,输出 md + json
- [ ] 跑 5-10 只真实 A 股的完整辩论案例
- [ ] 把案例归档到 `examples/cases/`
- [ ] 写部署指南(`DEPLOYMENT.md`)(可选)
- [ ] **里程碑**:发布到 GitHub,EP16 视频同步上线

### Week 3.5 — 信号层 + SKILL V2 数据升级(2026-05-11~12) ✅ 已完成

**目标:补齐 a-stock-data SKILL.md V2 的信号层能力,让 Agent 能感知题材热点和资金流向。**

**数据层升级(a_stock.py 735→1277 行,9→14 方法):**
- [x] 增强 `get_fundamentals()`:内联一致预期EPS(同花顺 `stock_profit_forecast_ths`) + 前向PE + PEG + PE消化时间计算
- [x] **新增** `get_profit_forecast()`:独立的机构一致预期端点,返回覆盖机构数、EPS区间、前向PE、PEG、PE消化
- [x] **新增** `get_hot_stocks()`:同花顺热点接口 — 当日涨停股 + 题材归因 reason tags(人工运营标签) + 题材词频统计
- [x] **新增** `get_northbound_flow()`:同花顺 hsgtApi — 北向资金(沪深股通)实时分钟级流向 + 可选历史日级数据
- [x] **新增** `get_concept_blocks()`:百度股市通 PAE — 个股所属概念板块/行业分类(申万)/地域,每个板块含当日涨幅
- [x] **新增** `get_fund_flow()`:百度股市通 PAE — 个股主力/散户资金流向(分钟级实时超大单/大单/中单/小单) + 20日历史

**管道接入(interface.py → tool wrapper → analyst):**
- [x] `interface.py`:新增 `signal_data` 类别,注册 5 个新方法到 `VENDOR_METHODS`
- [x] `default_config.py`:新增 `signal_data: "a_stock"` 默认配置
- [x] **新建** `signal_data_tools.py`:5 个 `@tool` 包装(参照 `news_data_tools.py` 模式)
- [x] `agent_utils.py`:re-export 5 个新工具供 analyst 导入
- [x] `hot_money_tracker.py`:绑定 `get_hot_stocks` + `get_northbound_flow` + `get_concept_blocks` + `get_fund_flow`,更新 prompt 添加工具说明和分析步骤
- [x] `fundamentals_analyst.py`:绑定 `get_profit_forecast`,更新 prompt 添加估值工具说明

**Bug 修复:**
- [x] `get_concept_blocks()` ResultCode 类型不匹配:百度 PAE 返回 `ResultCode` 为字符串 `"0"`,代码用 `!= 0` 比较(int),Python 3 下 `"0" != 0` 始终为 True → 改为统一 `str()` 比较
- [x] `get_fund_flow()` 同一模式预防性修复,确保 int/str 两种返回类型都能正确处理

**数据源映射更新:**

| 方法 | 数据源 | 用途 |
|---|---|---|
| get_profit_forecast | akshare → 同花顺 | 机构一致预期EPS + 前向估值 |
| get_hot_stocks | 同花顺 zx.10jqka.com.cn | 当日强势股 + 题材归因(零鉴权) |
| get_northbound_flow | 同花顺 data.hexin.cn hsgtApi | 北向资金分钟级 + 历史日级(零鉴权) |
| get_concept_blocks | 百度股市通 PAE | 概念板块/行业/地域 + 当日涨幅(零鉴权) |
| get_fund_flow | 百度股市通 PAE | 个股超大单/大单/中单/小单净流入(零鉴权) |

**双视角审视结论:**

投资者视角 — 已修复 P0(信号层接线完成 + 个股资金流向补齐),仍存在 P1 缺口:
- 龙虎榜买卖席位数据(hot_money_tracker 的 prompt 提到但 `get_insider_transactions` 只返回 F10 股东研究)
- 限售解禁日历(lockup_watcher 只能从新闻间接推断)
- 行业横向对比(单票绝对估值 vs 同行相对估值)

架构师视角 — 已知风险:
- mootdx TCP 单例无重连(连接断开后续调用全失败)
- 6-file pipeline 维护成本(每加一个 analyst/tool 改 6 个文件)
- 错误返回字符串而非异常(LLM 可能把错误当数据分析)
- 百度 PAE 接口无版本号/无文档,可能随时变更字段名或返回类型(已踩过 ResultCode str/int 坑)

### Week 4 — 辩论层 A 股特化(2026-05-12) ✅ 已完成

**目标:让牛熊辩论和三方风控辩论真正理解 A 股市场结构,而不是套用美股思维。**

**改造原则:**
- 保持英文 prompt(推理质量优先,与 Week 2 辩论层英文决策一致)
- 不改 LangGraph 拓扑,只改 prompt 内容
- 每个角色注入「A-Share XXX Framework」,用 A 股特有机制作为论据框架

**5 个文件改造:**

| 角色 | 注入的 A 股框架 | 核心论据 |
|------|----------------|---------|
| **Bull Researcher** | A-Share Bull Framework | 政策顺风(专精特新/国家战略)、北向资金确认、游资接力动量、PE消化成长叙事(30x锚点)、解禁出清利好 |
| **Bear Researcher** | A-Share Bear Framework | 政策反转风险(窗口指导/行业整顿)、解禁减持压力(预披露窗口)、游资撤退信号(放量滞涨/连板断裂)、估值泡沫(PEG>2)、T+1锁仓陷阱、北向撤退 |
| **Aggressive Debater** | A-Share Aggressive Framework | 涨停板动量效应(T+1防恐慌抛售)、政策底(policy put)、PE扩张周期(A股50-100x常态)、散户情绪放大器(80%散户)、游资席位确认 |
| **Conservative Debater** | A-Share Conservative Framework | T+1不可逃逸(核心结构性风险)、跌停板流动性陷阱(连续跌停无法出逃)、解禁悬顶、政策市反转、游资快进快出、ST/退市风险(±5%限制+机构强制卖出) |
| **Neutral Debater** | A-Share Neutral Framework | T+1双刃剑(锁损 vs 防恐慌)、政策信号分级(国务院>地方>传闻)、北向作辅助信号、估值区间法(非绝对判断)、板块轮动周期定位(2-4周)、仓位管理优先于方向判断 |

**设计亮点 — 同一机制的三方对立:**

T+1 制度:
- Aggressive:"T+1 防止恐慌抛售,有利多日连板"
- Conservative:"T+1 锁死亏损,隔夜风险无法对冲"
- Neutral:"关键在仓位控制,让单次隔夜缺口可承受"

涨跌停制度:
- Aggressive:"连续涨停创造爆发性收益"
- Conservative:"连续跌停导致灾难性亏损且无法退出"
- Neutral:"用限价单和分批建仓控制风险"

**改造前后对比:**

| 对比项 | 改造前 | 改造后 |
|--------|--------|--------|
| 辩论层身份 | 通用"Stock Analyst" | 明确"A-share stock"身份 |
| 论据框架 | 美股通用(growth/competitive/macro) | A 股特有(政策市/游资/涨跌停/T+1/北向/解禁) |
| 风控维度 | 通用风险偏好差异 | A 股结构性约束(T+1 锁仓、跌停流动性陷阱等) |
| 三方对立 | 人为角色差异 | 基于同一 A 股机制的真实多角度辩论 |

**已完成适配的全部角色(15 个):**

| 阶段 | 角色 | A 股适配 |
|------|------|---------|
| Analyst (7) | market / fundamentals / news / social / policy / hot_money / lockup | ✅ 中文 prompt + A 股框架 |
| Debate (2) | bull_researcher / bear_researcher | ✅ A-Share Bull/Bear Framework |
| Risk (3) | aggressive / conservative / neutral debater | ✅ A-Share Risk Framework |
| Manager (2) | research_manager / portfolio_manager | ✅ A-share 标注 + 交易约束 |
| Trader (1) | trader | ✅ T+1/涨跌停/手数/时段 |

**至此全部 15 个 Agent 角色完成 A 股适配。**

### Week 5 — 数据质量门控实测(2026-05-12) ✅ 已完成

**目标:用真实 A 股跑全部 14 个数据接口,发现并修复数据源问题。**

**实测标的:000858 五粮液(白马蓝筹,数据最全 → 如果它都有缺说明是结构性问题)**

**实测发现与修复:**

| 接口 | 问题 | 严重性 | 修复 |
|------|------|--------|------|
| get_northbound_flow | 历史数据来自 `hsgtData` API,返回 2024 年旧缓存;且只输出日期不输出金额 | **P0** | 删掉不可用的 hsgtData,改为实时数据 + 本地 CSV 自缓存历史 + 趋势对比 |
| get_insider_transactions | mootdx F10 原文 19969 chars,其中【4.股东变化】占 16121 chars(十大股东历史),浪费 token | **P1** | 截取最新一期,尾部标注 truncated |
| get_indicators | 测试脚本参数传错导致假报错(实际功能正常) | 测试 | 修正测试参数 |

**P0 北向资金历史数据——根因分析:**

eastmoney 全系北向资金接口(含 akshare `stock_hsgt_hist_em`、datacenter RPT_MUTUAL_DEAL_HISTORY、push2his kamt.kline)自 2024-08-16 后净买额字段全部返回 NaN/None/0。同花顺 `hsgtData` chart 数据也是 2024 年旧缓存。这是上游行业性数据断供,非我方 bug。

**解决方案:自建历史缓存**
- 实时数据仍用同花顺 `dayChart`(实测正常:HGT=-9.28, SGT=-31.10)
- 每次调用自动把当天收盘数据写入 `~/.tradingagents/cache/northbound_daily.csv`
- `include_history=True` 时从本地缓存读取最近 20 天 + 计算均值 + 今日 vs 均值对比
- 优点:零外部依赖,数据自己攒,越跑越丰富
- 缺点:新用户首次跑只有当天数据,无历史对比

**实测结果(修复后):**
- 14/14 接口全部 OK
- 北向资金:716 chars,实时+历史+趋势(修复前:1120 chars 含错误数据)
- 股东研究:5906 chars(修复前:19969 chars,**-70% token**)
- 技术指标:1207 chars(修复前:77 chars 错误信息)

### Week 6 — MiniMax 集成 + E2E 实战验证(2026-05-12) ✅ 已完成

**目标:接入 MiniMax 作为推荐 LLM 供应商,用真实 A 股跑通完整 Pipeline。**

**背景决策:为什么需要新增 LLM 供应商**

TradingAgents 每次分析需 30-50 次 LLM API 调用,必须使用 API Key 模式。Claude/ChatGPT 订阅版无法使用(订阅版走 Web 界面,不暴露 chat completions API)。需要一个国内直连、OpenAI 兼容、成本可控的供应商。

**供应商选型:**

| 供应商 | 优势 | 劣势 |
|--------|------|------|
| **MiniMax(推荐)** | 国内直连、OpenAI 兼容、M2.7 旗舰 + highspeed 双模型、价格合理 | 生态知名度不如 DeepSeek |
| DeepSeek | 性价比极高、推理能力强 | 高峰期限流严重 |
| 智谱 GLM | 国产老牌、API 稳定 | 模型能力略逊 |
| Kimi | Anthropic 兼容 API | 需要额外 backend_url 配置 |
| OpenAI | 全球最强模型 | 国内需代理、成本最高 |

**代码改动(4 文件):**

| 文件 | 改动 | 说明 |
|------|------|------|
| `tradingagents/llm_clients/factory.py` | `_OPENAI_COMPATIBLE` 增加 `"minimax"` | 路由 minimax → OpenAIClient |
| `tradingagents/llm_clients/openai_client.py` | `_PROVIDER_CONFIG` 增加 `"minimax": ("https://api.minimax.chat/v1", "MINIMAX_API_KEY")` | base_url + API key 环境变量 |
| `tradingagents/llm_clients/model_catalog.py` | 新增 `"minimax"` 模型目录(M2.7/M2.7-highspeed/M2.5/M2.5-highspeed) | CLI 选项 + 模型验证 |
| `README.md` | 重写「配置 LLM」章节:7 个供应商(.env 配置) + 3 套 config 示例(MiniMax/DeepSeek/Anthropic) | 明确说明"必须用 API Key,不能用订阅版" |

**关键技术细节:**
- MiniMax 走 `provider="minimax"` 而非 `provider="openai"`,因为 OpenAI 原生路径会启用 `use_responses_api=True`(指向 `/v1/responses`),MiniMax 不实现该端点
- MiniMax API 的模型列表通过 `GET /v1/models` 获取,当前可用:M2.7 / M2.7-highspeed / M2.5 / M2.5-highspeed / M2.1 / M2.1-highspeed / M2
- 选型:deep_think 用 `MiniMax-M2.7`(旗舰),quick_think 用 `MiniMax-M2.7-highspeed`(快速)

**E2E 实战结果(2 只股票):**

| 样本 | 板块 | 耗时 | AI Message 数 | 数据层错误 |
|------|------|------|---------------|-----------|
| 样本 A | 创业板 | 977s (16.3 min) | 17 | 1 (akshare 超时) |
| 样本 B | 主板 | 890s (14.8 min) | 23 | 2 (akshare 超时) |

**Pipeline 全链路验证:**

```
7 Analysts → Quality Gate → Bull/Bear Debate → Trader → Risk Panel (3方) → PM
    ✅           ✅            ✅              ✅         ✅              ✅
```

**链路覆盖度验证(不记录个股结论,仅记录各环节是否跑通):**
- 技术分析层:MACD/布林带/RSI 全套指标计算正常返回
- 基本面层:财报字段、融资事件字段解析正常
- 解禁评估层:10 章完整报告结构生成正常
- 资金面层:北向/主力资金字段拉取正常

**已知问题(不影响功能):**

| 问题 | 严重性 | 说明 |
|------|--------|------|
| Risk Panel 重复输出 | P2 | Hold 信号在 Risk Debate 阶段重复 3-4 次,可能是 debate loop 或 MiniMax stop token 处理 |
| `<think>` 标签泄漏 | P2 | MiniMax 的 thinking 内容被保存到最终决策文本,需在输出时过滤 |
| akshare 偶发超时 | P3 | 东方财富 `stock_individual_info_em` 偶尔 ProxyError,不影响整体流程 |

**案例文件归档:**
- 已于 2026-07-24 移除。本项目不在仓库内提供针对具体证券的分析报告或评级结论;
  `examples/run_cases.py` 保留为可自行运行的技术演示脚本,运行结果由使用者自行保管。

**run_cases.py 配置更新:**
- `llm_provider`: `"anthropic"` → `"minimax"`
- `deep_think_llm`: `"claude-sonnet-4-6"` → `"MiniMax-M2.7"`
- `quick_think_llm`: `"claude-sonnet-4-6"` → `"MiniMax-M2.7-highspeed"`
- 移除 `backend_url`(MiniMax 用 `_PROVIDER_CONFIG` 内置 URL)

---

## Week 7：Web UI（Streamlit 可视化界面）

**目标**：让用户不写代码也能用，一键分析 → 实时看进度 → 查看完整报告 → 下载 PDF。

**时间**：2026-05-12

### 架构设计

- **技术栈**：Streamlit（Python 生态内，零前端依赖）
- **线程模型**：分析在 daemon 线程跑（15 分钟长任务），主线程通过 `ProgressTracker` + `st.session_state` + 2 秒轮询 `st.rerun()` 实时刷新
- **启动方式**：`tradingagents-web` CLI 命令 或 `streamlit run web/app.py`

### 文件清单（10 Python + 2 配置 = 12 文件）

| 文件 | 行数 | 职责 |
|------|------|------|
| `web/app.py` | ~210 | 主入口：Page config、CSS 注入、5 态状态机 |
| `web/runner.py` | ~110 | 后台线程：创建 TradingAgentsGraph、stream 状态、检测 12 阶段完成 |
| `web/progress.py` | ~95 | ProgressTracker：线程安全、12 阶段定义、stage 状态追踪 |
| `web/history.py` | ~55 | 扫描 `~/.tradingagents/logs/` 历史 JSON |
| `web/pdf_export.py` | ~170 | fpdf2 PDF 生成：CJK 字体自动检测、封面 + 7 报告 + 辩论 + 风控 |
| `web/launch.py` | ~15 | CLI 启动器：`tradingagents-web` 命令入口 |
| `web/components/sidebar.py` | ~75 | 侧边栏：Logo + 股票输入 + 日期选择 + 历史列表 |
| `web/components/progress_panel.py` | ~105 | 进度面板：彩色状态徽章 + 进度条 + 4 指标 |
| `web/components/report_viewer.py` | ~130 | 报告展示：信号卡片 + 7 报告 + 辩论 Tabs + 风控 Tabs + PDF 下载 |
| `.streamlit/config.toml` | 6 | Streamlit 暗色主题配置 |
| `pyproject.toml` | +3 deps | 新增 streamlit / fpdf2 / python-dotenv |

### 视觉设计

- **暗色主题**：`#0a0a0a` 背景 + `#ff5a1f` 橙色主色（匹配视频录制风格）
- **Inter 字体**：Google Fonts CDN
- **Streamlit 去 Chrome**：隐藏 Deploy 按钮、汉堡菜单、Made with Streamlit 水印
- **渐变按钮**：主按钮带 box-shadow 发光效果 + hover 动画
- **信号卡片**：Buy 绿色 / Hold 金色 / Sell 红色，大字居中

### 修复的 Bug

| Bug | 原因 | 修复 |
|------|------|------|
| Signal 显示 N/A | `extract_signal` 只检查 `final_trade_decision`，该字段含 `<think>` 且无 BUY/SELL/HOLD 关键词 | 改为按优先级检查 `investment_plan` → `trader_investment_decision` → `final_trade_decision`，先 strip `<think>` |
| PDF 下载报错 | fpdf2 `output()` 返回 `bytearray`，Streamlit download 需要 `bytes` | 包 `bytes()` 转换 |
| 报告缺 trader/investment_plan | 字段名错误：代码写 `trader_investment_plan` 实际是 `trader_investment_decision` + `investment_plan` | 修正字段名 |

### 依赖变化

```
pyproject.toml:
+  "streamlit>=1.45.0",
+  "fpdf2>=2.8.0",
+  "python-dotenv>=1.1.0",

[project.scripts]
+  tradingagents-web = "web.launch:main"
```

### 合规免责声明（5 处覆盖）

中国《证券投资咨询管理暂行办法》要求：向公众提供证券投资建议需持牌，与是否收费无关。本项目定位为"开源学习工具"而非"投资咨询服务"，但仍在所有用户可见位置添加免责声明：

| 位置 | 内容 |
|------|------|
| Web UI 欢迎页底部 | 完整三句免责（学习研究 + 咨询持牌机构 + 不承担损失） |
| 侧边栏底部 | 短版提示 |
| 报告页信号卡片下方 | "本报告由 AI 自动生成，仅供学习研究，不构成投资建议" |
| PDF 报告封面 | 完整免责声明段落 |
| README.md | 顶部醒目提示 + 底部独立免责声明章节（含 4 条细则） |

**涉及文件**：`web/app.py`、`web/components/sidebar.py`、`web/components/report_viewer.py`、`web/pdf_export.py`、`README.md`

---

## 视频内容映射(EP12 - EP16)

| 集数 | 主题 | 对应里程碑 |
|---|---|---|
| EP12 | 拆解 TradingAgents 架构 + 改造路线图 | 调研阶段(已完成) |
| EP13 | 改造数据层 — 9 个 vendor 方法落地 A 股 | Week 1 |
| EP14 | Agent 提示词中文化 + 加 A 股特化角色 | Week 2 |
| EP15 | 实战 — 多空 Agent 辩论真实 A 股 | Week 3 案例 |
| EP16 | 发布开源版本 + 企业版邀约 | Week 3 收尾 |
| EP17 (可选) | 对比 hsliuping CN 版,讲清差异 | 收尾后 |

---

## 当前进展(2026-05-12)

### 已完成

- ✅ 调研原版 TradingAgents 架构(数据层 dispatch、Agent 编排、LangGraph 用法)
- ✅ 调研 hsliuping CN 版(扒清 Apache 2.0 部分 vs 商业闭源部分)
- ✅ 与 EP11 a-stock-data Skill 的桥接路径已明确
- ✅ 三周改造路线图、五大决策、差异化定位全部锁定
- ✅ Fork 原版仓库到本目录,记录 fork 点 commit `7e9e7b8`
- ✅ 写本 DEV_LOG
- ✅ **Week 1 数据层改造完成** — `a_stock.py` 9 个 vendor 方法 + interface 注册 + config 默认切换
- ✅ **Week 1 E2E 验证通过** — 688017(绿的谐波)4 analyst 英文辩论,Kimi 2.6 驱动,输出 HOLD 决策
- ✅ **Week 2 P0 输出语言** — `output_language: "Chinese"` 一行搞定
- ✅ **Week 2 P1 四 analyst 中文化** — market/fundamentals/news/social 全部改为 A 股特化中文 prompt
- ✅ **Week 2 P2 两个新角色** — policy_analyst(政策分析师) + hot_money_tracker(游资追踪) + 六文件管道联动
- ✅ **Week 2 P3 第七角色 + 下游修复** — lockup_watcher + 5 个下游 agent 补 3 新报告字段 + PM A 股约束
- ✅ **Week 2 E2E 最终验证** — 688017 七 analyst 全流程中文辩论,Underweight 决策,报告 ~2100 行
- ✅ **Week 2.5 间隙修补** — propagation 初始化 + trader 重写 + reflection/research_manager 适配 + _fetch_returns SPY→CSI300
- ✅ **Week 3 文档三件套** — README.md(中文) + CHANGES_FROM_UPSTREAM.md + NOTICE
- ✅ **Week 3 基准修复** — `_fetch_returns` SPY→000300.SS 实际取数 + 测试 4/4 通过
- ✅ **Week 3 案例脚本** — `examples/run_cases.py` 10 只跨板块 A 股批量运行
- ✅ **Week 3.5 信号层 + SKILL V2 升级** — a_stock.py 9→14 方法(含百度PAE概念板块+资金流向) + signal_data_tools 5工具 + analyst 绑定 + ResultCode 类型 bug 修复 + 5/5 端点实测通过
- ✅ **Week 4 辩论层 A 股特化** — 5 个辩论角色 prompt 注入 A 股论据框架(详见下方 Week 4 节)
- ✅ **Week 5 数据源修复** — 北向资金历史自缓存 + F10 截断(-70% token) + 14/14 接口实测通过
- ✅ **Week 5.5 数据质量门控(P0)** — `quality_gate.py` 两层验证(硬检查+LLM复审) + 7 analyst 必采清单 + graph 接线 + researcher 消费质量摘要
- ✅ **Week 5.5 数据缺口补齐(P1)** — a_stock.py 14→17 方法：龙虎榜席位(`get_dragon_tiger_board`)、限售解禁日历(`get_lockup_expiry`)、行业横向对比(`get_industry_comparison`) + signal_data_tools 3新工具 + analyst 绑定 + ToolNode 关键 bug 修复
- ✅ **Week 5.5 边界测试(P2)** — ST(*ST岩石 600696) 16OK/1WARN/0FAIL + 科创板(中芯国际 688981) 17/0/0 + 中小板(立讯精密 002475) 17/0/0
- ✅ **ToolNode 关键 Bug 修复** — `trading_graph.py` 的 `_create_tool_nodes()` 未包含 signal 工具(get_hot_stocks/get_northbound_flow 等),导致 analyst 的 tool call 在 ToolNode 执行时找不到函数。Week 2-4 的所有信号工具调用都受此影响
- ✅ **Week 6 MiniMax 集成** — factory.py + openai_client.py + model_catalog.py + README.md 四文件改动,MiniMax 成为推荐供应商
- ✅ **Week 6 E2E 实战验证** — 两只样本(创业板 16.3min + 主板 14.8min),MiniMax-M2.7 全链路通过
- ✅ **Week 7 Web UI** — Streamlit 可视化界面：一键分析 + 12 阶段实时进度 + 7 报告展示 + 多空/风控辩论 Tabs + PDF 导出 + 历史记录(10 文件 + 2 配置)

### 未开始

- ⏳ Risk Panel 重复输出问题排查(P2)
- ⏳ mootdx TCP 重连逻辑
- ⏳ 发布到 GitHub + EP16 视频

---

## 风险与开放问题

### 已识别风险

| 风险 | 应对 |
|---|---|
| mootdx 必须国内 IP 才稳定 | 视频里说明,海外用户用 akshare fallback |
| LLM 调用成本累积 | 默认推荐 MiniMax-M2.7(国内直连,成本远低于 GPT/Claude) |
| 与 hsliuping 的 CN 版定位重叠 | 文档/视频里清楚说明差异:License + 部署轻量 + 数据源 + A 股深度 + 配套教学 |
| 维护成本(上游频繁更新) | 选择性同步策略,关键改动在 fork 内独立演进 |

### 开放问题(待决策)

- [ ] 项目要不要加 Web UI?(原版无,CN 版有但商业闭源)— 倾向**先不加**,保持轻量
- [ ] 要不要做 Docker 镜像?— 倾向加,降低部署门槛
- [ ] 要不要 GitHub Actions CI?— 倾向先放着,发布时再加
- [ ] 中文 README 之外要不要英文 README?— 国际化考虑可以加,优先级低

---

## 协作约定

- 写代码前先读 `CHANGES_FROM_UPSTREAM.md`(待建)了解哪些已改、哪些未动
- 改 prompt 必须有真实 A 股案例验证,不能"看起来对就提交"
- 提交前用 `pytest tests/` 跑一遍原有测试,确保没有 regression
- License 头不要去掉,保留 Apache 2.0 attribution
