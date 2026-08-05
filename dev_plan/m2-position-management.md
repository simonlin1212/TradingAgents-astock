# M2 持仓管理（持仓感知 + 操作指导）

## 目标
对已持仓标的，根据**持仓情况（成本、数量、盈亏）+ 分析预测**，输出后续操作指导：持有 / 加仓 / 减仓 / 清仓，并给出**目标仓位与参考价位**（价位复用 M1 能力）。无持仓输入时行为与现状完全一致（向后兼容）。

## 功能设计

### 1. 输入：持仓数据（D2 待定，先做手动输入）
```json
// holdings.json 示例
[
  {"code": "600519", "name": "贵州茅台", "quantity": 100, "cost_price": 1450.0},
  {"code": "000001", "name": "平安银行", "quantity": 2000, "cost_price": 10.8}
]
```
- CLI：新增 Step（或 `--holdings holdings.json` 参数），交互式输入或文件导入
- Web：侧栏折叠表单（添加持仓行）
- config 新增键 `holdings: List[Dict]`（`tradingagents/default_config.py`）

### 2. State 扩展（`tradingagents/agents/utils/agent_states.py`）
- 新增字段 `holdings: List[Dict]`；`Propagator.create_initial_state` 注入（`tradingagents/graph/propagation.py`）
- 当前分析标的的持仓条目（匹配 code）注入相关 agent prompt：
  - **Portfolio Manager**：追加"当前持仓"上下文段落（成本/数量/盈亏/占总投资比例），并要求决策按持仓视角给出操作方向
  - **Research Manager / Trader**：轻量注入（仅提示存在持仓，避免 prompt 膨胀）

### 3. 输出：持仓操作建议
- `PortfolioDecision` 增加可选字段 `position_action`（Hold / Add / Reduce / Exit）+ `target_position_pct`（目标仓位 %）——**向后兼容**：无持仓时该字段为 None，渲染照旧
- 操作建议与 M1 `ExecutionAdvice` 联动：Add → 给出加仓价位区间与仓位（M1）；Reduce/Exit → 给出减仓/离场参考价
- 渲染：报告「持仓操作建议」章节 + Web 卡片

### 4. 交互流
```
用户输入持仓 → 选择标的（批量场景走 M4）→ 分析 → 报告含：
  ① 决策评级（现状）
  ② 持仓操作：持有/加仓/减仓/清仓 + 目标仓位 + 理由
  ③ 执行建议：参考价位区间（复用 M1）
```

## 实施步骤（小步）
1. config 加 `holdings` 键 + CLI `--holdings` / 交互 Step（Web 表单）
2. state 加 `holdings` 字段 + 初始注入
3. `schemas.py`：`PortfolioDecision` 加 `position_action` / `target_position_pct`（Optional，默认 None）
4. Portfolio Manager prompt 追加持仓上下文（含持仓盈亏计算示例）
5. 报告/Web 渲染持仓操作章节
6. 测试：`tests/test_holdings.py`（无持仓=现状；有持仓→position_action 非空；盈亏计算正确）

## 验收标准
- [ ] 传 `holdings.json` 后报告出现「持仓操作建议」（操作方向 + 目标仓位 + 理由）
- [ ] 不传持仓时输出与现状逐字节可比（或仅结构相同）
- [ ] 盈亏计算正确（cost vs 现价，正负）
- [ ] CLI 与 Web 双入口可用

## 风险与边界
- prompt 膨胀：持仓上下文只注入 PM 与轻量注入 RM/Trader，其他分析师不动
- 多持仓标的：单标的分析只关注当前 code 的持仓；多标的批量操作走 M4
- 免责声明：持仓建议为研究参考，非自动调仓指令

## 核心代码片段

### 1. config 键（`tradingagents/default_config.py`）
```python
DEFAULT_CONFIG = {
    ...,
    "holdings": [],   # list[dict]: {"code": "600519", "name": "贵州茅台",
                      #              "quantity": 100, "cost_price": 1450.0}
}
```

### 2. State 注入（`tradingagents/graph/propagation.py` 的 `create_initial_state`）
```python
def create_initial_state(company_name, trade_date, past_context=""):
    state = {...}  # 现有字段
    # 仅注入与当前标的匹配的持仓（避免 prompt 膨胀与串扰）
    holdings = get_config().get("holdings", [])
    state["holdings"] = [h for h in holdings if _match_code(h, company_name)]
    return state
```

