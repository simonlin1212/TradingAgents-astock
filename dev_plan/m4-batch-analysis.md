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

## 核心代码片段

### 1. 批量编排（新文件 `tradingagents/batch/runner.py`）
```python
from tradingagents.dataflows.utils import safe_ticker_component   # 安全边界，逐个过校验
from tradingagents.graph.trading_graph import TradingAgentsGraph
from dataclasses import dataclass, field

ALL_ANALYSTS = ["market", "social", "news", "fundamentals", "policy", "hot_money", "lockup"]
QUICK_ANALYSTS = ["market", "social", "fundamentals", "news"]     # 快速模式砍 3 个特化

@dataclass
class BatchResult:
    code: str; signal: str = ""; execution_advice: str = ""
    thesis: str = ""; status: str = "ok"; error: str = ""; state: dict = field(default_factory=dict)

def run_batch(pool: list[str], trade_date: str, config: dict,
              quick: bool = False, limit: int = 5) -> list[BatchResult]:
    results, analysts = [], QUICK_ANALYSTS if quick else ALL_ANALYSTS
    for raw in pool[:limit]:                          # v1 串行；并发需考虑 _em_get 全局锁
        code = safe_ticker_component(raw)             # 中文名/非法输入在此兜底
        try:
            graph = TradingAgentsGraph(selected_analysts=analysts, config=config)
            final_state, signal = graph.propagate(code, trade_date)   # trading_graph.py:446
            results.append(BatchResult(code, signal=signal,
                                       execution_advice=final_state.get("execution_advice", ""),
                                       thesis=_one_line(final_state), state=final_state))
        except Exception as e:                        # 独立失败隔离，不中断整批
            results.append(BatchResult(code, status="failed", error=str(e)))
    return results
```

### 2. 成本预估（写死估算公式，执行前打印）
```python
def estimate_calls(n: int, quick: bool, debate_rounds=1, risk_rounds=1) -> int:
    analysts = 4 if quick else 7
    per_stock = analysts + 2 * debate_rounds + 1 + risk_rounds * 3 + 1 + 1   # +质量门+PM+执行建议
    return n * per_stock
# 打印示例：5 标的全量 ≈ 5 × (7+2+1+3+1+1) = 75 次 LLM 调用（供用户确认）
```

### 3. 汇总渲染（`cli/main.py` 或 `tradingagents/batch/report.py`）
```python
def render_summary(results: list[BatchResult], out: Path):
    ok = [r for r in results if r.status == "ok"]
    ok.sort(key=lambda r: _RATING_RANK.get(r.signal, 9))          # Buy 优先
    lines = ["| 标的 | 评级 | 建议仓位 | 参考价位 | 一页理由 | 完整报告 |", "|---|---|---|---|---|---|"]
    for r in ok:
        lines.append(f"| {r.code} | {r.signal} | ... | ... | {r.thesis} | [报告]({r.code}_*)/complete_report.md |")
    lines.append("\n## 失败清单\n" + "\n".join(f"- {r.code}: {r.error}" for r in results if r.status != "ok"))
    out.write_text("\n".join(lines))
```

## 测试方法与步骤

### 测试文件与策略
| 文件 | 类型 | mock 策略 |
|------|------|-----------|
| `tests/test_batch.py` | unit | `monkeypatch` `TradingAgentsGraph.propagate` 返回假 `(state, signal)`；2-3 个标的 |
| `tests/test_batch_report.py` | unit | 固定 `BatchResult` 列表 → 汇总 markdown 断言（排序/失败清单/表头） |

### 关键用例
1. **失败隔离**：第 2 个标的 propagate 抛错 → 其余标的正常，结果含 `status="failed"` + 错误信息
2. **limit 截断**：pool 10 个 → 只跑 5 个
3. **quick 模式**：断言 `TradingAgentsGraph` 收到的 `selected_analysts == QUICK_ANALYSTS`
4. **安全边界**：pool 含中文名/非法输入 → 经 `safe_ticker_component` 转码或拒绝（不抛裸异常）
5. 汇总排序：Buy/Overweight/Hold/Sell 顺序正确；失败清单独立列出
6. 成本预估：`estimate_calls(5, quick=False) == 75`（固定公式回归）
7. 检查点：mock 续跑场景——重跑时已完成标的不重复执行（若实现续跑）

### 运行与验收步骤
```bash
python -m pytest tests/test_batch.py tests/test_batch_report.py -v    # 全 mock，离线可跑
python -m pytest tests/ -v -m "not integration"
# 手动冒烟（需真 LLM + 数据）：--limit 2 跑通 → 检查 summary.md 表格与完整报告链接
# 批量前置检查：先打印成本预估 → 用户确认 → 执行；EM_MIN_INTERVAL=1.5~2
```

## 手动测试场景（实际使用）

> 前置条件：`.env` 配置好 LLM provider；真实网络；先有 M3 的 `pool.csv` 或手写小标的池。
> ⚠️ 每次批量前先确认打印的成本预估（5 标的全量 ≈ 75 次 LLM 调用）。

### 场景 A：小批量全流程（核心场景）
**目的**：验证 2 标的批量分析端到端跑通。
1. 构造 `pool_small.csv`（2 只真实可交易标的，如 `600519,贵州茅台` / `000001,平安银行`）
2. 运行：`EM_MIN_INTERVAL=2 tradingagents batch --pool pool_small.csv --limit 2 --trade-date <当日>`
3. 观察：逐标的进度输出 → 成本预估打印 → 汇总生成
**预期**：2 个标的均 `status=ok`；`reports/batch_{ts}/summary.md` 表格含评级排序、建议仓位、参考价位、一页理由、完整报告链接；各链接可打开且含 VI 章节。

### 场景 B：快速模式对比
**目的**：验证 `--quick` 输出结构一致、耗时更短。
1. 同一 pool 分别跑 `--quick` 与全量模式（间隔 1s 以上）
2. 对比 summary.md 与单标的报告
**预期**：快速模式仅缺 policy/hot_money/lockup 三个分析师章节；评级与执行建议结构完整；耗时明显更短（约 30% 省调用）。

### 场景 C：失败隔离实测
**目的**：验证单个标的失败不中断整批。
1. 构造 `pool_bad.csv`：1 个正常标的 + 1 个非法代码（如 `999999`）+ 1 个已退市/停牌标的
2. 运行批量
**预期**：正常标的成功；非法标的在「失败清单」列出（原因明确，如解析失败）；整批不中断、不崩溃、无残留进程。

### 场景 D：断点续跑（checkpoint）
**目的**：验证中断后重跑跳过已完成标的。
1. 用 3 个标的跑批量，中途 Ctrl-C 中断（第一个已完成、第二个进行中）
2. 开启 `checkpoint_enabled` 重跑同一 pool
**预期**：已完成标的直接复用/跳过，未完成标的继续，最终汇总完整。

### 场景 E：成本与限流观察
**目的**：验证批量下的东财限流与 LLM 成本可控。
1. `--limit 5` 全量跑一次，记录耗时与调用数（与预估对比）
**预期**：LLM 调用数 ≈ 预估公式（±10%）；全程无东财 449；耗时记录可作为后续并发的基线。
