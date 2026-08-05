# M5 K线展示与走势预测

## 目标
标的分析完成后，在展示 UI 上显示该标的的**历史 K 线**（真实数据），并在 K 线末端叠加**预测走势**（未来 N 根虚拟 K 线，基于预测结果：评级方向 + M1 的目标价/止损位）。批量场景（M4）汇总页同样可用。

## 现状依据（调查结论）
- OHLCV 数据入口：`get_stock_data`（`tradingagents/dataflows/a_stock.py:557`）/ `_load_ohlcv_astock`（:476，mootdx→CSV 缓存→新浪 fallback，800 根日 K）
- Web 报告渲染：`web/components/report_viewer.py` 的 `render_report(final_state, ticker, ...)`（可展开章节模式，`_ANALYST_SECTIONS` 列表）
- 预测端点来源：M1 的 `ExecutionAdvice`（`target_price` / `stop_loss`）+ 5 档 `rating`（无 M1 时可回退）
- **依赖缺口**：pyproject 无任何绘图库 → 新增 `plotly`（交互蜡烛图，Streamlit 原生 `st.plotly_chart` 支持）

## 功能设计

### 原则
**预测 K 线用确定性路径生成，不用 LLM 生成 K 线形态**（LLM 画 OHLC 数组幻觉风险高、难校验）。预测路径锚定 M1 的价位端点，中间 K 线用可复现的随机游走（固定 seed），样式上明确区分预测区（虚线/半透明）。

### 1. 数据流
```
分析完成 → 现场取 OHLCV（或复用 state 已有数据）
        → 预测端点：execution_advice.target_price/stop_loss（M1）或 rating 系数回退
        → build_chart_data() 生成 {history, forecast} → 落盘 chart_data.json 到报告目录
        → Web 报告页读取 → plotly 蜡烛图（历史实线 + 预测虚线）
```

### 2. 预测端点回退规则（无 M1 时）
| rating | 预测终点 |
|--------|----------|
| Buy | 现价 × 1.08 |
| Overweight | 现价 × 1.05 |
| Hold | 现价 ± 2% 内震荡 |
| Underweight | 现价 × 0.95 |
| Sell | 现价 × 0.90 |

有 `execution_advice` 时：Buy/Overweight → `target_price`；Sell/Underweight → `stop_loss`（M1 保证 stop < 现价 < target）。

### 3. 预测窗口
默认 `forecast_days = 10`（交易日，可配 config `forecast_days`）。

## 核心代码片段

### 0. 新增依赖
```
pyproject.toml: "plotly>=6.0"     # ⚠️ 新增依赖后跑 uv lock --dry-run 验证（CLAUDE.md 规范）
```

### 1. 新模块 `tradingagents/charting/kline.py`
```python
from dataclasses import dataclass
import numpy as np
import pandas as pd
from tradingagents.dataflows.a_stock import get_stock_data

@dataclass
class ForecastSpec:
    days: int = 10
    endpoint: float | None = None    # M1 的 target_price / stop_loss
    direction: str = "up"            # up / down / sideways（由 rating 推导）

_FALLBACK_ENDPOINT = {"Buy": 1.08, "Overweight": 1.05, "Hold": 1.0,
                      "Underweight": 0.95, "Sell": 0.90}

def _forecast_spec(advice, rating: str, days: int) -> ForecastSpec:
    if advice is not None and advice.target_price:              # M1 端点优先
        direction = "up" if rating in ("Buy", "Overweight") else "down"
        endpoint = advice.target_price if direction == "up" else advice.stop_loss
        return ForecastSpec(days, endpoint, direction)
    last = 0.0  # 占位，实际由调用方传入现价
    return ForecastSpec(days, None, "up")                        # 回退系数在 _synthesize 内应用

def build_chart_data(ticker: str, trade_date: str, advice=None,
                     rating: str = "Hold", forecast_days: int = 10) -> dict:
    ohlcv = get_stock_data(ticker, trade_date)                   # a_stock.py:557
    hist = ohlcv[["open", "high", "low", "close"]].tail(120).reset_index()
    fut = _synthesize_forecast(hist, advice, rating, forecast_days)
    return {"ticker": ticker, "history": hist.to_dict("records"),
            "forecast": fut, "rating": rating}

def _synthesize_forecast(hist, advice, rating, days) -> list[dict]:
    last = float(hist.iloc[-1]["close"])
    spec = _forecast_spec(advice, rating, days)
    end = spec.endpoint if spec.endpoint else last * _FALLBACK_ENDPOINT.get(rating, 1.0)
    rng = np.random.default_rng(42)                              # 固定 seed → 可复现
    path = np.linspace(last, end, days + 1) + rng.normal(0, last * 0.004, days + 1)
    rows, prev_close = [], last
    for i in range(days):                                        # 每根：open=前close
        o, c = prev_close, path[i + 1]
        hi = max(o, c) + abs(rng.normal(0, last * 0.006))
        lo = min(o, c) - abs(rng.normal(0, last * 0.006))
        rows.append({"open": round(o, 2), "high": round(hi, 2),
                     "low": round(lo, 2), "close": round(c, 2), "forecast": True})
        prev_close = c
    return rows
```

