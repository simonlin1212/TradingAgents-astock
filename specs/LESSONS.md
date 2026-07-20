# LESSONS — 开发踩坑与架构决策

> 开发时必须参考。每条:结论 + 为什么 + 怎么应用。

## 1. claude-agent-sdk 的 httpx 冲突(必须可选依赖)

`claude-agent-sdk` 要求 `httpx>=0.28.1`,与 mootdx 锁的 `httpx==0.25.2` 冲突(和 `[google]` 同一类)。
- **为什么**:装 SDK 会把 httpx 顶到 0.28.1。
- **怎么应用**:放 `[agentsdk]` extra,`pip install -e .` 默认不装。**实测 mootdx 在 httpx 0.28.1 下运行时仍正常导入**(pin 只是元数据约束,非运行时崩),但为保守仍隔离为可选。

## 2. RateLimitEvent 语义 — 只有 status=='rejected' 才是硬失败(高危,两轮才修净)

`claude_agent_sdk` 的 `query()` 在限流**状态变化**时就 emit `RateLimitEvent`,`status ∈ {allowed, allowed_warning, rejected}`,**只有 `status=='rejected'` 是本次请求真被拒**。
- **为什么**:最初实现对**任何** `RateLimitEvent` 都抛 `_RateLimitHit` → 逼近额度出 `allowed_warning` 时订阅调用其实成功了却被误判失败、丢弃结果、**静默切到付费 provider**,违背"省订阅额度"的初衷。第一轮对抗审查只修了 `allowed_warning`,却把判断写成 `status=='rejected' or overage_status=='rejected'`——**埋了第二个坑**。
- **`overage_status` 千万别当降级信号**:它是**另一个维度**,描述"超额付费(overage)是否可用",与本次请求是否被服务无关。**组织禁用 overage 时,每个事件(含 `status=='allowed'`)都带 `overage_status='rejected'`/`overage_disabled_reason='org_level_disabled'`** → 若据此降级,则**100% 订阅调用被静默降级到付费 fallback,订阅永远用不上**(2026-07-19 本机真实冒烟才暴露,deepseek fallback 还会冒充 Claude 答错模型名,极隐蔽)。
- **怎么应用**:`_query` **只在 `status=='rejected'`** 时抛 `_RateLimitHit`,其余一律 `logger.warning` + `continue`(不丢后续 AssistantMessage/ResultMessage)。回归测试三连:`test_query_allowed_warning_does_not_fall_back` / `test_query_allowed_with_overage_rejected_does_not_fall_back` / `test_query_rejected_triggers_fallback`。
- **教训**:限流/配额 API 往往有多个正交状态位,别把"配置类"位(overage 是否开)误当"本次结果"位(request 是否被拒)。这类 bug 单测不出、只有真跑订阅才现形——**T-009 本机冒烟是必需的验收,不能省**。

## 3. F-004 护栏 — ANTHROPIC_API_KEY 抢占订阅计费

claude CLI 里 `ANTHROPIC_API_KEY` 优先级高于 `CLAUDE_CODE_OAUTH_TOKEN`,存在即悄悄走 API 计费。
- **怎么应用**:`TradingAgentsGraph.__init__` 在构造 deep_client **前**查 `os.environ`,启用 override 且存在 API_KEY → 抛错中止。
- **放弃的选项**:不在 `options.env` 里设 `ANTHROPIC_API_KEY=""` 显式清空——空字符串仍占认证槽位、可能让子进程用空 key 认证失败反破坏订阅路径。os.environ 护栏已充分。
- **测试注意**:`tests/conftest.py:31` 给所有测试注入 `ANTHROPIC_API_KEY=placeholder`,启用 override 的测试必须 `monkeypatch.delenv("ANTHROPIC_API_KEY")`,否则被护栏误拦。

## 4. output_format 形态是推断的,靠降级链兜底

