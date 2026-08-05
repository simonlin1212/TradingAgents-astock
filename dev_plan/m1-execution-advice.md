# M1 执行建议（价位 + 仓位）

## 目标
当前决策只给 5 档 Rating（Buy/Overweight/Hold/Underweight/Sell），**刻意不含任何可执行价位与仓位**。本里程碑为单标的分析增加"执行建议"：推荐买入时给出**买入区间、止损位、目标位、建议仓位比例**。

## 现状依据（调查结论，file:line）
- 最终决策 = `PortfolioDecision`（`tradingagents/agents/schemas.py:156-191`）：仅 `rating` + `executive_summary` + `investment_thesis` + `time_horizon`
- 刻意禁止：`TraderProposal`/`PortfolioDecision` docstring（`schemas.py:115-121, 164-165`）+ `_NO_LEVELS_RULE`（`tradingagents/agents/managers/portfolio_manager.py:26-29`）
- 决策链：7 分析师 → Quality Gate → Bull/Bear → Research Manager → Trader → 三方风险辩论 → **Portfolio Manager → END**（`tradingagents/graph/setup.py:138-210`）
- 报告章节「V. Portfolio Manager Decision」（`cli/main.py:762-767`）；Web 导出（`web/pdf_export.py:616-621`）
- 技术指标工具已有：`get_indicators`（stockstats），可拿 ATR/均线/支撑阻力

## 功能设计

### 原则
**不动现有决策链**（守住"评级+论证"的合规护栏），在其后新增独立节点，输出结构化执行建议。价位由**指标推导 + LLM 综合**生成，数值做确定性校验，绝不自由发挥。

### 1. Schema（`tradingagents/agents/schemas.py` 新增）
```python
class ExecutionAdvice(BaseModel):
    entry_zone: str            # 建议买入区间，如 "12.5 - 13.2"
    stop_loss: float           # 止损位（必须 < 现价）
    target_price: float        # 目标位（必须 > 现价）
    position_size_pct: float   # 建议仓位 %（0-100，含 0 = 不建议入场）
    rationale: str             # 一句理由
```

### 2. 仓位模型（确定性规则，v1 从简）
```
止损距离% = (现价 - stop_loss) / 现价
建议仓位% = min(单票风险预算% / 止损距离%, 单票仓位上限%)
默认：单票风险预算 = 1.5%（D4 可调），单票上限 = 20%（D4 可调）
```
LLM 只负责给出合理止损位（基于 ATR/支撑位），仓位由公式算出，杜绝幻觉仓位。

### 3. 新节点 `Execution Advisor`（`tradingagents/graph/setup.py`）
- 位置：`Portfolio Manager → Execution Advisor → END`
- 输入：`final_trade_decision` + `trader_investment_plan` + 关键行情/指标快照（现价、ATR、近期高低点，来自已有 `get_stock_data`/`get_indicators` 数据）
- 输出：`with_structured_output(ExecutionAdvice)` → 渲染 markdown 存新 state 字段 `execution_advice`（`agent_states.py` 增加）
- Rating = Buy/Overweight 才给完整建议；Hold 给"观望"占位；Sell 给"不参与/离场"占位
- 确定性校验（独立函数）：stop_loss < 现价 < target_price；position_size_pct ∈ [0,100]；非法则 clamp 或回退为 None

### 4. 报告与 UI
- CLI 报告新增「VI. Execution Advice」章节（`cli/main.py` save_report_to_disk）
- Web 报告卡片显示执行建议（`web/components/`）
- 免责声明文案更新：执行建议为**研究参考区间，非自动下单指令**（D1）

### 5. 测试（`tests/test_execution_advice.py`）
- 仓位公式单元测试（不同止损距离 → 正确仓位、封顶生效）
- 确定性校验：非法数值被 clamp/拒绝
- schema 渲染成 markdown 的格式测试

## 实施步骤（小步）
1. `schemas.py` 加 `ExecutionAdvice` + 渲染函数
2. `agent_states.py` 加 `execution_advice` 字段
3. `setup.py` 注册 `Execution Advisor` 节点（PM → 新节点 → END）
4. 仓位公式 + 校验函数（纯函数，先写测试）
5. CLI/Web 报告渲染
6. 免责声明更新

## 验收标准
- [ ] 单标的分析输出含 4 个字段，数值满足 stop_loss < 现价 < target_price
- [ ] Buy/Overweight 才有完整建议；Hold/Sell 为占位
- [ ] CLI 报告与 Web 均显示新章节
- [ ] 新增测试全绿，既有测试不破坏

## 风险与边界
- LLM 幻觉价位 → 用指标推导 + 确定性校验兜底；不合理数值宁可置空不硬填
- 仓位模型是简化版（不考虑组合相关性、波动率锥），报告注明局限
- 不改变 `final_trade_decision` 语义，`process_signal`/记忆标签不受影响

## 核心代码片段

### 1. Schema（`tradingagents/agents/schemas.py` 追加，仿照现有 `PortfolioDecision` 风格）
```python
class ExecutionAdvice(BaseModel):
    """执行建议：价位 + 仓位。数值必须满足确定性校验（见下）。"""
    entry_zone: str = Field(description="建议买入区间，如 '12.5 - 13.2'")
    stop_loss: float = Field(description="止损位，必须低于现价")
    target_price: float = Field(description="目标位，必须高于现价")
    position_size_pct: float = Field(ge=0, le=100, description="建议仓位 %，0 = 不建议入场")
    rationale: str = Field(description="一句理由，<=50 字")

def render_execution_advice(advice: ExecutionAdvice) -> str:
    # 仿照 render_pm_decision（schemas.py:194-211）的 markdown 渲染
    return (
        f"**Entry Zone**: {advice.entry_zone}\n"
        f"**Stop Loss**: {advice.stop_loss}\n"
        f"**Target Price**: {advice.target_price}\n"
        f"**Position Size**: {advice.position_size_pct}%\n"
        f"**Rationale**: {advice.rationale}"
    )
```

