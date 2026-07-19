# METRICS — 1.agent-sdk-max-provider

| 项 | 值 |
| ---- | ---- |
| 人工介入(执行中暂停) | 0（全程自主;入口闸审批不计） |
| 代码审查轮次 | 1（N4） |
| 审查通道 | Codex **降级** → 对抗式子代理（Codex exec 超时 10min,无文件范围漫游全仓库) |
| 审查拦截 | 1（RateLimitEvent 过度降级,高危,已修+加测试） |
| 规格期对抗审查 | 2 轮(9.5 方案 + 10.6 拆分,均 Codex,10+3 条采纳) |
| 自主决策留痕 | 3(见运行日志 decision:批量提交粒度/env 不清空 API_KEY/RateLimit 语义修法) |
| 测试 | 16 新单测,全量 151 passed / 1 skipped(google extra) |

## 备注
- 审查列带 `降级` 标注:本次 N4 未走 Codex 双模型,走对抗式子代理(子代理自行拉取 SDK 源码核对,质量可接受)。
- T-009(本机端到端冒烟)需用户本人 `claude setup-token` 登录 Max,无法代跑,标记待用户。
