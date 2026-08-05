# M4 批量分析（标的池 → 批量决策汇总）

## 目标
消费 M3 的标的池（或用户手输标的列表），逐个跑完整分析图，输出**汇总决策报告**：每个标的的评级、方向、执行建议、一页理由，附完整报告链接。单个标的失败不中断整批（独立失败隔离）。

## 现状依据
- 单标的入口：`TradingAgentsGraph.propagate(ticker, trade_date)`（`tradingagents/graph/trading_graph.py:446-453`）；CLI 用 `graph.graph.stream` + `finalize_graph_run`（`cli/main.py:1105, 514-534`）
- **无任何批量循环**（CLI 8 步交互单标的；Web 单线程单标的）
- 每次分析 30-50 次 LLM 调用；东财限流 `_em_get` 模块级串行
- checkpoint 能力已有：`checkpoint_enabled`（`tradingagents/default_config.py:49`）→ 断点续跑可复用

## 功能设计

### 1. CLI 子命令：`tradingagents scan --run`（或独立 `tradingagents batch`）
```
tradingagents batch --pool pool.csv --limit 5 --trade-date 2026-08-06 \
                    --quick --provider minimax
```
- `--pool`：M3 的 CSV 或用户手写标的列表（过 `safe_ticker_component` 校验）
- `--limit`：每批上限（默认 5，D3）
- `--quick`：**快速模式**（D3）——只跑核心 4 分析师（market/social/fundamentals/news）+ 1 轮辩论 + 1 轮风险辩论，砍掉政策/游资/解禁，省 ~30% 调用
- 复用现有 config 覆盖逻辑（`cli/main.py:982-995` 模式）

### 2. 批量编排（新增 `tradingagents/batch/` 或 `cli/batch_runner.py`）
```
for ticker in pool:            # v1 串行；后续可受限并发
    try:
        state, signal = graph.propagate(ticker, trade_date)   # 单标的完整图
    except Exception as e:
        results.append({ticker, status="failed", error=str(e)})  # 隔离失败
        continue
    results.append({ticker, signal, execution_advice, one-line thesis})
```
- 每个标的独立 `TradingAgentsGraph` 实例（避免 state 串扰），config 共享
- 检查点：开启 `checkpoint_enabled` 时逐标的续跑
- 东财限流：批量前设 `EM_MIN_INTERVAL=1.5~2`（CLAUDE.md 规范）

### 3. 汇总报告 `reports/batch_{ts}/summary.md`
| 排序 | 标的 | 评级 | 方向 | 建议仓位 | 参考价位区间 | 一页理由 | 完整报告 |
|------|------|------|------|----------|--------------|----------|----------|
- 按评级排序（Buy 优先）；失败标的单列「失败清单」+ 原因
- 每行链接到 `reports/{ticker}_{ts}/complete_report.md`（M1 的 VI 章节含执行建议）
- 批量结束打印 token/费用估算（基于调用次数统计，M3 的 D3）

### 4. 成本控制（D3 核心）
- 分析前打印预估：`调用数 ≈ (7 或 4 分析师 + 辩论×轮 + 风险×轮 + PM + 执行建议) × 标的数`，确认后执行
- `--limit` 硬上限（如 10，防误触）
- `--quick` 快速模式选项

### 5. Web（可选，后续）
- 侧栏「批量筛选」区：M3 条件 → 标的池 → 批量启动 → 进度条（每标的完成标记）+ 汇总表

## 实施步骤（小步）
1. 抽取批量编排核心（输入池 → 逐标的 propagate → 结果收集），CLI 子命令骨架
2. 失败隔离 + 检查点续跑
3. 汇总报告渲染（markdown 表）
4. `--quick` 快速模式（分析师子集，复用 `selected_analysts` 参数——`TradingAgentsGraph.__init__` 已支持，见 `trading_graph.py:133-139`）
5. 成本预估打印
6. 测试 `tests/test_batch.py`（mock LLM/数据层，2-3 标的）

## 验收标准
- [ ] `tradingagents batch --pool x.csv --limit 5` 跑通，汇总表评级排序正确
- [ ] 单标的抛错不中断整批，失败清单含原因
- [ ] `--quick` 与全量模式输出结构一致（缺的只是分析师章节）
- [ ] 断点续跑：中断后重跑跳过已完成标的
- [ ] 全部标的输入过 `safe_ticker_component` 校验

## 风险与边界
- **成本**：5 标的全量 ≈ 150-250 次 LLM 调用，务必先打印预估再执行
- 东财限流是模块级串行——并发跑多标的会排长队，v1 串行足够；后续并发需注意 `_em_get` 全局锁
- 长耗时：5 标的全量可能 10-30 分钟，CLI 需有逐标的进度输出；Web 用已有 `ProgressTracker` 模式
