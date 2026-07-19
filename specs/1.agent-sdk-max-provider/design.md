# Agent SDK Max Provider (POC) — 技术设计

## 设计版本

| 日期 | 版本 | 说明 |
| ---- | ---- | ---- |
| 2026-07-19 | v1 | 初始设计 |
| 2026-07-19 | v2 | 采纳 Codex 10.6 拆分审查:补主/fallback 配置契约、构造时注入降级 seam、补齐波及面(conftest/.env.example/codebase-context) |

## 项目架构

- 架构类型: 单体应用(Python 多 Agent 框架)
- 涉及层: LLM 客户端层(`tradingagents/llm_clients/`)、配置层(`default_config.py`)、编排接线层(`graph/trading_graph.py`)。**不涉及** `agents/`、`graph/setup.py` 编排、ToolNode、dataflows。

## 波及面(brownfield)

| 文件 | 改动性质 | 说明 |
| ---- | ---- | ---- |
| `tradingagents/llm_clients/claude_agent_sdk_client.py` | 新增 | 新 provider 客户端 + LangChain 兼容适配器 + 自包含降级 |
| `tradingagents/llm_clients/factory.py` | 修改 | `create_llm_client` 加 `claude_agent_sdk` 分支(`factory.py:37-52`) |
| `tradingagents/default_config.py` | 修改 | 新增 4 个配置项(`default_config.py:15-17` 旁) |
| `tradingagents/graph/trading_graph.py` | 修改 | `deep_client` 可选走新 provider + 启动护栏(`trading_graph.py:94-108`) |
| `pyproject.toml` | 修改 | 新增可选依赖 `[agentsdk]`(参照 `[google]`) |
| `tests/conftest.py` | **测试波及(Codex #8)** | `conftest.py:17,31` 给所有测试注入 `ANTHROPIC_API_KEY=placeholder`;启用 override 的测试须 `monkeypatch.delenv` 否则被 F-004 护栏误拦 |
| `.env.example` | **修改(Codex #9)** | 加 `CLAUDE_CODE_OAUTH_TOKEN` + "与 API_KEY 不可共存"说明 |
| `docs/codebase-context/{01-overview,02-directory,06-core-modules}.md` | **修改(Codex #10)** | 记录新 optional extra / 新客户端文件 / 新 provider,防波及面地图失真 |

现有 `deep_thinking_llm` 消费者:`create_research_manager`、`create_portfolio_manager`(`setup.py:107,114`),均无 `bind_tools`——接入面已锁定。

## 主/fallback 配置契约(F-008 — Codex #1/#2 核心修正)

**问题**:默认 `deep_think_llm="deepseek-v4-pro"`(`default_config.py:16`)。若切 Agent SDK 后复用它,会把 deepseek 模型串当 Claude 模型;降级到 DeepSeek 时又会把 Claude 模型串传给 DeepSeek。主与 fallback 的 model/provider 必须各自归属。

`default_config.py` 新增 4 项(默认关闭,不启用即完全等价现状):

| 配置项 | 默认 | 作用 |
| ---- | ---- | ---- |
| `deep_think_provider_override` | `None` | 置 `"claude_agent_sdk"` 时 deep 节点走新 provider;`None` 用现有 `llm_provider` |
| `agent_sdk_model` | `"claude-opus-4-8"` | **主 provider 用的 Claude 模型 id**(不复用 `deep_think_llm`) |
| `agent_sdk_fallback_provider` | `None`(→ `llm_provider`) | 降级目标 provider |
| `agent_sdk_fallback_model` | `None`(→ `deep_think_llm`) | 降级目标 model |

## 功能模块设计

### 模块 1: ClaudeAgentSDKClient + 自包含降级(新文件)

`tradingagents/llm_clients/claude_agent_sdk_client.py`,继承 `BaseLLMClient`,`get_llm()` 返回 LangChain `BaseChatModel` 兼容适配器 `AgentSDKChatModel`。

**导入守卫**:文件顶部 `try: import claude_agent_sdk except ImportError:` 置哨兵,`get_llm()` 时若未装抛可读提示(参照 v0.2.17 fpdf 守卫)。

**认证与调用**:读 `CLAUDE_CODE_OAUTH_TOKEN`(缺失抛提示先 `claude setup-token`);经 `query()` 约束成近似单次补全(禁用内置工具、`max_turns=1`、透传 system)。

**LangChain 适配器 `AgentSDKChatModel`**:
- `invoke(messages)` → `AIMessage` + `normalize_content`(`base_client.py`)。
- `with_structured_output(schema)` → 用 Agent SDK 原生结构化输出(JSON Schema/Pydantic + 自动重试)出 `schema` 实例。
- `bind_tools(...)` → `raise NotImplementedError`(F-006)。

**降级 seam(F-008/F-005,构造时注入 — 解决 Codex #2/#4)**:
`ClaudeAgentSDKClient.__init__` 接收 `fallback_spec={provider, model, base_url}`(由 factory/graph 传入)。`AgentSDKChatModel` 内部对 `invoke`/`with_structured_output().invoke` 包一层 try/except,捕获 quota/限流/调用异常 → **惰性用 `create_llm_client(**fallback_spec).get_llm()` 重建 fallback LLM 并重试一次** + WARNING。降级完全封在客户端内,`trading_graph` 不感知——避免 T-006 越界改 T-007 的文件。

### 模块 2: factory 路由

`factory.py:create_llm_client` 增加分支:`provider_lower == "claude_agent_sdk"` → `ClaudeAgentSDKClient(model, base_url, fallback_spec=..., **kwargs)`。放 anthropic 分支旁,保持签名/返回契约不变。

### 模块 3: 配置与护栏

见上"主/fallback 配置契约"。**启动护栏(F-004)**:`TradingAgentsGraph.__init__` 装配 `deep_client` 前,若 override 生效且 `os.getenv("ANTHROPIC_API_KEY")` 存在 → 抛错中止(默认策略)。

### 模块 4: trading_graph 接线

`trading_graph.py:94-108` 处:当 `deep_think_provider_override` 生效时,以 `create_llm_client("claude_agent_sdk", config["agent_sdk_model"], base_url, fallback_spec={provider: fallback_provider, model: fallback_model, base_url})` 构造 `deep_client`;`quick_client` 及其余不变。护栏在此调用。**接线只选 provider + 传配置,不含降级逻辑**(降级在模块 1 内)。

## 接口契约

- `create_llm_client(provider="claude_agent_sdk", model, base_url=None, fallback_spec=None, **kwargs) -> ClaudeAgentSDKClient`。
- `ClaudeAgentSDKClient.get_llm() -> AgentSDKChatModel`(鸭子兼容 `BaseChatModel`:`invoke`/`with_structured_output`;`bind_tools` 抛错)。
- `fallback_spec: {"provider": str, "model": str, "base_url": str|None}` — 构造时注入,客户端自持降级依据。
- 结构化契约:`with_structured_output(PortfolioDecision|ResearchPlan).invoke(prompt) -> 对应 Pydantic 实例`(schema 见 `agents/schemas.py`,不改)。

## 数据模型

无新增。复用 `agents/schemas.py` 的 `ResearchPlan` / `PortfolioDecision`。

## 安全考虑

- `CLAUDE_CODE_OAUTH_TOKEN` 走环境变量,禁硬编码/入日志(`.claude/rules/security.md`)。
- F-004 护栏是关键安全边界:防 `ANTHROPIC_API_KEY` 共存导致以为走订阅、实际产生 API 账单;默认"抛错中止"。
- 测试波及:`tests/conftest.py` 注入的 placeholder key 会触发 F-004——启用 override 的测试须显式 `monkeypatch.delenv("ANTHROPIC_API_KEY")`,否则误拦(Codex #8)。
- 不新增路径/文件写入,不触及 `safe_ticker_component`。

## 技术决策

| 决策 | 选项 | 理由 |
| ---- | ---- | ---- |
| 接入面 | 仅 deep_thinking_llm 两节点 / 全量 | 取前者:无 bind_tools/ToolNode,最小风险 |
| 主模型来源 | 复用 deep_think_llm / 独立 agent_sdk_model | 取独立:默认是 deepseek 模型串,复用即错(Codex #1) |
| fallback 配置 | 共用 deep 配置 / 独立 provider+model | 取独立:降级到 DeepSeek 不能传 Claude 模型串(Codex #1) |
| 降级位置 | 客户端构造时注入 seam / graph 接线处 | 取前者:自包含,不外溢改 trading_graph(Codex #2/#4) |
| API_KEY 共存 | 抛错 / 静默清除 | 取抛错:防悄悄计费 |
| 依赖 | 必装 / 可选 extra | 取可选 `[agentsdk]`:复用 `[google]` 模式 |
| bind_tools | 静默降级 / 抛错 | 取抛错:边界误用须显式暴露 |
