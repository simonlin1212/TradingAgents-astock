# 目录结构

## 目录树

```text
tradingagents/
├── agents/                 # Agent 角色与工具
│   ├── analysts/           #   7 个 Analyst（市场/情绪/新闻/基本面 + 政策/游资/解禁）
│   ├── researchers/        #   Bull/Bear 多空研究员
│   ├── risk_mgmt/          #   激进/保守/中立 三方风险辩论
│   ├── managers/           #   research_manager / portfolio_manager
│   ├── trader/             #   trader（交易提案）
│   ├── utils/              #   Agent 状态、工具集、记忆、结构化输出
│   ├── quality_gate.py     #   质量闸门
│   └── schemas.py          #   Pydantic 结构化 schema
├── dataflows/              # 数据层（vendor 直连 HTTP）
│   ├── a_stock.py          #   A 股 vendor（所有 A 股数据入口，含东财节流 _em_get）
│   ├── interface.py        #   vendor 路由与 fallback
│   ├── utils.py            #   safe_ticker_component 安全边界 + 中文 ticker 解析
│   ├── alpha_vantage*.py   #   Alpha Vantage vendor（美股备选）
│   ├── y_finance.py        #   yfinance vendor（美股备选）
│   └── config.py
├── graph/                  # LangGraph 编排
│   ├── trading_graph.py    #   TradingAgentsGraph 主入口
│   ├── setup.py            #   图节点装配
│   ├── conditional_logic.py#   条件跳转（辩论轮次控制）
│   ├── checkpointer.py     #   sqlite 检查点
│   ├── propagation.py / reflection.py / signal_processing.py
├── llm_clients/            # 多模型客户端（工厂模式）
│   ├── factory.py          #   create_llm_client 入口
│   ├── claude_agent_sdk_client.py  # 个人 Max 订阅 provider(可选 [agentsdk])
│   ├── {openai,anthropic,google,azure}_client.py / base_client.py
│   ├── model_catalog.py / validators.py
└── default_config.py       # 全局默认配置
web/                        # Streamlit Web UI
├── app.py / launch.py / runner.py / history.py / progress.py / pdf_export.py
└── components/             #   sidebar / progress_panel / report_viewer
cli/                        # CLI（Typer）
├── main.py / config.py / models.py / utils.py / stats_handler.py / announcements.py
tests/                      # pytest（test_*.py）
issues/                     # GitHub Issue 归档
```

## 目录职责

| 目录 | 职责 | 典型文件 |
| ---- | ---- | ---- |
| tradingagents/agents/analysts | 各分析师角色的 prompt 与工具编排 | market_analyst.py, policy_analyst.py |
| tradingagents/agents/utils | Agent 共享：状态、工具集、记忆、结构化 | agent_utils.py, memory.py, structured.py |
| tradingagents/dataflows | 所有数据获取与 vendor 路由 | a_stock.py, interface.py, utils.py |
| tradingagents/graph | LangGraph 图装配与执行 | trading_graph.py, setup.py |
| tradingagents/llm_clients | 多提供商 LLM 客户端工厂 | factory.py, model_catalog.py |
| web/ | Streamlit 前端 | app.py, runner.py |
| cli/ | 命令行前端 | main.py |

## 文件清单（供增量扫描对比新增/删除）

| 文件 | 所属轮次 |
| ---- | ---- |
| pyproject.toml / README.md | 1 |
| tradingagents/default_config.py | 1 |
| tradingagents/graph/trading_graph.py | 3 |
| tradingagents/graph/setup.py | 3 |
| tradingagents/dataflows/interface.py | 4 |
| tradingagents/dataflows/a_stock.py | 4 |
| tradingagents/agents/schemas.py | 5 |
| tradingagents/agents/utils/agent_states.py | 5 |
| tradingagents/agents/analysts/*.py | 6 |
| tradingagents/llm_clients/factory.py | 6 |
| tradingagents/dataflows/utils.py | 7 |