### 3. Schema 扩展（`tradingagents/agents/schemas.py`，向后兼容）
```python
class PositionAction(str, Enum):
    HOLD = "hold"; ADD = "add"; REDUCE = "reduce"; EXIT = "exit"

class PortfolioDecision(BaseModel):
    rating: PortfolioRating
    executive_summary: str
    investment_thesis: str
    time_horizon: Optional[str] = None
    # 新增（可选字段，无持仓时为 None，渲染逻辑零改动）
    position_action: Optional[PositionAction] = None
    target_position_pct: Optional[float] = Field(default=None, ge=0, le=100)
```

### 4. PM prompt 注入持仓上下文（`tradingagents/agents/managers/portfolio_manager.py`）
```python
def _holdings_block(holdings: list[dict], current_price: float) -> str:
    if not holdings:
        return ""
    h = holdings[0]
    pnl = (current_price - h["cost_price"]) / h["cost_price"] * 100
    return (
        "\n**Current Position (research reference):**\n"
        f"- Cost {h['cost_price']}, Qty {h['quantity']}, "
        f"current PnL {pnl:+.1f}%\n"
        "- Output position_action as hold/add/reduce/exit with target_position_pct."
    )
# 追加到 PM system prompt 末尾；无持仓时返回 ""，行为与现状一致
```

## 测试方法与步骤

### 测试文件与策略
| 文件 | 类型 | mock 策略 |
|------|------|-----------|
| `tests/test_holdings.py` | unit | 纯逻辑：持仓匹配、盈亏计算、prompt block 渲染 |
| `tests/test_holdings_graph.py` | unit/smoke | mock LLM 结构化输出：有/无持仓两组固定 `PortfolioDecision`，验证渲染差异 |

### 关键用例
1. **向后兼容**：无持仓 → `position_action is None`，`render_pm_decision` 输出与现状逐字节一致（关键回归用例）
2. 持仓匹配：输入 code `600519` 匹配 `600519.SH` / 中文名；不匹配当前标的不注入
3. 盈亏计算：cost 1450 / 现价 1500 → `+3.4%`；现价 < cost → 负值
4. `_holdings_block`：空持仓 → `""`；有持仓 → 含 Cost/Qty/PnL 行
5. 渲染：`position_action=add` + `target_position_pct=15` → 报告「持仓操作建议」出现
6. CLI `--holdings` 解析：合法 JSON、缺失字段报错提示

### 运行与验收步骤
```bash
python -m pytest tests/test_holdings.py tests/test_holdings_graph.py -v
python -m pytest tests/ -v -m "not integration"          # 全量回归（重点看渲染用例）
# 手动冒烟：CLI 传 --holdings holdings.json 分析持仓标的，报告出现持仓操作章节；
# 不传时报告与 v0.4.0 输出一致
```

## 手动测试场景（实际使用）

> 前置条件：`.env` 配置好 LLM provider；准备示例持仓文件（见下）。

### 场景 A：盈利持仓「持有/减仓建议」
**目的**：验证盈利持仓（现价 > 成本）给出合理操作方向。
1. 构造 `holdings_gain.json`：
```json
[{"code": "600519", "name": "贵州茅台", "quantity": 100, "cost_price": 1400.0}]
```
2. 运行：`tradingagents --holdings holdings_gain.json`（或交互 Step 输入持仓）→ 分析 600519
3. 查看报告「持仓操作建议」章节
**预期**：显示持仓上下文（Cost 1400 / 当前盈亏 +X%）；`position_action` 为 hold/add（盈利且基本面好时）并给 `target_position_pct`；理由与评级自洽。

### 场景 B：亏损持仓「止损/减仓建议」
**目的**：验证亏损持仓输出与盈利场景有区分度。
1. 构造 `holdings_loss.json`：同上但 `cost_price: 1700.0`（现价之下为亏损）
2. 同场景 A 分析
**预期**：显示盈亏为负（`-X.X%`）；操作方向偏向 reduce/exit（或 hold 但提示风险），`target_position_pct` 低于或等于现状；与场景 A 输出存在可辨识差异。

### 场景 C：无持仓「向后兼容回归」
**目的**：确认没破坏现有功能。
1. 不传任何持仓参数，用同一标的、同一日期跑一次分析
2. 对比报告（可先存档一份 v0.4.0 输出作基线）
**预期**：无「持仓操作建议」章节（或该字段不渲染）；其余内容与基线一致；`position_action` 未出现在决策中。

### 场景 D：Web 端持仓输入
1. `streamlit run web/app.py` → 侧栏「持仓」折叠区添加一行（代码 + 数量 + 成本价）→ 分析该标的
**预期**：报告出现持仓上下文与操作建议；不填持仓时页面无此区块。
