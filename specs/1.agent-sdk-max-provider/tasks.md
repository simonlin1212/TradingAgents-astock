# Agent SDK Max Provider (POC) — 任务清单

## 任务版本

| 日期 | 版本 | 说明 |
| ---- | ---- | ---- |
| 2026-07-19 | v1 | 初始任务 |
| 2026-07-19 | v2 | 采纳 Codex 10.6:单测分散进各实现任务、补 conftest/.env.example/codebase-context 波及面、T-001 只留 pyproject、补依赖与主/fallback 配置契约 |

## 项目信息

- 项目名: tradingagents-astock
- 架构类型: 单体应用(Python 多 Agent 框架)
- specs 路径: specs/1.agent-sdk-max-provider/

## 任务列表

### 功能 1: provider 客户端与适配器

- [x] T-001: `pyproject.toml` 新增可选依赖 `[agentsdk] = ["claude-agent-sdk>=..."]`(仅打包,参照 `[google]`)~10min
- [x] T-002: 新建 `claude_agent_sdk_client.py`——`ClaudeAgentSDKClient` + `AgentSDKChatModel` 适配器(**同一个类一并交付**):顶部导入守卫(F-007)、`CLAUDE_CODE_OAUTH_TOKEN` 认证+缺失提示、`query()` 禁用内置工具/`max_turns=1`/透传 system、消息↔prompt 映射、`invoke()` 出 `AIMessage`+`normalize_content`、`with_structured_output(schema)` 出 Pydantic 实例、`bind_tools` 抛 `NotImplementedError`(F-006)、`__init__` 接收 `fallback_spec` 的**降级 seam**(F-008,先留接口,逻辑在 T-006)。**自带单测**:invoke→AIMessage+normalize、结构化输出、bind_tools 抛错、OAuth 缺失提示、system/message 映射 ~2h

### 功能 2: 配置、路由、护栏、降级

- [x] T-003: `default_config.py` 加 4 项:`deep_think_provider_override` / `agent_sdk_model`(缺省 `claude-opus-4-8`)/ `agent_sdk_fallback_provider` / `agent_sdk_fallback_model`(F-003/F-008)~15min
- [x] T-004: `factory.create_llm_client` 加 `claude_agent_sdk` 分支并透传 `fallback_spec` + **自带单测**(路由指向 `ClaudeAgentSDKClient`)~20min
- [x] T-005: `trading_graph.py:94-108` 接线——override 生效时以 `agent_sdk_model` + `fallback_spec` 构造 `deep_client`;`__init__` 启动护栏(override 生效且存在 `ANTHROPIC_API_KEY` → 抛错中止,F-004)+ **自带单测**(护栏拦截、接线只选 provider 不含降级逻辑)~40min
- [x] T-006: 在 T-002 的 seam 上实现降级(F-005):捕获 quota/失败异常 → 惰性 `create_llm_client(**fallback_spec).get_llm()` 重试一次 + WARNING + **自带单测**(降级仍产出 `PortfolioDecision`;测试内 `monkeypatch.delenv("ANTHROPIC_API_KEY")` 避开 F-004,AC-003/AC-007)~50min

### 功能 3: 集成测试与文档

- [x] T-007: 集成/回归测试——factory 路由端到端、F-007 默认安装不带 SDK + 缺依赖提示(AC-005)、启用 override 测试正确 `monkeypatch.delenv` 处理 `conftest.py` 注入的 placeholder key(AC-007)、**不启用时 `.venv/bin/python -m pytest tests/ -v` 全绿且行为不变(AC-004)**~1h
- [x] T-008: 文档同步——README/`CLAUDE.md`(新 provider、`claude setup-token` 步骤、`[agentsdk]` 安装、"仅个人自用/共享额度/无 SLA/护栏"限制)+ `.env.example` 加 `CLAUDE_CODE_OAUTH_TOKEN` 及"与 `ANTHROPIC_API_KEY` 不可共存"说明(AC-006)+ `docs/codebase-context/{01-overview,02-directory,06-core-modules}.md` 增量(新 extra / 新客户端文件 / 新 provider)~45min
- [ ] T-009 **[待用户执行]**: 本地端到端冒烟(需本人 claude setup-token 登录 Max,无法代跑;步骤见 README「用 Max 订阅额度」)——`claude setup-token` → 启用 override → 跑一次真实分析,确认 research_manager/portfolio_manager 走 Agent SDK 且订阅额度被消耗、`ANTHROPIC_API_KEY` 未共存(AC-001/AC-002)~30min

> 无部署任务:库内 provider,无 staging/部署形态,按规则不生成部署任务。

## 依赖关系

- T-002 依赖 T-001(extra 声明后再写守卫与实现)
- T-004 依赖 T-002、T-003(路由指向客户端 + 传 fallback_spec 配置)
- T-005 依赖 T-003、T-004(接线用配置 + 护栏)
- T-006 依赖 T-002、T-003(降级在适配器 seam 上 + fallback 配置)
- T-007 依赖 T-002、T-004、T-005、T-006(集成需全部实现就位)
- T-008 依赖 T-002(codebase-context 需反映真实新增文件)
- T-009 依赖 T-005、T-006、T-008(冒烟需接线+降级+setup-token 文档)

无环:T-001→T-002→{T-004→T-005, T-006, T-008}→T-007;T-009 收口。

## 功能点覆盖(自检)

F-001→T-002 | F-002→T-002 | F-003→T-003+T-005 | F-004→T-005 | F-005→T-006 | F-006→T-002 | F-007→T-001+T-002+T-007 | F-008→T-002+T-003+T-004

## 风险点

- **[需实测]** `claude-agent-sdk` 确切包名、`query()` 签名、结构化输出 API、quota/限流异常类型以实际安装版本为准——T-002/T-006 实现前先跑 SDK 探针,不照文档臆测。
- **[政策]** 官方 SDK 计费/订阅规则仍在变(2026-06 曾调整一次);仅个人自用,发布给他人须另取 Anthropic 批准——写入文档警示。
- **[额度]** 订阅额度与网页版/Claude Code 共享、按周动态限流、无 SLA——F-005 降级必须,不能省。
- **[护栏×测试]** `tests/conftest.py:31` 给所有测试注入 `ANTHROPIC_API_KEY=placeholder`,会触发 F-004;启用 override 的测试须 `monkeypatch.delenv`(已并入 T-006/T-007),否则误拦。
- **[配置陷阱]** 默认 `deep_think_llm=deepseek-v4-pro`,主 provider 必须用独立 `agent_sdk_model`、fallback 必须用独立 provider+model,否则模型串错配(已由 F-008/T-003 处理)。
