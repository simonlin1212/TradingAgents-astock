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

## 核心代码片段

### 1. clist 泛化（新文件 `tradingagents/scanner/clist.py`，**东财调用必须走 `_em_get`**）
```python
from tradingagents.dataflows.a_stock import _em_get   # 统一限流入口（a_stock.py:288-303）

# 东财 clist 字段：f12=code f14=name f2=现价 f3=涨跌幅 f20=总市值 f9=PE
def get_market_snapshot(fs: str = "m:0+t:6,m:0+t:80,m:1+t:2",   # 全 A（沪深主板+创业+科创）
                        sort: str = "3:desc",                    # 3=涨跌幅, 20=总市值
                        fields: str = "f12,f14,f2,f3,f20,f9",
                        pz: int = 100) -> list[dict]:
    return _em_get("https://push2.eastmoney.com/api/qt/clist/get", params={
        "pn": 1, "pz": pz, "po": 1, "np": 1, "fltt": 2, "invt": 2,
        "fid": sort.split(":")[0], "fs": fs, "fields": fields,
    })

def top_gainers(limit=100) -> list[dict]: return get_market_snapshot(sort="3:desc", pz=limit)
def top_mktcap(limit=100)   -> list[dict]: return get_market_snapshot(sort="20:desc", pz=limit)
```
> ⚠️ 开工时先打印原始 JSON 核对字段名（f9 PE 在亏损股可能为 `-`），再写解析。

### 2. 筛选器（新文件 `tradingagents/scanner/scanner.py`）
```python
from pydantic import BaseModel

class ScreenCriteria(BaseModel):
    industries: list[str] = []          # 来自 get_industry_comparison 的板块名
    pe_min: float | None = None;  pe_max: float | None = None
    mktcap_min: float | None = None     # 亿元
    chg_min: float | None = None        # 涨跌幅下限 %
    exclude_st: bool = True
    limit: int = 20

def run_screen(c: ScreenCriteria) -> list[dict]:
    rows = top_gainers(limit=500)                     # 候选池（可换 fs 限定行业）
    rows = [r for r in rows if _is_st(r) is not c.exclude_st]
    if c.pe_min is not None:  rows = [r for r in rows if _pe(r) >= c.pe_min]
    if c.pe_max is not None:  rows = [r for r in rows if _pe(r) <= c.pe_max]
    if c.mktcap_min: rows = [r for r in rows if _mktcap(r) >= c.mktcap_min]
    if c.chg_min:    rows = [r for r in rows if _chg(r) >= c.chg_min]
    return rows[:c.limit]                              # 每条含触发条件标注

def _is_st(name: str) -> bool:
    return "ST" in name.upper() or "退" in name
```

### 3. CLI 子命令（`cli/main.py` 或新 `cli/scan.py`，仿照现有 `@app.command()`）
```python
@app.command()
def scan(industry: list[str] = typer.Option([]), pe_min: float = typer.Option(None),
         mktcap_min: float = typer.Option(None), chg_min: float = typer.Option(None),
         exclude_st: bool = typer.Option(True), limit: int = typer.Option(20),
         output: Path = typer.Option(Path("pool.csv"))):
    pool = run_screen(ScreenCriteria(industries=industry, pe_min=pe_min,
                                     mktcap_min=mktcap_min, chg_min=chg_min,
                                     exclude_st=exclude_st, limit=limit))
    pd.DataFrame(pool).to_csv(output, index=False)     # 供 M4 消费
```

## 测试方法与步骤

### 测试文件与策略
| 文件 | 类型 | mock 策略 |
|------|------|-----------|
| `tests/test_scanner.py` | unit | `monkeypatch` 掉 `_em_get` 返回 fixture JSON（固定 3-5 行 clist 样本），零网络 |
| `tests/test_scanner_cli.py` | unit | mock `run_screen`，验证 CLI 参数 → 条件对象 → CSV 输出 |

### 关键用例
1. 排行解析：fixture JSON → `top_gainers` 返回结构正确的 list[dict]（字段映射、`-` 值 → None）
2. 条件 AND：pe 区间 + chg 下限同时生效；单个条件不满足即过滤
3. ST 过滤：`*ST*` / `退*` 名称被排除，`exclude_st=False` 时保留
4. limit 截断：候选 500 → 输出 ≤ limit
5. **限流合规**：断言扫描全程 `_em_get` 被调用（且未绕过直接 `requests.get`）
6. CLI：`--pe-min 10 --limit 5` 生成 CSV，表头与 M4 期望一致

### 运行与验收步骤
```bash
python -m pytest tests/test_scanner.py tests/test_scanner_cli.py -v   # 全 mock，离线可跑
python -m pytest tests/ -v -m "not integration"
# 手动冒烟（真数据，慢）：EM_MIN_INTERVAL=1.5 tradingagents scan --limit 10 --exclude-st
# 检查：输出 pool.csv；东财未被封（HTTP 200，无 449/重试）
```

## 手动测试场景（实际使用）

> 前置条件：网络可用；建议先跑单元测试确认解析逻辑（mock 已覆盖），再上真数据。

### 场景 A：首次真数据「字段核对」（必做一次）
**目的**：验证东财 clist 返回字段与计划中假设一致（f12/f14/f2/f3/f20/f9）。
1. 临时跑一次最小查询并打印原始响应：
```python
python - <<'EOF'
from tradingagents.scanner.clist import get_market_snapshot
import json
print(json.dumps(get_market_snapshot(pz=3), ensure_ascii=False, indent=1))
EOF
```
2. 人工核对：code/name/现价/涨跌幅/总市值/PE 各字段名与类型；亏损股 PE 是否为 `-`
**预期**：字段映射正确；若不符，更新 `clist.py` 解析并回改测试 fixture。

### 场景 B：条件筛选「真实筛选」
**目的**：验证组合条件从真市场筛出标的池。
1. 运行：`EM_MIN_INTERVAL=1.5 tradingagents scan --industry 半导体 --pe-max 50 --mktcap-min 100 --limit 20 -o pool.csv`
2. 检查 `pool.csv`
**预期**：≤20 行；每行含 code/name/现价/涨跌幅/市值/PE；无 ST/退市；可抽查 2-3 只股票行情与条件吻合；耗时合理（限流生效）。

### 场景 C：限流与稳定性
**目的**：验证批量请求不触发东财封 IP。
1. 连跑 3 次场景 B（每次间隔 ~1s 后）
2. 观察日志/响应
**预期**：无 HTTP 449/封禁重试/空响应；设 `EM_MIN_INTERVAL=2` 更稳；连续跑不报 `Too Many Requests`。

### 场景 D：CSV 可直接被 M4 消费
**目的**：验证与批量分析的接口衔接。
1. 场景 B 产出 `pool.csv`，用 `tradingagents batch --pool pool.csv --limit 2`（M4 实现后）试跑
**预期**：M4 能正确读取并逐个分析（批量跑通 = M3 与 M4 衔接闭环）。
