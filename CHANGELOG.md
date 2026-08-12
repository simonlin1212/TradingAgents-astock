# Changelog

All notable changes to TradingAgents are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Breaking changes within the 0.x line are called out explicitly.

## [0.5.14] — 2026-08-09

### 修复：连字符分隔符被当成构词，评级被静默丢弃

`最终评级：**Sell**- 退出` 里的 `-` 只是分隔符，却被当成"会延续成更长的词"而判否，
`parse_rating` 静默返回 Hold —— 记录下错误的决策。

判据再补一层：**连字符要看它后面**。跟字母/数字是构词（`Sell-off` / `Buy-side` 拒），
跟空白或其它字符只是分隔符（`Sell- 退出` 收）。覆盖矩阵扩到 27 例。

### 修复：版本号三处不同步

上一版改了 `pyproject.toml` 和 `CHANGELOG.md`，**漏了 `CLAUDE.md` 的「当前版本」行**
—— 后续 agent 和发版流程读它会拿到旧版本。

新增 `tests/test_version_consistency.py`：三处不一致直接测试失败，不再靠人记得。

### 测试

369 passed / 13 skipped / **0 failed**（新增 4 例）。

---

## [0.5.13] — 2026-08-09

### 修复：加粗 + 连字符仍会被判成评级（正则回溯）

v0.5.12 把 markdown 收尾星号写成 `\*{0,2}(?!词字符)` —— **先消耗再判断会回溯**：
`建议：**Sell**-off risk remains elevated` 里 `\*{0,2}` 先吃掉 `**`，被 `-` 判否后
退一步只吃一个 `*`，剩下那个 `*` 恰好满足边界，于是又判成 Sell。正好把这条规则本来
要挡的连字符散文放了回来。

改成把星号**放进前瞻内部**（`(?!\*{0,2}词字符)`）——"后面不能是（0~2 个星号 + 词
字符）"没有可回溯的余地。`最终评级：**Sell**` 这类正常写法不受影响。

⚠️ **刻意不用占有量词 `(?>...)` / `*+`**：那是 Python 3.11+ 才有的，而本项目声明
`requires-python = ">=3.10"`，3.10 用户会在**导入时**就 `re.error`——比逻辑 bug
更硬的破坏。新增一条守卫用例，直接检查编译后的 pattern 里没有这些写法。

覆盖矩阵扩到 25 例。

### 测试

365 passed / 13 skipped / **0 failed**（新增 4 例）。

---

## [0.5.12] — 2026-08-09

Codex 第七轮 + **两处重构**。这两块前后各被修了三轮"修了又漏"，问题不在某个字符，
在抽象选错了——所以这次改的是判据本身，不是再打一个补丁。

### 重构：评级边界改用「不能延续成更长的词」

第七轮指出，v0.5.11 收紧后又误伤了 `最终评级：Buy（基于风险收益比）` 和
`最终评级：Underweight(估值偏高)` —— 因为我枚举的是**收尾**标点，没算上开括号，
于是合法评级被静默改写成 Hold。

三轮的轨迹：

| 判据 | 漏掉的 |
|---|---|
| 无边界 | `Buyer interest` → Buy |
| `(?![A-Za-z])` | `Sell-off risk`、`Buy2024` → Sell / Buy |
| 枚举收尾标点 | `Buy（基于风险收益比）` → **反被判成 Hold** |

**枚举允许的标点是个填不完的坑。** 改成只问一件事：紧跟其后的字符会不会让它变成
另一个词（`[A-Za-z0-9_-]`）？会就不算评级，其余（中文、各种括号、标点、空白、行尾）
一律放行。

新增 22 例参数化覆盖矩阵，并写明**改这条规则必须整张过一遍**——只补自己想到的那
一两个用例，正是前三轮反复的成因。

### 重构：BESTIP 保护改为上下文管理器

原来是在两处手动调 `_restore_bestip()`，**再加一条提前返回就会漏掉一处**，而漏掉的
后果是静默给用户留下一台死服务器。改成 `with _preserve_mootdx_bestip() as keep:`：
选出可用服务器时调 `keep()` 表示"这次覆写是想要的"，其余每条退出路径（**包括异常**）
都自动还原。

`_get_mootdx_client()` 114 → 82 行。新增两例：选中时不还原、探测抛异常时也还原。

端到端实测：真实探测 38 台全部失败后，用户配置的 `218.6.170.47` 完好无损。

### 测试

361 passed / 13 skipped / **0 failed**（新增 21 例）。

---

## [0.5.11] — 2026-08-09

Codex 第六轮：**上一版那两个修复本身都没修对。**

### 修复：BESTIP 快照取到的是空默认值（v0.5.10 的修复无效）

v0.5.10 为了不覆写用户配置，在探测前快照了 `config.get("BESTIP")`。但在新进程里
**mootdx 要等 `BaseQuotes.__init__` 调 `config.setup()` 之后才把持久化的值读进来**
——此前 `get("BESTIP")` 返回的是模块默认空值。于是快照到的是空值，一旦全部探测失败，
"还原"反而**把用户真实配置抹成空**，比不还原更糟。

实测（mootdx 0.11.7）：`setup()` 前 `{'HQ': ''}`，`setup()` 后
`{'HQ': ['218.6.170.47', 7709]}`。现在快照前先显式 `setup()`。

端到端验证：真实探测 38 台全部失败后，用户配置的服务器完好无损。
测试也改为复刻真实构造函数语义（旧的假件根本不调 `setup()`，所以抓不到这条）。

### 修复：评级边界仍放行连字符散文（v0.5.10 的修复不完整）

`(?![A-Za-z])` 只挡住了紧跟字母的情况，连字符和数字后缀照样过关：

| 文本 | v0.5.10 | 现在 |
|---|---|---|
| `建议：Sell-off risk remains elevated` | Sell ❌ | Hold |
| `最终评级：Buy-side interest is weak` | Buy ❌ | Hold |
| `最终评级：Buy2024` | Buy ❌ | Hold |

改为要求评级词后面是**真正的结束**（行尾 / 空白 / 中文 / 常见标点），并先吃掉
markdown 的收尾星号，`最终评级：**Sell**` 这类正常写法不受影响。

