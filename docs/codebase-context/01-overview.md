# 项目概述与技术栈

## 项目定位

A 股深度特化的**多 Agent 投研框架**（fork 自 TauricResearch/TradingAgents）。给量化/投研用户：输入一只 A 股代码与交易日，7 个 Analyst 角色各自取数分析，经 Bull/Bear 多空辩论 + 三方（激进/保守/中立）风险辩论，最终由 Portfolio Manager 汇总生成结构化投资决策报告。核心差异化是**数据层全直连 HTTP、零第三方数据库依赖**，并对 A 股特有场景（政策、游资、解禁）做了角色扩展。

## 技术栈

| 层 | 技术 | 版本 |
| ---- | ---- | ---- |
| 语言 | Python | >=3.10 |
| Agent 编排 | LangGraph | >=0.4.8 |
| LLM 抽象 | LangChain (core/openai/anthropic/experimental) | core>=0.3.81 |
| 结构化输出 | Pydantic (BaseModel/Enum) | 随 langchain-core |
| Web UI | Streamlit | >=1.45.0 |
| CLI | Typer + questionary + rich | typer>=0.21.0 |
| A 股行情数据 | mootdx（TCP 7709） | >=0.10.0 |
| 检查点 | langgraph-checkpoint-sqlite | >=2.0.0 |
| 缓存 | redis | >=6.2.0 |
| PDF 导出 | fpdf2 | >=2.8.6 |
| 回测 | backtrader | >=1.9.78 |

- 打包: setuptools（`pyproject.toml`），非 npm 项目
- 可选依赖:
  - `[google]` → langchain-google-genai（避开 mootdx 的 httpx 版本冲突，默认不装）
  - `[agentsdk]` → claude-agent-sdk（个人 Claude Max 订阅 provider；同样顶 httpx>=0.28.1 与 mootdx 冲突，默认不装）

## 脚本命令

| 命令 | 作用 |
| ---- | ---- |
| `pip install -e .` | 安装（需 Google 模型加 `.[google]`） |
| `tradingagents` / `python main.py` | 启动 CLI（entry: `cli.main:app`） |
| `tradingagents-web` / `streamlit run web/launch.py` | 启动 Web UI（entry: `web.launch:main`） |
| `python -m pytest tests/ -v` | 运行测试 |

## 环境变量（仅键名与用途，不含值）

| 键 | 用途 | 来源 |
| ---- | ---- | ---- |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` / `DEEPSEEK_API_KEY` / `XAI_API_KEY` / `DASHSCOPE_API_KEY` / `ZHIPU_API_KEY` / `MINIMAX_API_KEY` / `OPENROUTER_API_KEY` | 各 LLM 提供商密钥 | .env.example |
| `BACKEND_URL` | 中转/代理网关地址（可选，全局模型请求走此址） | .env.example |
| `EM_MIN_INTERVAL` | 东财接口节流最小间隔（默认 1.0s） | CLAUDE.md / a_stock.py |
| `TRADINGAGENTS_RESULTS_DIR` / `TRADINGAGENTS_CACHE_DIR` / `TRADINGAGENTS_MEMORY_LOG_PATH` | 结果/缓存/记忆日志落盘路径 | default_config.py |
