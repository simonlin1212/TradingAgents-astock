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
