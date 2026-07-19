# 数据源接口 / vendor 路由汇总

> 本项目无 HTTP 服务端路由；此处汇总**数据获取方法**及其 vendor 实现。
> 调用统一经 `dataflows/interface.py:route_to_vendor(method, ...)`（`interface.py:202`），按 `config["data_vendors"]` 选 vendor 并自动 fallback。
> **加数据方法前先查本表，已有的直接复用 method 名，不重复造。**

## vendor 方法映射（`VENDOR_METHODS`，interface.py:103）

| method | A 股实现（a_stock.py） | 备选 vendor | 类别 |
| ---- | ---- | ---- | ---- |
| `get_stock_data` | get_stock_data (`a_stock.py:548`) | alpha_vantage, yfinance | core_stock_apis |
| `get_indicators` | get_indicators (`a_stock.py:648`) | alpha_vantage, yfinance | technical_indicators |
| `get_fundamentals` | get_fundamentals (`a_stock.py:710`) | alpha_vantage | fundamental_data |
| `get_balance_sheet` | get_balance_sheet (`a_stock.py:939`) | alpha_vantage | fundamental_data |
| `get_cashflow` | get_cashflow (`a_stock.py:970`) | alpha_vantage | fundamental_data |
| `get_income_statement` | get_income_statement (`a_stock.py:1001`) | alpha_vantage | fundamental_data |
| `get_news` | get_news (`a_stock.py:1121`) | alpha_vantage | news_data |
| `get_global_news` | get_global_news (`a_stock.py:1191`) | — | news_data |
| `get_insider_transactions` | get_insider_transactions (`a_stock.py:1290`) | — | news_data |
| `get_profit_forecast` | get_profit_forecast (`a_stock.py:1339`) | — | signal_data（A 股专有） |
| `get_hot_stocks` | get_hot_stocks (`a_stock.py:1432`) | — | signal_data |
| `get_northbound_flow` | get_northbound_flow (`a_stock.py:1568`) | — | signal_data |
| `get_concept_blocks` | get_concept_blocks (`a_stock.py:1689`) | — | signal_data |
| `get_fund_flow` | get_fund_flow (`a_stock.py:1757`) | — | signal_data |
| `get_dragon_tiger_board` | get_dragon_tiger_board (`a_stock.py:1873`) | — | signal_data（龙虎榜） |
| `get_lockup_expiry` | get_lockup_expiry (`a_stock.py:2001`) | — | signal_data（限售解禁） |
| `get_industry_comparison` | get_industry_comparison (`a_stock.py:2082`) | — | signal_data |

## Agent 侧工具封装（LangChain tool，供 Agent 调用）

| 工具文件 | 暴露方法 |
| ---- | ---- |
| agents/utils/core_stock_tools.py | get_stock_data |
| agents/utils/technical_indicators_tools.py | get_indicators |
| agents/utils/fundamental_data_tools.py | get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement |
| agents/utils/news_data_tools.py | get_news, get_global_news, get_insider_transactions |
| agents/utils/signal_data_tools.py | get_profit_forecast, get_hot_stocks, get_northbound_flow, get_concept_blocks, get_fund_flow, get_dragon_tiger_board, get_lockup_expiry, get_industry_comparison |

## 外部数据源（直连，无 SDK/数据库）

| 源 | 协议 | 提供数据 |
| ---- | ---- | ---- |
| mootdx | TCP 7709 | OHLCV K线、财务快照、F10 |
| 东方财富（push2/datacenter/np-weblist） | HTTP（走 `_em_get` 节流） | 实时行情、龙虎榜、解禁、资金流、滚动新闻 |
| 腾讯财经 | HTTP | PE/PB/市值/换手率 |
| 新浪财经 | HTTP | K线历史、财报三表 |
| 同花顺 10jqka | HTTP | EPS 一致预期、热股题材 |
| 财联社 cls.cn | HTTP | 全球财经快讯 |
| 百度股市通 | HTTP | 概念板块归属 |

> ⚠ 关键约束：新增东财端点必须走 `a_stock.py:_em_get`，禁止裸 `requests.get`（防封 IP）。
