# M3 筛选器（Scanner，纯数据层）

## 目标
按筛选条件从全 A 股筛出候选标的池，作为 M4 批量分析的输入。**零 LLM 调用**，纯数据层，最快见效。

## 现状依据（可复用的现成件）
- `get_hot_stocks()`（`tradingagents/dataflows/a_stock.py:1441-1517`）— 当日涨停/热门股 + 题材聚合（同花顺，非东财）
- `get_industry_comparison()`（`a_stock.py:2091-2155`）— 全行业排行榜，走东财 push2 **clist 通用列表接口**（`_em_get`）
- `_build_name_code_map()`（`a_stock.py:88-121`）— 全 A 股 code↔name 池（mootdx）
- `_eastmoney_datacenter()`（`a_stock.py:306-330`）— 数据中心无过滤查询（全市场龙虎榜/解禁）
- **缺失**：无涨幅榜/市值/PE/资金流排行的现成函数（clist 换 `fs`/`sortColumns` 即可扩展）

## 功能设计

### 1. 新增 `tradingagents/scanner/` 模块
```
tradingagents/scanner/
├── __init__.py
├── clist.py     # clist 通用列表封装（数据获取）
└── scanner.py   # 筛选条件 → 标的池（聚合+过滤）
```
遵循 `interface.py` vendor 路由模式；东财调用一律 `_em_get`。

### 2. clist 泛化（`clist.py`）
把 `get_industry_comparison` 里的 clist 调用（`a_stock.py:2112-2123`）抽成通用函数：
```python
get_market_snapshot(fs: str, sort: str, fields: list, pz: int = 100) -> list[dict]
```
- `fs="m:0+t:6,m:0+t:80,m:1+t:2"`（全 A）→ **涨幅榜**（sort by 涨跌幅 desc）
- 换 fields 取 市值/PE/PB → **市值榜 / PE 排行**
- 资金流排行：走已有 `get_fund_flow`（东财 push2）逐票取，或 clist 的资金流字段（需验证 clist 是否直接带主力净流入，不带则循环 `get_fund_flow` 限流执行）

### 3. 筛选条件（`scanner.py`，v1）
| 条件 | 来源 | 类型 |
|------|------|------|
| 行业/板块 | `get_industry_comparison` / clist fs=m:90+t:2 | 枚举多选 |
| 热门/涨停 | `get_hot_stocks` | 布尔 |
| 涨跌幅区间 | clist 涨幅榜 | 数值区间 |
| 市值区间 | clist 市值字段 | 数值区间 |
| PE/PB 区间 | clist PE/PB 字段 | 数值区间 |
| 资金流方向 | `get_fund_flow`（或 clist 字段） | 枚举 |
| 排除 ST/退市 | 名称/代码规则 | 默认开启 |

条件 AND 组合；支持 `--limit N`（默认 20）截断候选池。

### 4. CLI：`tradingagents scan`
```
tradingagents scan --industry 半导体,军工 --pe-min 10 --pe-max 40 \
                   --mktcap-min 100 --chg-min 0 --exclude-st --limit 20 \
                   -o pool.csv
```
输出 `pool.csv`（code/name/现价/涨跌幅/市值/PE/触发条件），可被 M4 直接消费。
Web：侧栏「批量筛选」折叠区（M4 时一并做）。

## 实施步骤（小步）
1. `clist.py`：泛化 `get_market_snapshot`（先复刻现有行业排行行为，验证不回归）
2. 扩展出涨幅榜 / 市值 / PE 排行（各一个函数 + 单测，mock 掉 `_em_get` 网络）
3. `scanner.py`：条件解析 + AND 聚合 + ST 过滤 + limit
4. CLI `scan` 子命令 + CSV 导出
5. 测试 `tests/test_scanner.py`

## 验收标准
- [ ] 每种排行函数返回结构正确的列表（mock 验证）
- [ ] 组合条件能筛出标的池，条件 AND 生效
- [ ] 东财调用全部经 `_em_get`（新增端点审查）
- [ ] `tradingagents scan` 输出 CSV 可直接用于 M4
- [ ] 既有测试不破坏

## 风险与边界
- clist 字段可用性依赖东财接口返回（需实测 fields 名，`f12`=code `f14`=name `f2`=现价 `f3`=涨跌幅 `f20`=总市值 `f9`=PE，开工时先打印原始 JSON 核对）
- 资金流若需逐票取，单次扫描可能几十次东财请求 → 走 `_em_get` 且建议放 `EM_MIN_INTERVAL=1.5~2`
- scanner 是"粗筛"：只有行情/基本面阈值，不含分析师判断——精筛交给 M4