`ClaudeAgentOptions.output_format` 类型仅标 `dict[str,Any]`。实现用 `{"type":"json_schema","schema":pydantic.model_json_schema()}`,结果读 `ResultMessage.structured_output`(字段确实存在,已核 SDK 源码),为 None 时 `json.loads(_extract_json(text))`。
- **怎么应用**:JSON 解析/校验异常**不**触发跨 provider 降级(不在 `_FALLBACK_ERRORS`),而是冒泡到框架 `invoke_structured_or_freetext` 的外层 → 同 llm free-text 重试。**T-009 本机冒烟必须验证 output_format 真实被 SDK 接受**;若不认,structured_output 会一直 None → 走文本 JSON 兜底。

## 5. Agent SDK query 是异步,deep 节点是同步 .invoke

`query()` 是 async 迭代器;Research/Portfolio Manager 通过 `.invoke(prompt_str)` / `with_structured_output(schema).invoke(str)` **同步直接调用**(纯字符串,不走 `prompt|llm` 管道,不 bind_tools)。
- **怎么应用**:适配器用鸭子类型(非 BaseChatModel 子类)即可;`_run_async` 桥接(无 loop→asyncio.run;有 loop→独立线程独立 loop,异常经 box 重抛)。

## 6. 降级封在客户端内,不外溢 graph

框架自带的 free-text 兜底在**同一个 llm** 上重试,所以跨 provider 降级(F-005)必须封在适配器内(`fallback_spec` 构造时注入,`_get_fallback` 惰性建)。graph 接线只选 provider + 传配置,不含降级逻辑——避免任务边界越界。

## 7. bind_tools 桥接 — 用"折叠工具循环"让工具分析师也走订阅(全节点)

分析师是 LangGraph **ReAct 模式**:`chain = prompt | llm.bind_tools(tools)`,LLM 返回 `tool_calls` → 外部 `ToolNode` 执行 → 回灌 → 循环,直到 `result.tool_calls==0` 才算完成。Agent SDK 相反,是**内部自跑工具循环、只吐最终结果**。两种范式冲突,原 POC 直接让 `bind_tools` 抛错、把分析师挡在订阅外。
- **关键洞察(不用改图)**:`bind_tools(tools)` 返回一个 `Runnable`(`_BoundAgentSDK`,必须是 Runnable 才能 `prompt | bound` 组合),其 `.invoke` 把 LangChain 工具桥接成 **Agent SDK 进程内 MCP 工具**(`create_sdk_mcp_server`+`@tool(name, desc, json_schema)`),让 SDK 内部把整段 ReAct 循环跑完,返回**没有 tool_calls 的最终报告**。LangGraph 见 0 tool_calls 即视分析师完成,外部 ToolNode 空转。**分析师的多轮外部循环被折叠进 SDK 内部循环。**
- **工具处理器**:LangChain 工具是同步、且打网络(mootdx 等),SDK handler 是 async——必须 `await asyncio.to_thread(lc_tool.invoke, args)`,否则阻塞 SDK 的 event loop。工具异常当**数据**返给模型(`[tool error] ...`),不崩。
- **取最终文本**:工具循环里中间轮会 emit 推理文本,不能把所有 AssistantMessage 文本拼起来当报告。`_query(prefer_result=True)` 取 `ResultMessage.result`(权威最终答);深度节点(单轮)仍用拼接文本、result 仅兜底。
- **降级自然汇流**:订阅撞额度时 fallback provider 的 `bind_tools(tools).invoke` 返回真 `tool_calls` → **重新汇入 LangGraph 正常外部 ToolNode 循环**,无需改图。
- **接线对称**:`quick_think_provider_override` 与 `deep_think_provider_override` 对称(`trading_graph._make_client`),护栏 F-004 对二者统一判断。两者都 on = 全节点走订阅。**2026-07-20 全节点真机跑通:7 分析师+辩论+2 深度节点 0 降级、报告全出内容。**
