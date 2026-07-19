# 编码规范与约定

> 与 `.claude/rules/` 一致，此处补充代码库实证约定。

## 命名

| 对象 | 规则 | 示例 |
| ---- | ---- | ---- |
| 模块/文件 | snake_case.py | a_stock.py, default_config.py |
| 函数/变量 | snake_case | resolve_ticker, safe_ticker_component |
| 常量 | UPPER_SNAKE | EM_MIN_INTERVAL, VENDOR_METHODS |
| 模块私有 | 前缀 `_` | _em_get, _build_name_code_map |
| Agent 角色文件 | `{role}_analyst.py` / `{role}_researcher.py` | market_analyst.py, bull_researcher.py |

## 代码风格

- 缩进 4 空格，无 Tab；无 lint 配置，遵循 PEP 8
- Import 顺序：标准库 → 第三方 → 本项目（`tradingagents.*`），组间空行
- 每模块顶部 `logger = logging.getLogger(__name__)`，禁用 `print` 打日志
- 类型标注用 `typing`（含 `Annotated`）；公共数据函数标注返回类型
- 公共函数写 docstring，解释「为什么」与边界；非显然逻辑（安全/限流/兼容）必留注释

## 关键约定（本项目特有，违反会踩坑）

| 约定 | 说明 | 位置 |
| ---- | ---- | ---- |
| 东财端点走 `_em_get` | 禁止裸 requests.get 访问 eastmoney，防封 IP | a_stock.py |
| ticker 进路径先过 `safe_ticker_component` | 唯一路径安全边界，白名单校验 | dataflows/utils.py |
| 新数据源走 vendor 路由 | 遵循 interface.py 的 `VENDOR_METHODS` + `route_to_vendor` 模式 | dataflows/interface.py |
| 结构化输出用 schemas.py 的模型 | 不散落定义决策结构 | agents/schemas.py |
| 外部 HTTP 返回按不可信处理 | 校验字段、异常降级不崩溃 | 各 vendor |

## 配置

- 全局默认在 `tradingagents/default_config.py`；运行时 config 由前端合并覆盖
- 密钥/端点走环境变量或 `.env`（已 gitignore），`.env.example` 只放 key 名

## 工具/入口速查

| 用途 | 入口 |
| ---- | ---- |
| 建 LLM 客户端 | llm_clients/factory.py:create_llm_client |
| 取任意数据 | dataflows/interface.py:route_to_vendor |
| 解析中文股票名 | dataflows/a_stock.py:resolve_ticker |
| 跑一次完整分析 | graph/trading_graph.py:TradingAgentsGraph.propagate |
