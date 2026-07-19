# TradingAgents-astock — 代码库参考文档索引

- 最后更新: 2026-07-19 00:49 UTC
- 扫描类型: full
- 项目根: /Users/zero/MyCode/TradingAgents-astock
- 业务地图: 已全量生成 2026-07-19（源码 80 个 .py 文件，>30 触发首扫）

## 文档导航

| 文档 | 内容 | 什么时候看 |
| ---- | ---- | ---- |
| 01-overview | 项目概述与技术栈 | 初次接触项目 |
| 02-directory | 目录结构 | 找文件放哪/在哪 |
| 03-architecture | 架构与模块关系 | 新代码归属、理解 Agent 编排与数据路由 |
| 04-api-routes | 数据源接口 / vendor 路由汇总 | 加数据接口前查重 |
| 05-data-models | Pydantic schema 与状态类型 | 定义结构化输出前查重 |
| 06-core-modules | Agent 角色 / 图节点 / LLM 客户端 | 加 Agent 或工具前查复用 |
| 07-business-logic | 端到端分析线路与关键规则 | 改分析流程前看线路 |
| 08-conventions | 编码规范与约定 | 动手写代码前 |
| 09-changelog | 文档变更记录 | 追溯文档演进 |

## 快速定位

| 我想找… | 去 |
| ---- | ---- |
| 某个数据怎么取（K线/财务/新闻/资金流） | 04-api-routes |
| 结构化输出/决策的字段定义 | 05-data-models |
| 有没有现成 Agent / 工具 / LLM 客户端 | 06-core-modules |
| 一次分析从输入到报告的完整线路 | 07-business-logic |
| 命名/风格/安全边界规矩 | 08-conventions |
| A 股数据 vendor 全貌 | 04-api-routes + 03-architecture |
