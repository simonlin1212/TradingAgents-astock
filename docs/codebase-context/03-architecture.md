# 架构设计与模块关系

## 分层结构

```text
前端层  cli/ (Typer)  |  web/ (Streamlit)
    ↓ 构造 config + 调用
编排层  graph/TradingAgentsGraph  ← LangGraph 状态图
    ↓ 节点执行
Agent 层  analysts → researchers(Bull/Bear) → risk_mgmt(三方) → managers → trader
    ↓ 调用工具
工具层  agents/utils/*_tools.py（core_stock / fundamental / news / signal / technical）
    ↓ 经 vendor 路由
数据层  dataflows/interface.route_to_vendor → a_stock / alpha_vantage / yfinance
    ↓ 直连 HTTP/TCP
外部源  mootdx(TCP) · 东财 · 腾讯 · 新浪 · 同花顺 · 财联社 · 百度
```

## 启动链路

1. `cli/main.py:app`（Typer）或 `web/launch.py:main`（Streamlit）读取用户输入与 `.env`
2. 合并 `tradingagents/default_config.py` 默认配置 → 实例化 `graph/trading_graph.py:TradingAgentsGraph.__init__`（`trading_graph.py:61`）
3. `TradingAgentsGraph` 内 `GraphSetup.setup_graph`（`graph/setup.py:29`）装配 LangGraph 节点与条件边；`_create_tool_nodes`（`trading_graph.py:163`）绑定各 Agent 可用工具
4. `propagate(company_name, trade_date)`（`trading_graph.py:301`）→ `prepare_graph_run` → `_run_graph` 驱动状态图执行
5. `finalize_graph_run` / `process_signal`（`trading_graph.py:465`）产出最终决策并落盘报告

## 关键机制

- **vendor 路由 + fallback**：`dataflows/interface.py:route_to_vendor`（`interface.py:202`）按 `config["data_vendors"]` / `tool_vendors` 选主 vendor，失败自动降级到其余可用 vendor（`get_vendor` → `VENDOR_METHODS` 映射表）
- **东财限流**：所有 eastmoney 端点统一走 `a_stock.py:_em_get`（模块级时间戳串行 + 随机抖动 + 复用 Session）；新增东财端点必须走此入口
- **辩论轮次控制**：`graph/conditional_logic.py` 依据 `max_debate_rounds` / `max_risk_discuss_rounds` 决定 Bull/Bear 与三方风险辩论的循环边
- **检查点续跑**：`graph/checkpointer.py` + `checkpoint_enabled` 配置，支持中断恢复（Web 侧栏可 resume）

## 路由/节点表（LangGraph 节点，非 HTTP 路由）

| 节点角色 | 定义位置 | 职责 |
| ---- | ---- | ---- |
| Analysts（7） | agents/analysts/*.py | 各维度取数分析，产出分析段 |
| Bull/Bear Researcher | agents/researchers/*.py | 多空辩论 |
| Risk Debators（3） | agents/risk_mgmt/*.py | 激进/保守/中立风险辩论 |
| Research Manager | agents/managers/research_manager.py | 汇总研究，产 ResearchPlan |
| Trader | agents/trader/trader.py | 产 TraderProposal |
| Portfolio Manager | agents/managers/portfolio_manager.py | 产 PortfolioDecision（终裁） |

## 模块依赖关系

| 模块 | 依赖谁 | 被谁依赖 |
| ---- | ---- | ---- |
| graph/trading_graph | graph/setup, agents/*, llm_clients/factory, dataflows/interface | cli/main, web/runner |
| dataflows/interface | dataflows/a_stock, alpha_vantage*, y_finance | agents/utils/*_tools |
| dataflows/a_stock | dataflows/utils（safe_ticker_component） | interface, 各工具 |
| llm_clients/factory | *_client, model_catalog, validators | trading_graph, agents |