### 2. Web 组件 `web/components/kline_viewer.py`
```python
import plotly.graph_objects as go
import streamlit as st

def render_kline(st, chart_data: dict) -> None:
    h, f = chart_data["history"], chart_data["forecast"]
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=[r["index"] for r in h], open=[r["open"] for r in h],
        high=[r["high"] for r in h], low=[r["low"] for r in h],
        close=[r["close"] for r in h], name="历史"))
    if f:
        fig.add_trace(go.Candlestick(
            x=list(range(len(h), len(h) + len(f))), open=[r["open"] for r in f],
            high=[r["high"] for r in f], low=[r["low"] for r in f],
            close=[r["close"] for r in f], name="预测",
            increasing_line_color="rgba(34,197,94,.7)", decreasing_line_color="rgba(239,68,68,.7)"))
    fig.update_layout(xaxis_rangeslider_visible=False, height=420, showlegend=True)
    st.plotly_chart(fig, use_container_width=True)
```

### 3. 报告页挂载（`web/components/report_viewer.py` 的 `render_report` 内新增）
```python
with st.expander("📈 K线走势与预测", expanded=True):
    chart = _load_chart_data(final_state)   # 优先读报告目录 chart_data.json，否则现场 build
    if chart:
        render_kline(st, chart)
    else:
        st.caption("K线数据暂不可用（OHLCV 获取失败）")
```

### 4. 落盘（分析结束时写入报告目录，供历史报告离线查看）
```python
# cli/main.py 或 web/runner.py finalize 处
chart_data = build_chart_data(ticker, trade_date, advice=final_state.get("execution_advice"), rating=signal)
(results_dir / f"{ticker}_{ts}" / "chart_data.json").write_text(json.dumps(chart_data, ensure_ascii=False))
```

## 单元/集成测试

| 文件 | 类型 | mock 策略 |
|------|------|-----------|
| `tests/test_kline.py` | unit | `monkeypatch` `get_stock_data` 返回固定 OHLCV DataFrame（120 行） |
| `tests/test_kline_viewer.py` | unit | 构造假 `chart_data`，断言 figure trace 数量与名称（plotly 是纯数据构造，可离线测） |

### 关键用例
1. `_synthesize_forecast`：输出 `days` 根、每根 `forecast=True`；`open=前close`；`high ≥ max(o,c)`、`low ≤ min(o,c)`
2. 端点：有 advice 且 Buy → 终点 = `target_price`；Sell → 终点 = `stop_loss`；无 advice → 回退系数（Buy ×1.08）
3. **可复现**：同输入两次调用输出完全一致（seed=42）
4. `build_chart_data`：返回 `{ticker, history(≤120), forecast, rating}` 结构；history 无 `forecast` 键
5. 渲染：figure 恰有 2 个 trace（有预测）或 1 个（无预测）；预测 trace 与历史区分
6. 落盘/读取：`chart_data.json` 可 round-trip（JSON 序列化/反序列化后结构不变）

### 运行命令
```bash
python -m pytest tests/test_kline.py tests/test_kline_viewer.py -v
python -m pytest tests/ -v -m "not integration"     # 全量回归（新依赖后先 uv lock --dry-run）
```

## 手动测试场景（实际使用）

> 前置条件：`pip install -e ".[plotly]"`（或加依赖后重装）；`.env` 配置好 LLM。

### 场景 A：单标的 K 线 + 预测（核心场景）
**目的**：验证 Web 展示历史 K 线并叠加预测走势。
1. `streamlit run web/app.py` → 侧栏输入一只 Buy 倾向的标的 → 分析完成
2. 报告页展开「📈 K线走势与预测」
**预期**：历史 120 根实线蜡烛图；末端追加 10 根虚线/半透明预测蜡烛；预测终点高于现价（Buy）；缩放/悬停交互正常。

### 场景 B：评级方向差异
**目的**：验证预测方向随评级变化。
1. 分别分析一只强势股与一只弱势股（或同标的换日期）
**预期**：Buy/Overweight → 预测向上（终点≈M1 target）；Sell/Underweight → 预测向下（终点≈stop_loss）；Hold → 平缓震荡。三种方向肉眼可辨。

### 场景 C：历史报告离线查看
**目的**：验证已完成的分析重新打开仍有 K 线（不重新联网）。
1. 完成一次分析后关闭页面，再次从「历史」入口打开该报告
**预期**：K 线正常渲染——数据来自报告目录 `chart_data.json`，与首次展示一致（含预测区）。

### 场景 D：批量页展示（M4 联动）
**目的**：验证批量汇总中每只标的可展开 K 线。
1. M4 批量分析完成后，在 summary 表每行「K线」入口点击展开
**预期**：每标的显示其历史 K 线 + 对应评级的预测走势；失败清单中的标的显示占位。

### 场景 E：数据缺失兜底
**目的**：验证 OHLCV 获取失败时不崩 UI。
1. 分析一只长期停牌/数据缺失的标的（若有）
**预期**：显示「K线数据暂不可用」提示，报告其余部分正常。

## 风险与边界
- 预测区是**示意性路径**（锚定 M1 价位 + 随机游走），不是真实未来行情——图内必须标注「预测/示意」
- plotly 新增依赖：跑 `uv lock --dry-run` 验证；若 uv 锁不上再评估备选（matplotlib 静态 PNG 仅 CLI）
- 预测 K 线用 `rng` 固定 seed，同一标的每次展示一致；后续若想更贴近 LLM 观点，可扩展 `ForecastSpec` 注入趋势斜率