### 测试

340 passed / 13 skipped / **0 failed**（新增 2 例）。

---

## [0.5.10] — 2026-08-09

Codex 第五轮的两处，都是新增行为自己带出来的副作用。

### 修复：探测服务器会覆写用户配置的 mootdx 服务器

mootdx 的 `StdQuotes.__init__` 里有 `config.set('BESTIP', {'HQ': self.server})`
——**每建一次带 `server` 的 client 都会持久化写进它的配置文件**。v0.5.6 把候选表从
10 台扩到 38 台之后，逐台探测等于把用户原本配好的服务器一路覆写，最后留在配置里的
是最后一台**失败的**服务器：

- 下面那个裸 `Quotes.factory()` 兜底读的正是 BESTIP，于是再也救不回来；
- 更糟的是同一台机器上**其它用 mootdx 的程序**也会被留下一台死服务器。

现在探测前先快照 BESTIP，裸 factory 兜底之前、以及一台都没选出来时都还原回去。

### 修复：中文标签后跟英文散文会被误判成评级

`_CN_LABEL_EN_RE` 缺词边界，于是：

| 文本 | 修复前 | 修复后 |
|---|---|---|
| `最终评级：Buyer interest remains weak` | Buy ❌ | Hold |
| `建议：Selling pressure is high` | Sell ❌ | Hold |
| `最终评级：Holder structure changed` | Hold（碰巧对） | Hold |

这类误判会被写进记忆日志，再污染 `tradingagents performance` 的评级统计，
而且从报告里完全看不出来。已加 `(?![A-Za-z])`，正常的中英混排（`最终评级：Buy`）
不受影响。

### 测试

338 passed / 13 skipped / **0 failed**（新增 4 例）。

---

## [0.5.9] — 2026-08-09

### 🔴 修复：裸跑 `tradingagents` 被 v0.5.2 打断（升级即破坏）

Typer 在只注册一个命令时用「单命令模式」，裸跑就等于跑那个命令。v0.5.2 加了
`performance` 子命令后它切换成「命令组模式」，于是：

```
$ tradingagents
Usage: tradingagents [OPTIONS] COMMAND [ARGS]...
╭─ Error ─────────────────╮
│ Missing command.        │
╰─────────────────────────╯
```

而 README 和所有文档写的都是裸跑 —— **每个现有用户升级后的第一条命令都会失败**。
已加 `@app.callback(invoke_without_command=True)` 保住这条默认路径，`--checkpoint`
等原有参数照常可用。新增 4 例测试，其中一例专门断言那段注释里写着后果——这个
callback 很容易在重构时被当成多余代码删掉。

### 修复：「今天」按主机时区算，海外用户会误判

`_is_historical()` 用 `datetime.now().date()`（主机本地日期）。主机在 UTC+9 以东
（如新西兰 UTC+13）时，当地已过零点而上海还在前一天 —— **当天的分析会被判成
「复盘历史」**：实时分钟资金流被整段略去，快照工具打出莫须有的未来函数警告。
反过来主机在西半球也会把已经过去的交易日当成"今天"。

改为固定按 A 股市场时区（Asia/Shanghai）计算，与主机时区无关。资金流回溯窗口的
天数差也一并改用市场日期。

### 修复：README 的指标口径与实际输出不符

v0.5.6 已把指标改名为 `direction_accuracy` / `up_rate` / `outperform_rate`，但
README 仍写着「胜率 / alpha 胜率」—— **而这正是 v0.5.6 要纠正的误导**：对看空评级
而言，"胜率"描述的是标的涨没涨，不是判断对不对。中英文 README 已同步为实际指标名，
并写明三者的区别与各自的样本量口径。

### 测试

334 passed / 13 skipped / **0 failed**（新增 5 例）。

---

## [0.5.8] — 2026-08-09

Codex **终轮**审计的四处。前三轮修的东西里，有两处"看着修好了、实际没生效"。

### 修复：未来函数告警仍然不会触发（承接 v0.5.6）

v0.5.6 给 `get_profit_forecast` 的工具补上了 `curr_date` 参数——但给了默认空串。
LangChain 因此只把 `ticker` 标成必填，模型按 `{"ticker": "600519"}` 正常调用时
`curr_date` 是空串，`_is_historical("")` 返回 False，**告警照样一次都不会触发**。
基本面分析师的提示词里也只写了工具名、没提日期参数。

改为**必填**，并在提示词里显式写出 `get_profit_forecast(ticker, curr_date)` 及其原因。
到这一版，这个告警才真正生效。

### 修复：历史资金流放大窗口后没裁回来（承接 v0.5.6）

v0.5.6 为了能回溯到分析日而放大了请求窗口，但过滤掉未来行之后**没有裁回承诺的
20 个交易日**——复盘 90 天前会返回约 40 行，既改变了请求的趋势窗口，又把每次情绪
工具的返回体撑大一倍。已裁回 20 行。

### 修复：未选中的分析师角色也会被建模型

`role_llms` 里配了 `policy`，但本次分析只选了 `market` 时，`policy` 的模型仍会被
实例化。**一个永远不会执行的节点，可能因为缺 API key 或缺可选依赖，把一次本来完全
正常的分析在启动时就打断。** 现按 `selected_analysts` 过滤分析师角色；多空 / 风险 /
Manager 这些不受选择控制的角色照常构建。

### 修复：方向正确率的显著性用错了分母

`direction_accuracy` 排除了 Hold，但"样本是否足够"的判断用的是**已结算总数**。
20 条已结算里只有 1 条有方向时，噪音提示被抑制，报告却敢显示「方向正确率 100%」。
现在这个指标单独用 `directional_count` 判显著性，并给出专门的提示。

### 测试

329 passed / 13 skipped / **0 failed**（新增 7 例）。

---

## [0.5.7] — 2026-08-09

### 文档：`pip` 与 Python 版本对不上的排错（[#92](https://github.com/simonlin1212/TradingAgents-astock/issues/92)）

