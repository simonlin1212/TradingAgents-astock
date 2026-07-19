# 核心模块

## Agent 角色（写新 Agent 前先查是否已有可复用）

### Analysts（7 个，agents/analysts/）

| 角色 | 文件 | 职责 | 来源 |
| ---- | ---- | ---- | ---- |
| 市场分析师 | market_analyst.py | 技术面/行情 | 原版 |
| 情绪分析师 | social_media_analyst.py | 社媒情绪 | 原版 |
| 新闻分析师 | news_analyst.py | 新闻面（含 ticker 校验防概念词中断） | 原版 |
| 基本面分析师 | fundamentals_analyst.py | 财报/估值 | 原版 |
| 政策分析师 | policy_analyst.py | A 股政策解读 | A 股特化 |
| 游资追踪 | hot_money_tracker.py | 龙虎榜/游资席位 | A 股特化 |
| 解禁监控 | lockup_watcher.py | 限售解禁 | A 股特化 |

### 辩论与决策

| 角色 | 文件 | 职责 |
| ---- | ---- | ---- |
| Bull Researcher | researchers/bull_researcher.py | 多头论点 |
| Bear Researcher | researchers/bear_researcher.py | 空头论点 |
| Aggressive/Conservative/Neutral Debator | risk_mgmt/*.py | 三方风险辩论 |
| Research Manager | managers/research_manager.py | 汇总研究 → ResearchPlan |
| Portfolio Manager | managers/portfolio_manager.py | 终裁 → PortfolioDecision |
| Trader | trader/trader.py | 交易提案 → TraderProposal |

## Agent 共享工具（agents/utils/）

| 模块 | 职责 | 位置 |
| ---- | ---- | ---- |
| agent_utils.py | Agent 通用辅助 | agents/utils/agent_utils.py |
| agent_states.py | LangGraph 状态定义 | agents/utils/agent_states.py |
| memory.py | 交易记忆（落盘 trading_memory.md） | agents/utils/memory.py |
| structured.py | 结构化输出解析 | agents/utils/structured.py |
| *_tools.py | 数据工具封装（见 04-api-routes） | agents/utils/ |
| quality_gate.py | 质量闸门校验 | agents/quality_gate.py |

## 图编排（graph/）

| 模块 | 职责 | 关键符号 |
| ---- | ---- | ---- |
| trading_graph.py | 主入口类 | `TradingAgentsGraph`（:58）, `propagate`（:301）, `process_signal`（:465） |
| setup.py | 节点/边装配 | `GraphSetup.setup_graph`（:29） |
| conditional_logic.py | 辩论轮次条件边 | — |
| checkpointer.py | sqlite 检查点 | — |
| signal_processing.py / propagation.py / reflection.py | 信号处理 / 状态传播 / 反思 | — |

## LLM 客户端（llm_clients/，工厂模式）

| 模块 | 职责 |
| ---- | ---- |
| factory.py | `create_llm_client(...)`（:11）统一入口，按 provider 分发 |
| base_client.py | 客户端基类 |
| openai_client / anthropic_client / google_client / azure_client | 各提供商实现 |
| claude_agent_sdk_client | 个人 Claude Max 订阅 provider(经 Agent SDK,仅 deep 节点,可选 [agentsdk];含 F-004 护栏 + F-005 降级) |
| model_catalog.py / validators.py | 模型目录 / 参数校验 |

> provider 默认 deepseek（default_config：deep_think=deepseek-v4-pro, quick_think=deepseek-chat）。Google 需可选依赖 `[google]`。

## Web / CLI 模块

| 模块 | 职责 |
| ---- | ---- |
| web/runner.py | 驱动一次分析（连接 UI ↔ graph） |
| web/history.py / progress.py | 历史记录 / 进度（支持中断 resume） |
| web/pdf_export.py | 中文 PDF 导出（fpdf2） |
| web/components/{sidebar,progress_panel,report_viewer}.py | UI 组件 |
| cli/main.py | Typer app 入口 |