### 2. 仓位公式（新文件 `tradingagents/agents/utils/position_sizing.py`，纯函数）
```python
def position_size_pct(price: float, stop_loss: float,
                      risk_budget_pct: float = 1.5, cap_pct: float = 20.0) -> float:
    """仓位% = min(风险预算% / 止损距离%, 单票上限%)。非法输入返回 0。"""
    if price <= 0 or stop_loss <= 0 or stop_loss >= price:
        return 0.0
    risk_dist = (price - stop_loss) / price          # 止损距离（相对现价）
    return round(min(risk_budget_pct / risk_dist, cap_pct), 1)

def validate_advice(advice: ExecutionAdvice, price: float) -> ExecutionAdvice:
    """确定性校验：止损<现价<目标；非法字段 clamp 或置 None 不硬填。"""
    if not (advice.stop_loss < price < advice.target_price):
        return ExecutionAdvice(entry_zone="N/A", stop_loss=0, target_price=0,
                               position_size_pct=0.0, rationale="价位无效，不提供执行建议")
    advice.position_size_pct = position_size_pct(price, advice.stop_loss)
    return advice
```

### 3. 节点注册（`tradingagents/graph/setup.py` 追加，仿照现有节点）
```python
graph.add_node("Execution Advisor", execution_advisor_node)
graph.add_edge("Portfolio Manager", "Execution Advisor")   # 现 setup.py:210 是 PM -> END
graph.add_edge("Execution Advisor", END)
```
节点实现（`tradingagents/agents/managers/execution_advisor.py`，仿照 `portfolio_manager.py`）：
```python
def execution_advisor_node(state: AgentState) -> dict:
    advice = advisor_llm.with_structured_output(ExecutionAdvice).invoke(
        _build_advice_prompt(state)          # PM 决策 + trader 提案 + 现价/ATR/高低点快照
    )
    advice = validate_advice(advice, current_price(state))
    return {"execution_advice": render_execution_advice(advice)}
```

## 测试方法与步骤

### 测试文件与策略
| 文件 | 类型 | mock 策略 |
|------|------|-----------|
| `tests/test_position_sizing.py` | unit | 无（纯函数） |
| `tests/test_execution_advice.py` | unit | mock LLM 的 `with_structured_output` 返回固定 `ExecutionAdvice`，验证校验/渲染 |
| `tests/test_graph_execution_node.py` | unit/smoke | 参照现有 `tests/conftest.py` 的 mock LLM 模式跑 mini graph（跳过 7 分析师，直接喂假 state） |

### 关键用例
1. `position_size_pct`：正常（价 10/止损 9.5 → 3.0%）、止损≥现价 → 0、封顶（止损 9.9 → 20%）、风险预算 0 → 0
2. `validate_advice`：非法价位 → 占位 Advice（全 0/ N/A）；合法价位 → 仓位被公式覆盖而非 LLM 直出
3. 渲染：`render_execution_advice` 输出 5 个 `**X**` 头
4. 集成：PM 决策为 Buy 时有完整建议；Hold/Sell 时占位
5. 回归：`final_trade_decision` 与 `process_signal` 输出不变（新节点不触碰旧字段）

### 运行与验收步骤
```bash
python -m pytest tests/test_position_sizing.py tests/test_execution_advice.py -v   # 单元
python -m pytest tests/ -v -m "not integration"                                    # 全量回归
# 手动冒烟：CLI 单标的分析，确认报告出现「VI. Execution Advice」章节且数值自洽
```

## 手动测试场景（实际使用）

> 前置条件：`pip install -e .`；`.env` 配置好 LLM provider（DeepSeek/MiniMax 任选）；网络可用。

### 场景 A：强势股「完整执行建议」（核心场景）
**目的**：验证 Buy/Overweight 评级下给出完整价位 + 仓位。
1. 选一只当日强势标的（可从 `get_hot_stocks` 或涨幅榜挑，如近期涨停股，代码记作 `XXXXXX`）
2. 运行：`tradingagents` → Step 1 输入代码 → 其余步骤选默认（研究深度选「深入」）→ 等待完成
3. 打开 `reports/XXXXXX_{ts}/complete_report.md`，定位「VI. Execution Advice」
**预期**：4 个字段齐全且自洽：`stop_loss < 当前价 < target_price`；`position_size_pct` ∈ (0, 20]；`entry_zone` 覆盖现价附近；`rationale` ≤ 50 字。Rating 为 Buy/Overweight。

### 场景 B：弱势股「占位建议」
**目的**：验证 Sell/Underweight 不硬填价位。
1. 选一只明显弱势标的（如连续下跌、破位股）
2. 同场景 A 跑分析，查看 VI 章节
**预期**：Rating 为 Sell/Underweight/Hold 时，执行建议为"观望/不参与"占位（仓位 0%），不出现伪造的买入区间。

### 场景 C：边界标的「校验兜底」
**目的**：验证 LLM 输出非法数值时被校验拦截。
1. 选一只波动极大或 ST 类标的（注意 `safe_ticker_component` 对中文/代码均可用）
2. 跑分析后人工检查 VI 章节数值
**预期**：若出现 `stop_loss >= 现价` 或 `target <= 现价` 等非法值，报告显示占位（`N/A` / 0%）而非非法数值；不抛异常。

### 场景 D：Web 端展示
1. `streamlit run web/app.py` → 侧栏输入标的 → 分析完成
2. 查看报告页
**预期**：执行建议以卡片/段落展示在最终决策之后；数值与 CLI 报告一致。