用户装了 Python 3.14，`pip install -e .` 却报 `requires a different Python: 3.9.6`。
**不是仓库问题**：报错里的 3.9.6 就是当前 `pip` 绑定的解释器（macOS 自带的 `pip3`
常指向系统 3.9），但这句提示本身很容易让人以为是项目要求写错了。

中英文 README 各加一条 FAQ：怎么确认 `pip` 对应哪个解释器（`pip3 -V`）、为什么推荐
用 `python -m pip` 的写法、以及配合虚拟环境的完整命令（含 Windows 版）。

---

## [0.5.6] — 2026-08-09

Codex **复审**发现的五处，全部实测复现。复审的价值在这一轮体现得很清楚——其中两条
正是上一版修复自己留下的洞。

### 修复：未来函数告警在生产路径上是死代码

v0.5.1 给 `get_profit_forecast` 加了未来函数告警，但它的 LangChain `@tool` 只暴露
`ticker`，`route_to_vendor` 也只传 `ticker` —— `curr_date` 恒为 `None`，判定永远为
False，**告警一次都不会触发**。模型照样把今天的一致预期当成分析日当天的事实。
（审计发现只有这一个工具漏传，其余 16 个都正常。）

现已补上参数与转发，并加测试锁死"凡是数据层按 `curr_date` 做时点处理的工具，
`@tool` 都必须暴露并转发它"。

### 修复：历史资金流被过滤成一条不剩

东财日线资金流接口只提供"从今天回溯 N 个交易日"，没有 end_date。v0.5.1 仍固定要
20 天再按 `curr_date` 过滤 —— 复盘一个较早的日期时，返回的 20 行全在分析日之后，
**过滤后一行不剩**。把"数据不对"变成了"没有数据"，比不过滤更糟；而当时的测试夹具
恰好返回了一条真实请求不会包含的旧数据，把这个问题盖住了。

现按分析日与今天的间隔放大回溯窗口（上限 500，约两年），并在确实取不到时**明说原因**，
不让正文凭空少一段。

### 修复：mootdx 只试 10 台就判"全网不可达"

v0.5.5 为了规避 bestip 的全表测速而跳过了它，但这样一来 mootdx 自带主机表里的其余
28 台就永远试不到 —— 精选的 10 台恰好都不可用时会被误判成协议被拦，还记 5 分钟负缓存。

- **候选表扩为 38 台**（精选 10 台在前 + mootdx 自带主机表去重），逐台真实取数验证，
  覆盖面等同 bestip 而不做它那套要跑几分钟的测速。
- **TCP 预筛改为并发**：多数候选是"连都连不上"，串行要等满每个超时。并发只是把等 IO
  并行化，不改变选取顺序，精选表依旧优先。
- 实测全表不可用时：**73.7s → 27.0s**（v0.5.5 是 23.7s 但只覆盖 10 台；最初 >170s）。
  二次调用命中负缓存 0ms。

### 修复：角色模型串味 —— 主 provider 的专属参数被带给别家

`role_llms` 给某个角色配了别家 provider 时，仍复用主 provider 的 `llm_kwargs`。
`reasoning_effort`（openai）/ `thinking_level`（google）/ `effort`（anthropic）都是
各家私有参数，塞进 qwen / glm / 自建网关的请求体里可能被直接拒收。现按角色 provider
过滤，通用参数（`max_tokens` / `callbacks`）保留。

### 修复：订阅降级后 `max_tokens` 丢失

开着 Claude 订阅覆盖时，`max_tokens` 只进了 `llm_kwargs`，没进 `fallback_spec`。
撞额度降级到付费 provider 后，那边用自己的默认上限——报告照样被截断，而这正是用户
配 `max_tokens` 想避免的事。

### 测试

322 passed / 13 skipped / **0 failed**（新增 6 例）。

---

## [0.5.5] — 2026-08-09

Codex 审计后的五处修复。全部实测复现，无一误报。

### 修复：截断告警对**默认 provider** 根本不会响

`warn_if_truncated` 只认 Anthropic 的 `stop_reason=max_tokens` 与 Chat Completions
的 `finish_reason=length`。但 `openai` 是默认 provider 且走 **Responses API**，它的
截断信号是 `status="incomplete"` + `incomplete_details.reason="max_output_tokens"`；
Gemini 则是大写的 `finish_reason="MAX_TOKENS"`。两种都不匹配 —— 也就是说 v0.5.1
新加的这个告警，在默认配置下**一次都不会触发**。现已覆盖四种形状（值比较统一转小写），
并新增反向用例：因内容过滤而 `incomplete` 不该被报成输出上限。

### 修复：非 A 股防护漏了三个 vendor

`get_dragon_tiger_board` / `get_lockup_expiry` / `get_industry_comparison` 直接调
`safe_ticker_component`，绕过了 `_normalize_ticker`。实测拿港股 `00700` 调用，返回的
是**看起来完全正常的报告**——「近30日未上龙虎榜」「无历史解禁记录」——模型会当成腾讯
的事实。v0.5.3 声称的"一个卡点覆盖 15 个接口"并不成立，现已全部接入。

### 修复：绩效统计对看空评级把对错算反了

给出 Sell / Underweight 之后股价下跌，是**判断正确**，但原实现只看"收益是否为正"，
把它记成失败、把随后的上涨记成成功——所谓"胜率"根本不是决策准确率。

- 新增 **`direction_accuracy`（方向正确率）**：只统计有方向的评级（Hold 不表态不计入），
  按方向判定（看多要跑赢、看空要跑输），优先用 alpha 口径。
- 原两个指标改名为 `up_rate`（标的上涨占比）/ `outperform_rate`（跑赢占比），
  **命名即口径**，报告里明确写出它们与判断对错无关。

### 修复：平均持有期永远显示不出来

记忆日志写的是 `5d`（带后缀），`int("5d")` 抛异常被吞成 `None`，于是每条记录的持有期
都丢失、`avg_holding_days` 恒为空。改为提取数字部分。

### 修复：mootdx 提前收手会漏掉可用服务器

