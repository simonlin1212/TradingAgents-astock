# PR #18（hejingchi）— start_date 功能 + 主题切换 + Windows 字体

**状态**: 已归档（2026-08）· 不直接 merge
**来源**: https://github.com/simonlin1212/TradingAgents-astock/pull/18

## 内容
1. start_date 功能（数据起始日期 / 按月分析）
2. 主题切换
3. Windows 字体

## 处理结果
- **start_date 已由项目独立落地**（v0.2.21，#16）：`market_lookback_days` config 键 + `get_stock_data` / `get_indicators` 的 `look_back_days` 参数注入，Web 侧栏「数据起始日期」/ CLI Step 2b。感谢 @hejingchi 提供的定位思路；实现单独干净落地，未夹带字体/主题改动（见 CHANGELOG.md [0.2.21]）。
- **主题切换 / Windows 字体**：未落地，无后续计划记录。

## 归档原因
与 v0.2.6 架构冲突，不建议直接 merge；其中可落地的 start_date 功能已独立实现，故从 CLAUDE.md「待处理」移入本归档。
