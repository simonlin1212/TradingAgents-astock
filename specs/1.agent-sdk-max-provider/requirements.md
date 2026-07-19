# Agent SDK Max Provider (POC) — 需求规格

## 概述

新增一个 `claude_agent_sdk` LLM provider,经 Claude Agent SDK 调用、消耗**个人 Claude Max/Pro 订阅额度**而非 Anthropic API 计费。POC 范围:仅把结构化决策节点(`deep_thinking_llm` = research_manager + portfolio_manager)可选路由到该 provider,LangGraph 与 7 个工具 Analyst 一行不动。

## 项目信息

- 项目名: tradingagents-astock
- 架构类型: 单体应用(Python 多 Agent 框架,LangChain + LangGraph)

## 需求版本

| 日期 | 版本 | 说明 |
| ---- | ---- | ---- |
| 2026-07-19 | v1 | 初始需求(经 Codex 对抗审查修正后) |

## 用户故事

- 作为持有 Claude Max 的**个人自用**开发者,我想让框架的结构化决策节点走 Max 订阅额度,以省下这部分 Claude API token 费,同时不改动现有工具 Analyst 与 LangGraph 编排。

## 背景与可行性依据(已确认)

- 官方支持:Claude Agent SDK / `claude -p` 会消耗用户的 Pro/Max 订阅额度,且明确覆盖"在自己的项目里用 Agent SDK"(个人自用不需 Anthropic 额外批准;仅"做成给他人用、代路由他人订阅凭证的产品"才需批准)。
- 认证机制:本机 `claude /login` 或无头 `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN`;**环境中若存在 `ANTHROPIC_API_KEY` 会优先并悄悄变回 API 计费**,必须护栏拦截。
- Agent SDK 原生支持结构化输出(JSON Schema / Pydantic,校验失败自动重试),满足 research_manager / portfolio_manager 的 `with_structured_output` 需求。
- 代码实测:`deep_thinking_llm` 仅供 research_manager + portfolio_manager,**不 `bind_tools`、不进 ToolNode**——是最干净的接入面(`tradingagents/graph/setup.py:107,114`)。

## 功能需求

1. [F-001] 新增 `claude_agent_sdk` provider,经 `claude-agent-sdk` 发起调用,认证走 `CLAUDE_CODE_OAUTH_TOKEN`,消耗 Max 订阅额度。
2. [F-002] 该 provider 的 `get_llm()` 返回一个 **LangChain `BaseChatModel` 兼容对象**,至少支持 `.invoke(messages)` 返回 `AIMessage`(纯文本节点)与 `with_structured_output(schema)` 返回可 `.invoke()` 出 Pydantic 实例的链(结构化节点)。POC **不要求** `bind_tools`。
3. [F-003] 通过 config 开关控制:仅 `deep_thinking_llm`(research_manager + portfolio_manager)可选走该 provider;`quick_thinking_llm` 及 7 个工具 Analyst 保持现状不变。该 provider **使用自己的 Claude 模型 id**(`agent_sdk_model`,如 `claude-opus-4-8`),**不得复用默认的 `deep_think_llm=deepseek-v4-pro`**(否则把 deepseek 模型串当 Claude 模型)。
4. [F-004] 护栏——启用该 provider 时,启动阶段若检测到 `ANTHROPIC_API_KEY` 存在,明确报错并中止(默认策略,防止悄悄回退 API 计费)。
5. [F-005] 护栏——调用失败或撞订阅额度(quota/限流错误)时,自动降级到 fallback,**fallback 使用自己的 provider+model**(`agent_sdk_fallback_provider`/`agent_sdk_fallback_model`,缺省回落到现有 `llm_provider`+`deep_think_llm`),**不得把 Claude 模型串传给 DeepSeek**;不中断整轮分析,记录一条 WARNING。
6. [F-006] 边界保护——该 provider 的适配器若被误用于需要 `bind_tools` 的场景,须抛出清晰错误而非静默产生错误行为。
7. [F-007] `claude-agent-sdk` 作为**可选依赖**(如 `[agentsdk]` extra),`pip install -e .` 默认不装,避免污染默认安装(参照现有 `[google]` 模式);未安装时导入守卫给出可读提示。
8. [F-008] **主/fallback 完整配置契约**:主 provider(model)与 fallback(provider+model+base_url)各自的配置有明确归属;fallback 配置在 `ClaudeAgentSDKClient` **构造时注入**,降级逻辑**自包含于客户端内部**,不外溢改动 `trading_graph` 接线——避免 T-006/T-007 越界改同一段代码导致提交归属失真。

## 非功能需求

- 适用范围: **仅个人自用**;仅覆盖 Claude 模型;不适合有 SLA 的定时/生产批处理(订阅额度与网页版/Claude Code 共享、按周动态限流、无 SLA)。
- 兼容性: 不改动 LangGraph 编排、ToolNode、7 个工具 Analyst 与 `quick_thinking_llm` 链路;默认配置行为不变(不启用即完全等价于现状)。
- 安全: 遵循 `.claude/rules/security.md`;OAuth token 走环境变量,禁止硬编码、禁止入日志。

## 验收标准

- [ ] [AC-001] 设置 `CLAUDE_CODE_OAUTH_TOKEN`、config 启用后,跑一次完整分析,research_manager 与 portfolio_manager 的调用**经 Agent SDK 完成**,且订阅端可见额度消耗(本机验证)。
- [ ] [AC-002] 环境同时存在 `ANTHROPIC_API_KEY` 时,启动被 F-004 护栏拦截(报错/告警),不产生 API 账单。
- [ ] [AC-003] 模拟 Agent SDK 调用抛 quota/失败错误时,F-005 降级到 deepseek,整轮分析仍产出 `PortfolioDecision`,日志含降级 WARNING。
- [ ] [AC-004] 不启用该 provider 时,`.venv/bin/python -m pytest tests/ -v` 全绿,行为与现状完全一致。
- [ ] [AC-005] `pip install -e .`(不带 extra)不引入 `claude-agent-sdk`;未安装时启用该 provider 给出可读的依赖缺失提示(需有测试承接)。
- [ ] [AC-006] `.env.example` 含 `CLAUDE_CODE_OAUTH_TOKEN` 及"与 `ANTHROPIC_API_KEY` 不可共存"说明。
- [ ] [AC-007] 启用 override 的 F-004/F-005 测试正确处理 `tests/conftest.py` 注入的 `ANTHROPIC_API_KEY=placeholder`(测试内 `monkeypatch.delenv`),不被护栏误拦、能走到降级路径。

## 依赖

- `claude-agent-sdk`(Python 包,可选依赖)
- Claude Code CLI(用户本机 `claude setup-token` 生成 OAuth token)
- 现有 `langchain-core`(BaseChatModel / AIMessage 类型)

## 开放问题

- [已答] 是否个人自用? → 是,仅本地自用(公开发布给他人须另取 Anthropic 批准,本 POC 不涉及)。
- [已答] 首版是否处理工具 Analyst? → 否,仅 `deep_thinking_llm` 两个结构化节点。
- [待确认-非阻塞] fallback provider 默认取 config 里的 `llm_provider`(deepseek)还是单独指定?建议:单独 config 项 `agent_sdk_fallback_provider`,缺省回落到现有 quick/deep 的 provider。
- [待确认-非阻塞] quota/限流错误的具体异常类型以 `claude-agent-sdk` 实际抛出为准,实现时按其错误类型匹配(设计已留降级钩子)。