v0.5.1 加的「连续 3 台协议失败就停手」被指出证明力不足：三台远端拒绝**推不出**本地
网络封了协议，而列表靠后的服务器完全可能是好的，提前收手会让它永远试不到、还顺手记
5 分钟负缓存。已移除，改为跑完整张表。实测代价仅 18.7s → 23.7s（最初是 >170s，真正
的耗时大头 bestip 全表测速仍单独规避）。新增用例：可用服务器排在末位时仍能被选中。

### 测试

316 passed / 13 skipped / **0 failed**（新增 13 例）。

---

## [0.5.4] — 2026-08-06

干净 clone 上 `pytest` 从 11 red 变成全绿，并修掉藏在其中的一个计费护栏隐患。

### 修复：`ClaudeSDKError` 占位符退化成 `Exception`，让计费护栏失效

可选依赖 `claude-agent-sdk` 没装时，模块把 `ClaudeSDKError` 占位成 **`Exception`**
（注释写的是"placeholder so `except` clauses never NameError"）。但
`ClaudeSDKError` 会进 `_FALLBACK_ERRORS` —— 那个元组决定「哪些错误可以降级到按
token 计费的 provider」。一旦退化成 `Exception`，`isinstance(任何异常, ...)` 恒为真，
连**刻意排除在外**的 `_AuthError`（订阅凭据失效）也会被判成可降级。

而这条护栏存在的全部意义，就是不让"订阅 token 过期"变成"悄悄开始烧 API 账单"。

改用独立的 `_MissingSDKError` 占位：`except ClaudeSDKError` 一样不会 NameError，
元组永远不会变成 catch-all，保护这条护栏的两条测试也不再依赖可选依赖是否安装。

### 修复：9 个用例在没装可选依赖时红着，而不是跳过

`tests/test_agent_sdk_provider.py` 里有 9 个用例会走到 SDK 自己的 API
（`ClaudeAgentOptions` / `create_sdk_mcp_server`），没装依赖就报 ImportError。
同一文件里另外 3 个用例早已用 `skipif` 处理过同样情况——这 9 个只是漏加。

长期红的真实代价是**没人再看**：本次排查前，这 11 个红被反复当成"已知的缺依赖噪音"
掠过，而其中两条恰恰是上面那条计费护栏的测试。现在按文件既有约定统一加
`requires_sdk` 标记。

**干净 clone（`pip install -e .` 不带 `[agentsdk]`）跑 `pytest`：303 passed,
13 skipped, 0 failed。**

---

## [0.5.3] — 2026-08-06

