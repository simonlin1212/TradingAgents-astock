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
