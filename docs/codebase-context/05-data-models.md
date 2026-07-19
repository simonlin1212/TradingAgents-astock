# 数据模型与类型

> 结构化输出用 Pydantic（`agents/schemas.py`）。**定义新结构化输出前先查本表，已有的直接引用。**

## 枚举

| 名称 | 取值 | 定义位置 |
| ---- | ---- | ---- |
| PortfolioRating | 组合评级（str Enum） | agents/schemas.py:32 |
| TraderAction | 交易动作（buy/sell/hold 等，str Enum） | agents/schemas.py:42 |

## 结构化输出模型（Pydantic BaseModel）

| 名称 | 用途 | 产出角色 | 定义位置 |
| ---- | ---- | ---- | ---- |
| ResearchPlan | 研究计划/综合结论 | Research Manager | agents/schemas.py:61 |
| TraderProposal | 交易提案 | Trader | agents/schemas.py:109 |
| PortfolioDecision | 最终组合决策（终裁） | Portfolio Manager | agents/schemas.py:171 |

## Agent 状态

| 名称 | 说明 | 定义位置 |
| ---- | ---- | ---- |
| Agent state（TypedDict/dataclass） | LangGraph 在节点间传递的全局状态：各 Analyst 报告段、辩论历史、最终决策等 | agents/utils/agent_states.py |

## 结构化解析工具

| 名称 | 说明 | 定义位置 |
| ---- | ---- | ---- |
| structured 输出辅助 | 将 LLM 文本解析/校验为上述 schema | agents/utils/structured.py |
| rating | 评级归一化 | agents/utils/rating.py |

## LLM 模型目录

| 名称 | 说明 | 定义位置 |
| ---- | ---- | ---- |
| model_catalog | 各提供商可用模型清单与能力标注 | llm_clients/model_catalog.py |
| validators | 模型/参数校验 | llm_clients/validators.py |