港股/美股代码不再被当成 A 股静默查询（[#43](https://github.com/simonlin1212/TradingAgents-astock/issues/43) 前置修复）。

`_normalize_ticker()` 的文档写着"返回纯 6 位代码"，但从不校验位数：港股 `00700`
/ `0700.HK`、美股 `AAPL` 都被**原样放行**，然后拿去问 mootdx / 腾讯 / 东财。这些
源对不存在的代码往往不报错，只返回空值或僵尸报价（北交所 920 号段踩过同类问题），
于是模型会拿着一份看起来正常、实际属于别的市场的数据写完整篇报告——报告里完全
看不出来。

- **一个卡点覆盖 15 个数据接口**：`_normalize_ticker` 是所有 vendor 方法的必经之路。
- 港股代码报错时**指明去处**（姊妹项目 global-stock-data）和 roadmap（#43），
  而不是只说"不支持"。
- A 股各种写法（`SH600519` / `600519.SH` / `sz000001` / 北交所 `920002`）一个都
  不受影响，24 例测试两侧都锁。

港股多 Agent 分析本身仍在 roadmap：数据层可行性已验证（腾讯 / 新浪 / 东财 push2 /
Yahoo K线 / 东财港股三表 五个端点实测均可用），但 A 股特化的政策 / 游资 / 解禁三个
角色对港股不适用，需要单独设计角色集。

---

## [0.5.2] — 2026-08-06

新增决策绩效统计，并修掉一个会污染它的评级解析漏洞。

### 新增：`tradingagents performance`（[#61](https://github.com/simonlin1212/TradingAgents-astock/issues/61)）

决策和真实收益其实一直都在存——`TradingMemoryLog` 每次分析落一条决策，下次分析
同一只股票时自动拉真实行情回填收益与 alpha。缺的只是汇总：在此之前整个仓库连一个
胜率都算不出来。

- **零 LLM 调用**，只读已落盘的结果。
- 整体胜率 / **alpha 胜率**（对沪深 300）/ 平均与中位收益 / 最好最差。
- 按评级、按标的分组。
- **评级区分度检验**：五档评级从 Buy 到 Sell，平均 alpha 是否单调递减。不单调就说明
  评级没有实际区分能力——这比单看胜率有意义得多。仅在五档都有样本时才给结论。
- `--json` 输出便于二次加工。

三条刻意的"不许骗人"设计：

1. **收益解析不出来的记录跳过，不当成 0%** —— 后者会把统计悄悄拉向中性。
2. **样本少于 20 条时报告自己标注「这些比率基本是噪音」**，不等用户去数。
3. **报告结尾写明这不是回测、不是策略业绩**：持有窗口重叠、无仓位管理、未计交易
   成本，样本可能有选择偏差。

指标口径参考 [Vibe-Trading](https://github.com/HKUDS/Vibe-Trading)（MIT）的
`agent/backtest/metrics.py`：胜率与盈亏按已完成交易计。**刻意不算夏普、不做年化**
——用离散且重叠的决策点去年化只会得到一个看着专业但没有意义的数字。

### 修复：中文标签 + 英文评级词被静默判成 Hold

`最终评级：Buy` 这种混排（`output_language` 为中文、模型却保留英文评级词）躲过了
原有的每一条规则：英文标签规则要求出现 `rating`；中文标签规则只认中文评级词；裸
英文词扫描按空白切分，`最终评级：Buy` 是**一个** token，`strip("*:.,")` 又剥不掉
全角冒号。结果静默落到默认值 Hold —— 决策评级被悄悄改写，报告里完全看不出来，
属于 #78 / #80 同类问题的未修变种。

这个漏洞会直接污染上面的绩效统计（评级分组全错），是在用真实数据验证报告时撞出来的。

### 测试

新增 `tests/test_performance.py`（16 例）与 4 例评级解析用例（含"中文评级词仍然
优先"的反向边界）。全量回归 277 passed。

---

## [0.5.1] — 2026-08-06

修复未来函数：在历史日期上跑分析时，数据层会把"今天"的数据当成分析日当天的事实。

上游 TradingAgents 把这类问题称作 backtesting date fidelity（#475），它的修复覆盖
yfinance 新闻。本仓库的 A 股数据层做了同类审计（AST 扫全部 15 个接口），发现**三个
函数收了日期参数却完全没有使用**：

| 函数 | 原行为 | 处理 |
|------|--------|------|
| `get_fund_flow` | 今天的分钟资金流 + 从**今天**回溯 20 个交易日 | 真正做时点截断 |
| `get_fundamentals` | 腾讯**实时** PE/PB/市值 | 数据源无历史时点值 → 明确告警 |
| `get_profit_forecast` | 同花顺**当前**一致预期 | 同上 |

在 2026-06-01 分析某只股票时，这三个接口都会返回今天的数据——而报告里完全看不出
被污染了，属于静默失败。

### 修复

- **`get_fund_flow` 做 point-in-time 截断**：历史日线逐行按 `curr_date` 过滤；
  复盘历史日期时**整段不取**实时分钟资金流（那只有"今天"的），并在正文说明为什么
  略去——不说的话用户会以为接口坏了。当天分析行为不变。
- **`get_fundamentals` / `get_profit_forecast` 加未来函数告警**：这两个数据源根本
  不提供历史时点值，补不上就必须说出来。正文顶部插入警告，点名分析日期，并给模型
  明确指令「**不得**把这些数字当作当天已知的事实」。当天分析不显示告警，不误伤正常用法。
- 新增 `_is_historical()` / `_snapshot_notice()` 两个共用工具，避免各处各写一套。

### 测试

新增 `tests/test_lookahead_guard.py`（15 例），含两类反向边界：**当天分析不能被误伤**
（实时资金流仍要取、不显示告警），以及**解析不了的日期不能当成历史**（否则误伤实时分析）。

---

## [0.5.0] — 2026-08-06

两项功能：分角色模型（可选），以及让情绪分析师看得到硬数据。

### 新增：分角色模型 `role_llms`（可选，默认关闭 · [#39](https://github.com/simonlin1212/TradingAgents-astock/issues/39)）

同一个模型分饰多空两角时倾向于自我附和，辩论就失去意义。现在可以给单个角色指定
另一家模型：

```python
"role_llms": {
    "bull": {"provider": "qwen", "model": "qwen-plus"},
    "bear": {"provider": "glm",  "model": "glm-4.6"},
}
```

- **默认空表 = 行为完全不变**。只有一家模型的用户不需要碰这一项。
- 16 个可配角色（7 分析师 + 多空 + 两个 Manager + 交易员 + 风险三方 + 质量门）。
- 角色名写错**当场报错**，不静默忽略——否则会以为配置生效了。
- 相同 provider + model **复用同一个实例**，写满 16 个角色也不会开 16 条连接。
- 换 provider 时不会把主 provider 的 `backend_url` 带过去（会把请求发到别家网关）。
- 与 `claude_agent_sdk` 订阅覆盖并用时，被单独配置的角色会绕开订阅按 token 计费，
  启动时**点名警告**是哪几个，不让人以为全程走订阅却在悄悄花钱。

### 改进：情绪分析师改为数据驱动（[#61](https://github.com/simonlin1212/TradingAgents-astock/issues/61)）

此前情绪分析师只有 `get_news` 一个工具，只能从新闻语气推断情绪——而"新闻听起来
利好"和"资金正在流出"完全可以同时发生。现在补上三样可核对的硬数据：

- `get_fund_flow` — 主力/超大单资金净流入（当日分钟级 + 近 20 日），情绪最硬的证据
- `get_stock_data` — 量价，用于判断情绪强度
- `get_hot_stocks` — 当日强势股与题材归因，用于判断热度与归因

提示词同步改为「先看资金、再看新闻」，并**强制报告出「资金面与消息面是否背离」**
——消息面正面而主力持续净流出（或相反）是这次改造最有价值的产出。必采清单从 5 项
扩到 9 项，取不到的数据要求如实标注，不许用新闻语气补一个编造的数字。

### 修复：mootdx 全表不可用时首次调用要卡几分钟（承接 [#90](https://github.com/simonlin1212/TradingAgents-astock/issues/90)）

v0.4.1 的修复引入了一个自己的问题：全部服务器都不可用时，会去跑 `bestip` 全表测速，
实测首次调用 **>170 秒**才报错。

- **协议层失败要正确计数**：这批服务器是在 `Quotes.factory` 建连握手时就抛错的，
  根本走不到"取数验证"那一步。只统计后者会让计数恒为 0，快速失败判断随之失效。
- **协议被拒时跳过 bestip**：bestip 用的是同一套协议、同一批主机，不可能有别的结果。
  只有内置表整体 TCP 都连不上（IP 老化，bestip 的本来用途）才跑它。
- **连续 3 台协议失败就停手**：连续失败指向协议层被拦（代理/防火墙），换服务器无解。
- 实测 **>170s → 18.7s**，第二次调用命中负缓存 0ms。报错文案也据实区分
  「端口连不上」与「协议被拒」，两者排查方向完全不同。

### 测试

新增 `tests/test_role_llms.py`（16 例）与 `tests/test_sentiment_data_tools.py`（5 例），
`tests/test_mootdx_server_selection.py` 补 3 例覆盖握手期失败这条真实路径。
其中两类断言值得单独说：**默认不配 role_llms 时每个角色仍走原来的 quick/deep**，
以及**分析师绑定的工具与图里 ToolNode 注册的工具必须一致**（不一致只会在真跑分析时炸）。

---

## [0.4.1] — 2026-08-06

三个 issue 的静默失败修复：报告被悄悄截断、mootdx 反复降级、Kimi 报看不懂的 401。

### 修复：mootdx 反复降级、永不恢复（[#90](https://github.com/simonlin1212/TradingAgents-astock/issues/90)）

`_probe_tdx()` 只做 TCP 握手就认定服务器可用，但实测内置服务器表里有相当一部分
**TCP 三次握手成功、通达信协议握手立刻被 RST**。旧逻辑挑中这种服务器后写进单例
钉死，于是之后每一次取数都失败、降级到新浪，而且永远不会重选——正是 issue 里
「一直调用不了数据反复降级」的表现。

- **选服务器要真取到数才算数**：TCP 探测降级为廉价预筛，之后必须真的拉到一根 K 线
  （`_tdx_client_works()`）才会被采用，否则换下一台。bestip / 裸 factory 两级 fallback
  同样要过这一关。
- **坏掉的服务器会被弃用**：所有 mootdx 调用统一走 `_mootdx_call()`，调用失败即丢弃
  当前 client，下一次重新选服务器，而不是一直钉在死服务器上降级。
- **全挂时快速失败**：全部服务器验证失败后记负缓存，5 分钟内直接报错，不再每次
  取数都把整张服务器表重探一遍（旧逻辑下这会把「取不到数」放大成「每个请求卡几十秒」）。
- 报错文案写明真实原因（端口能连上但协议取数失败 / 检查代理与防火墙对 TCP 7709 的拦截）。

### 修复：报告写到一半结束（[#91](https://github.com/simonlin1212/TradingAgents-astock/issues/91)）

撞的是**输出** token 上限，不是上下文上限，而返回值本身完全合法——没有任何提示，
用户只会以为模型没写完。

- **截断会明说**：回复因达到输出上限而停止时（Anthropic `stop_reason=max_tokens` /
  OpenAI 兼容 `finish_reason=length`）打出明确日志，并告诉你调哪个配置项。
- **新增 `max_tokens` 配置项**（环境变量 `TRADINGAGENTS_MAX_TOKENS`），已接到
  anthropic / openai 兼容 / google / azure 四条通道——此前 OpenAI 兼容通道根本不转发
  这个参数，配了也没用。
- **第三方模型不再被小兜底值截断**：走 `anthropic` 通道跑 Kimi 这类模型时，
  langchain-anthropic 认不出模型名，会落到一个很小的默认输出上限（1.5.x 是 4096，
  更早是 1024）。现在这类模型默认放宽到 8192。判据是「模型名是否 claude 开头」，
  所以 `claude-sonnet-4-5-20250929` 这种带日期的正规 ID 不会被误伤。

### 修复：接 Kimi 报 401 invalid x-api-key（[#89](https://github.com/simonlin1212/TradingAgents-astock/issues/89)）

README 的「方案 G」教用户设 `ANTHROPIC_AUTH_TOKEN`——**这个变量本项目从来不读**
（它是 Claude Code CLI 的约定）。照着配的用户，请求会发到 api.anthropic.com，
拿 Kimi 的 token 认证，报一句与 Kimi 无关的 401。

- **启动即报错**：用非 Claude 模型名走 `anthropic` 通道却没配端点时直接中止，
  并说明要设 `backend_url` / `ANTHROPIC_BASE_URL` 和 `ANTHROPIC_API_KEY`，
  以及 `ANTHROPIC_AUTH_TOKEN` 为什么不生效。
- **支持 `ANTHROPIC_BASE_URL` 环境变量**配置端点，不再只能写 config。
- README 中英文两版的 Kimi 配置段改正，并新增两条 FAQ。

### 测试

新增 `tests/test_mootdx_server_selection.py`（6 例）与 `tests/test_output_token_limit.py`
（13 例）：覆盖「TCP 通但协议不通的服务器必须跳过」「坏 client 失败后被弃用」
「全挂后快速失败不重探」「第三方模型拿到显式输出上限」「带日期的 Claude ID 不被误判」
「截断必须告警、正常收尾不告警」「缺端点时启动即报错」。

---

## [0.4.0] — 2026-07-31

新增：让节点走**个人 Claude Pro/Max 订阅额度**而非按 token 计费的 Anthropic API。
基于社区 PR [#86](https://github.com/simonlin1212/TradingAgents-astock/pull/86)
（感谢 [@kingxiaozhe](https://github.com/kingxiaozhe)）。默认关闭，行为不变。

### 新增：`claude_agent_sdk` provider（可选依赖 `[agentsdk]`）

此前项目对 Claude 只有 `anthropic` provider＝走 `ANTHROPIC_API_KEY` **按 token 计费**，
没有任何走订阅的通道。本版补上：经 Claude Agent SDK 调用本机已登录的 `claude`，
**消耗订阅额度，不产生 API 账单**。

- **两档覆盖**：`deep_think_provider_override` 只覆盖深度节点（Research / Portfolio
  Manager）；再加 `quick_think_provider_override` 则含 7 个工具分析师＝全节点走订阅。
  Web 侧栏三档（关闭 / 仅深度 / 所有节点）。
- **工具桥接**：分析师的 LangChain 工具桥接为 Agent SDK 进程内 MCP 工具，SDK 内部跑完
  ReAct 循环返回最终报告，LangGraph 视为完成，无需改图。
- **启动护栏**：检测到 `ANTHROPIC_API_KEY` 与订阅覆盖共存时**直接报错中止**——
  API key 优先级更高，留着它会悄悄走 API 计费。
- **撞额度自动降级**到配置的付费 provider（`agent_sdk_fallback_provider` / `_model`）。
- 仅供个人自用：消耗的是使用者自己账号的额度。

### 在 PR 基础上的四处改动

1. **模型默认值改用别名**。PR 默认 `claude-opus-4-8`，写死的完整 id 会随版本迭代过期
   （仓库 `model_catalog` 的 anthropic 条目就已停在 `4-6`）。改用 `claude` CLI 的
   `opus` / `sonnet` 别名——恒指向最新模型。完整 id 仍然支持。
   quick 节点默认给 `sonnet` 而非 `opus`：节点数量多（7 分析师 + 辩手），
   订阅按额度限流，全用 opus 很快撞上限。
2. **🔴 凭据失效不再静默降级到计费 provider**。原实现里认证失败会走
   `_SDKResultError` → 落进 `_FALLBACK_ERRORS` → 降级到按 token 计费的 provider。
   用户开订阅模式就是为了避免账单，token 一过期就悄悄开始计费——正是启动护栏 F-004
   想防的事，只是从启动时挪到了运行中。新增 `_AuthError`（**刻意不在** `_FALLBACK_ERRORS`
   里）+ `_looks_like_auth_failure()` 正向识别，报错里直接给出 `claude setup-token` 修复步骤。

   > 实测发现有必要：OAuth token 过期时 SDK 把它翻译成 `Claude Code returned an
   > error result: success`，`ResultMessage.subtype` 仍是 `"success"` 而 `is_error=True`，
   > 真正原因只出现在 `api_retry` 事件与助手文本里。用户看到那句话完全无从下手。
3. **未采纳 PR 夹带的全局默认变更**：PR 把 `llm_provider` 默认从 `openai/gpt-5.4`
   改成 `deepseek/deepseek-v4-pro`，那是贡献者个人偏好，会改变所有人的默认行为。
4. **未采纳 PR 的 `docs/codebase-context/` 与 `specs/`**（约 600 行贡献者自用的
   spec-driven 脚手架文档）。另外 PR 的 `factory.py` 基于较旧的 main，整体取用会
   **回退 v0.2.20 的 `openai_compatible` provider**——已改为只补 4 行路由，
   测试 `test_openai_compatible_is_routed_to_openai_client` 当场抓到了这个回退。

### 审计中又修的三处

- **`anthropic` 无法作为降级 provider（死结）**：原护栏检测到 `ANTHROPIC_API_KEY`
  就一律中止——留着 key 启动被拦，删掉 key 又会在撞额度真要降级时认证失败。
  改为在 **Agent SDK 子进程环境**里把该变量置空（`ClaudeAgentOptions.env`），
  父进程保留供降级使用，启动只告警不中止。
- **认证识别过宽（我引入的）**：原实现扫所有助手正文匹配 "invalid api key" 等词。
  工具分析师会复述桥接工具的失败原文——某个行情源自己的 key 失效时正文里就可能
  出现这些词，会被误判成订阅凭据失效并中止整轮分析。收窄为**只在合成错误消息**
  （`model == "<synthetic>"` 或带 `error` 字段）上匹配。
- **Web UI「所有节点」把深度模型复制给了 quick 节点**，覆盖掉 sonnet 默认值——
  7 个分析师 + 辩手全跑 opus 会让订阅额度烧得极快，且与文档所述矛盾。

- **401 只出现在 `ResultMessage` 时被漏判**：该路径会落进 `_SDKResultError`
  → `_FALLBACK_ERRORS` → **静默降级到计费 provider**，正好违背「不产生 API 账单」
  这条承诺。改为先判 `api_error_status == 401` 再走通用分支。
- **降级客户端没带 callbacks**：降级意味着开始计费，而统计/成本回调恰好在
  花钱的时候看不到这些调用。已把 callbacks 一并传入。
- **跨 provider 降级仍转发主 provider 的 `backend_url`**（如把 anthropic 请求发到
  MiniMax 网关）——显式指定另一家时改为不带端点，让其用自己的默认地址。

- **`(role, content)` 元组消息被静默清空**：`Reflector.reflect_on_final_decision()`
  传的正是 `[("system", ...), ("human", ...)]`，而消息解析只认 BaseMessage 与 dict，
  元组走 `getattr` 取不到字段 → 两条消息双双变空串 → SDK 收到空 prompt **却照常
  返回内容**，是「不报错的错答案」。quick 节点走订阅时这条路径是活的。

### 依赖

`[agentsdk]` 链路为 `claude-agent-sdk → mcp → httpx2`，**不碰 httpx**，与 mootdx 的
`httpx<0.26` 无冲突（`uv lock --dry-run` 实测通过）。与 #87 中被移除的 `[google]`
情况不同，无需单开 venv。PR 注释里「会与 mootdx 冲突」的说法已过时（mcp 已迁到 httpx2），一并订正。

### 测试

`pytest tests/` **214 passed / 1 skipped / 45 subtests**。新增认证失败识别、
`_AuthError` 不参与降级、报错可操作性三组断言。端到端实跑验证链路可达
（本机 OAuth token 已过期，正确地报出可操作错误而非静默降级）。

## [0.3.1] — 2026-07-31

修三个静默失败 + 合并两个社区 PR。无破坏性变更。

### 修复：`uv sync` 因 `[google]` extra 的无解冲突而对所有人失败（#87）

感谢 [@jakeparkcolde](https://github.com/jakeparkcolde) 的高质量报告与复现步骤。

`langchain-google-genai>=4.0.0` 要求 `google-genai>=1.53.0`，而该区间内**每一个**
google-genai 版本都要求 `httpx>=0.28.1`；`mootdx`（核心 A 股数据源）钉死
`httpx>=0.25,<0.26`。**没有任何版本组合能同时满足——冲突是结构性的，不是坏 pin。**

真正的杀伤力在于：**uv 构建的是覆盖所有 extra 的 universal lock**，所以只要这个
extra 存在，`uv sync` 就对**所有人**失败，包括从不用 Gemini 的用户。

- **移除 `[google]` extra**。留空更糟——`pip install .[google]` 会静默什么都不装，
  用户以为装好了，直到运行期才炸。
- `google_client.py` 导入失败时抛出**带可直接执行安装命令**的 `ImportError`，
  而不是裸 `ModuleNotFoundError`（沿用 v0.2.17 处理 fpdf 的做法）。
- `tests/test_google_api_key.py` 改为缺依赖时 skip——此前它会让 `pytest tests/`
  **在收集阶段整体中断**，一个测试都跑不了。
- `mootdx` 下限 `0.10.0` → `0.11.7`：放宽会让 uv 回溯到要求 `pandas<1.3.5` 的
  远古版本，报出与真实成因无关的 pandas 冲突，把真正的 httpx 问题盖住。

实测 `uv lock` 由失败转为成功解析。

### 修复：A 股历史决策回报永远查不到，记忆闭环从未生效（社区 PR #84）

感谢 [@wangyuxun6699](https://github.com/wangyuxun6699)。

`_fetch_returns` 把裸六位码直接传给 yfinance，而同一函数里 benchmark 用的却是
`"000300.SS"`（带后缀）。yfinance 对裸码返回空表 → `len(stock) < 2` → 返回 None
→ **记忆条目永久 pending**，且被 `except Exception` 吞成 warning。
实测：`600519` → 0 行、`600519.SS` → 10 行；`000001` → 0 行、`000001.SZ` → 10 行。
等于 agent「从历史决策学习」的能力对 A 股一直是空转。

新增 `_normalize_yfinance_ticker()`：沪市 → `.SS`、深市 → `.SZ`，
`SH600519` / `600519.SH` 等写法一并归一，非 A 股代码原样返回。

**本版在 PR 基础上补了一条**：Yahoo **完全不覆盖北交所**（实测 `920002` 的裸码 /
`.BJ` / `.SS` / `.SZ` 四种写法全部返回空表）。PR 正确地没有硬造后缀，但这样北交所
条目会每次运行白发一次网络请求、且永远 pending 不给任何理由。新增
`_is_unsupported_by_yfinance()` 直接短路并明确写清原因。

> **Round-2 清理**：记忆反思已改走 A 股数据源后，上述两个 helper 在生产路径上再无
> 调用方，仅被测试保活；已删除（见 Round-2 bugfix）。

### 修复：DeepSeek V4 / MiniMax M2.x 结构化输出不稳定（社区 PR #83）

感谢 [@wangyuxun6699](https://github.com/wangyuxun6699)。

两类模型的结构化输出各自会失败、退回自由文本 —— 多一次模型调用，且
Research Manager / Trader / Portfolio Manager 的输出格式不稳定，中文评级更容易
解析失败：**DeepSeek V4 / reasoner** 不接受 LangChain 结构化输出默认发送的
`tool_choice`；**MiniMax M2.x** 则是不支持 json_mode，且 `<think>` 内容会污染
最终报告。（⚠️ PR 描述把两者都写成「不接受 tool_choice」，但其代码与测试明确
声明 MiniMax `supports_tool_choice=True`——以代码为准，本地无 MiniMax key 无法
实测，不据未验证的描述改动行为。）

**这正是 v0.2.19「中文 TRADING SIGNAL 恒为 HOLD」的上游成因**：v0.2.19 修的是症状
（让 `parse_rating` 认中文），本版修的是病因（结构化输出为什么会失败）。

新增模型能力声明表 `llm_clients/capabilities.py`（精确 ID + 前缀匹配，未知模型
保持宽松默认）：对 DeepSeek V4/reasoner 抑制不兼容的 `tool_choice` 并保留 Schema
工具绑定（不再直接降级为自由文本），对 MiniMax M2.x 关闭 json_mode 并启用
`reasoning_split` 防止 `<think>` 污染最终报告。带前向兼容测试（`MiniMax-M3`
不继承 M2 行为、DeepSeek V3 家族不被 V4 结论误伤）。

本版在 PR 基础上收紧两处：① `^deepseek-v\d` 会把 catalog 在售的 V3.2 与未来所有
版本一并归类为「不接受 tool_choice」，而该结论只在 V4/reasoner 上实测过，被误伤的
型号反而更容易退回自由文本——收窄为 `^deepseek-v4(?:$|[.-])`，与作者自己给 MiniMax
写的 `^MiniMax-M2(?:$|[.-])` 同一把尺子。② 抑制 `tool_choice` 原用 `setdefault`，
调用方显式传入时会被保留、能力声明形同虚设——改为 pop + 覆盖并 warning。

### 测试

`pytest tests/` **169 passed / 1 skipped / 45 subtests**，且现在**开箱即可运行**
（此前缺 langchain-google-genai 会导致收集阶段整体中断）。

## [0.3.0] — 2026-07-24

明确项目定位为「框架的工程实现与研究复现」，并**移除可执行价位相关能力**。**有破坏性变更**（见下）。

### 移除（破坏性）
- **可执行价位能力整体删除**：Trader 与 Portfolio Manager 现在只输出方向 / 评级与理由，框架内**不再存在**建仓价、止损位、仓位、目标价这类输出。
  - 删除字段：`TraderProposal.entry_price` / `.stop_loss` / `.position_sizing`、`PortfolioDecision.price_target`。
  - 提示词同步收紧：仅删字段挡不住模型把价位写进散文字段，因此系统提示与 `executive_summary` / `reasoning` 的字段描述都显式要求不给价位。
  - 渲染函数不再输出 `**Entry Price**` / `**Stop Loss**` / `**Position Sizing**` / `**Price Target**` 四节；其余 markdown 格式不变。
  - **这是删除而不是开关**——不提供 opt-in 配置项。需要这类能力的使用者可自行 fork 添加（Apache-2.0 允许），并自行承担相应责任。
  - **升级影响**：依赖 `TraderProposal.entry_price` 等字段的下游代码需自行调整。
- **`ResearchPlan.strategic_actions`** 的字段描述去掉「including position sizing guidance」。

### 移除
- **`examples/cases/` 下的 3 份个股分析报告**（含具体建仓价 / 止损 / 目标价）。本仓库不再随代码分发针对具体证券的分析报告或评级结论；`examples/run_cases.py` 保留为可自行运行的脚本，运行结果由使用者自行保管。
- `DEV_LOG.md` / `CHANGES_FROM_UPSTREAM.md` 的 E2E 记录改为脱敏样本，只保留工程指标（耗时 / AI message 数 / 链路通过），移除个股评级与分析结论。

### 文档
- README 新增「项目定位」章节：说明这是 [arXiv 2412.20138](https://arxiv.org/abs/2412.20138) 框架的工程实现，用于研究与教学；不提供投资服务；模型与数据由使用者自备、产出归使用者所有。

### 测试
- 新增 `TestExecutionLevelsFlag`：锁定「默认 schema 无价位字段 / 开启后有 / 默认提示词禁止给价位 / 开启后要求给价位 / 默认渲染不含价位」五条。
- 全量 164 passed + 48 subtests passed。

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
