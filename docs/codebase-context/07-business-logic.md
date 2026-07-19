# 关键业务逻辑

## 主线路：一次完整分析（输入代码 → 投资决策报告）

**线路**：
`前端（cli/main.py | web/runner.py）` 构造 config
→ `graph/trading_graph.py:TradingAgentsGraph.__init__`（:61）
→ `propagate(company_name, trade_date)`（:301）→ `prepare_graph_run`（:310）→ `_run_graph`（:398）
→ LangGraph 依次执行：**7 Analysts 取数分析 → Bull/Bear 多空辩论 → 三方风险辩论 → Research Manager 汇总 → Trader 提案 → Portfolio Manager 终裁**
→ `finalize_graph_run`（:369）→ `process_signal`（:465）产出 `PortfolioDecision`
→ 落盘报告（results_dir）/ Web 侧渲染 + 可选 PDF 导出

每个 Analyst 节点内：LLM 决定调用哪个数据工具 → 工具经 `interface.route_to_vendor` → vendor（默认 a_stock）取数 → 回填分析段。

**关键规则**：

- **中文 ticker 自动解析**：用户/LLM 传中文股票名 → `dataflows/utils.py:safe_ticker_component` 检测中文 → `a_stock.py:resolve_ticker`（:115）→ `_build_name_code_map`（mootdx 全市场映射，缓存）→ 6 位代码。链路见 CLAUDE.md「中文股票名解析链路」。
- **路径安全边界**：任何把 ticker 拼进文件路径处，必须先过 `safe_ticker_component`（白名单 `^[A-Za-z0-9._\-\^]+$`）。这是唯一安全边界，改动须慎重。
- **东财限流**：a_stock.py 内所有 eastmoney 请求走 `_em_get`（串行时间戳 + 抖动 + Session 复用），`EM_MIN_INTERVAL` 可调；仅东财受限，其余源不受影响。
- **vendor fallback**：主 vendor 失败自动降级到其余可用 vendor（`interface.py:route_to_vendor`）。
- **辩论轮次**：由 `max_debate_rounds` / `max_risk_discuss_rounds`（default_config）经 `conditional_logic.py` 控制循环。

**边界与注意**：

- 新闻工具会校验 ticker，防止把概念词误当代码导致 A 股分析中断（v0.2.18 修复，见 news_analyst.py / news_data_tools.py）。
- `fpdf` 导入有守卫，防启动崩溃（v0.2.17）。
- mootdx 0.11.x 有防崩处理（v0.2.15）。
- 检查点续跑：`checkpoint_enabled` + `graph/checkpointer.py`，Web 侧栏可 resume 中断的分析。

## 交易记忆

**线路**：分析过程 → `agents/utils/memory.py` → 落盘 `memory_log_path`（默认 `~/.../memory/trading_memory.md`）→ `graph/reflection.py` 供后续反思复用。

## 结构化决策产出

**线路**：各决策角色 LLM 输出 → `agents/utils/structured.py` 解析校验为 `agents/schemas.py` 的 `ResearchPlan` / `TraderProposal` / `PortfolioDecision` → `quality_gate.py` 质量闸门 → 报告。
