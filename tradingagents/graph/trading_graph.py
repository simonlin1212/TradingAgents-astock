# TradingAgents/graph/trading_graph.py

import logging
import os
from pathlib import Path
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, List, Optional

import yfinance as yf

logger = logging.getLogger(__name__)

from langgraph.prebuilt import ToolNode

from tradingagents.llm_clients import create_llm_client

from tradingagents.agents import *
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.dataflows.utils import safe_ticker_component
from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)
from tradingagents.dataflows.config import set_config

# Import the new abstract tool methods from agent_utils
from tradingagents.agents.utils.agent_utils import (
    get_stock_data,
    get_indicators,
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_news,
    get_insider_transactions,
    get_global_news,
    get_profit_forecast,
    get_hot_stocks,
    get_northbound_flow,
    get_concept_blocks,
    get_fund_flow,
    get_dragon_tiger_board,
    get_lockup_expiry,
    get_industry_comparison,
)

from .checkpointer import checkpoint_step, clear_checkpoint, get_checkpointer, thread_id
from .conditional_logic import ConditionalLogic
from .setup import ROLE_KEYS, GraphSetup
from .propagation import Propagator
from .reflection import Reflector
from .signal_processing import SignalProcessor

# 七个分析师角色——它们受 `selected_analysts` 控制，没选中就不会进图。
_ANALYST_ROLES = frozenset({
    "market", "social", "news", "fundamentals", "policy", "hot_money", "lockup",
})

# 各家 provider 私有的参数：换了 provider 就不能带过去（别家可能直接拒收）。
_PROVIDER_SPECIFIC_KWARGS = frozenset({
    "reasoning_effort",   # openai
    "thinking_level",     # google
    "effort",             # anthropic
})


def _normalize_yfinance_ticker(ticker: str) -> str:
    """Return the Yahoo Finance symbol for a ticker used by the graph.

    A-stock decisions are stored with their six-digit code (for example
    ``600519``), while Yahoo Finance requires an exchange suffix for mainland
    China listings (``600519.SS``).  Without the suffix ``Ticker.history``
    usually returns an empty frame, so deferred memory outcomes remain pending
    indefinitely.  Common A-share prefixes/suffixes are normalized as well;
    non-A-share symbols remain unchanged so the graph remains usable for other
    markets too.
    """
    symbol = str(ticker).strip().upper()

    # The A-stock layer accepts SH/SZ/BJ prefixes and uses .SH for Shanghai,
    # whereas Yahoo uses .SS.  Normalize those forms before handling bare
    # six-digit codes. Yahoo has no Beijing exchange suffix, so keep BJ codes
    # unqualified instead of inventing a symbol that cannot return data.
    if (
        len(symbol) == 9
        and symbol[:6].isdigit()
        and symbol[6:] in (".SH", ".SZ", ".BJ")
    ):
        code, exchange = symbol[:6], symbol[7:]
        if exchange == "SH":
            return f"{code}.SS"
        if exchange == "SZ":
            return f"{code}.SZ"
        return code
    if (
        len(symbol) == 8
        and symbol[:2] in ("SH", "SZ", "BJ")
        and symbol[2:].isdigit()
    ):
        code, exchange = symbol[2:], symbol[:2]
        if exchange == "SH":
            return f"{code}.SS"
        if exchange == "SZ":
            return f"{code}.SZ"
        return code

    if len(symbol) != 6 or not symbol.isdigit():
        return symbol

    # The 920xxx range is Beijing-listed; Yahoo has no supported suffix for it.
    if symbol.startswith("92"):
        return symbol
    # Shanghai-listed A shares, B shares and ETFs use the .SS suffix on Yahoo.
    if symbol.startswith(("5", "6", "9")):
        return f"{symbol}.SS"
    # Other Beijing-listed six-digit ranges are not covered by Yahoo either.
    if symbol.startswith(("4", "8")):
        return symbol
    # Shenzhen-listed stocks (000/001/002/003/300/301, etc.).
    return f"{symbol}.SZ"


def _is_unsupported_by_yfinance(symbol: str) -> bool:
    """True for codes Yahoo Finance has no coverage for at all.

    Beijing Stock Exchange listings (920xxx current, 43x/83x/87x legacy) are
    absent from Yahoo under every suffix — verified 2026-07-31: ``920002``,
    ``920002.BJ``, ``920002.SS`` and ``920002.SZ`` all return an empty frame.
    Retrying them every run only burns a request and leaves the memory entry
    pending forever with no stated reason, so short-circuit and say why once.
    """
    return (
        len(symbol) == 6
        and symbol.isdigit()
        and (symbol.startswith("92") or symbol[:2] in ("43", "83", "87"))
    )


class TradingAgentsGraph:
    """Main class that orchestrates the trading agents framework."""

    def __init__(
        self,
        selected_analysts=["market", "social", "news", "fundamentals", "policy", "hot_money", "lockup"],
        debug=False,
        config: Dict[str, Any] = None,
        callbacks: Optional[List] = None,
    ):
        """Initialize the trading agents graph and components.

        Args:
            selected_analysts: List of analyst types to include
            debug: Whether to run in debug mode
            config: Configuration dictionary. If None, uses default config
            callbacks: Optional list of callback handlers (e.g., for tracking LLM/tool stats)
        """
        self.debug = debug
        self.config = config or DEFAULT_CONFIG
        self.callbacks = callbacks or []

        # Update the interface's config
        set_config(self.config)

        # Create necessary directories
        os.makedirs(self.config["data_cache_dir"], exist_ok=True)
        os.makedirs(self.config["results_dir"], exist_ok=True)

        # Initialize LLMs with provider-specific thinking configuration
        llm_kwargs = self._get_provider_kwargs()

        # Add callbacks to kwargs if provided (passed to LLM constructor)
        if self.callbacks:
            llm_kwargs["callbacks"] = self.callbacks

        # Optional: route nodes through a personal Claude Pro/Max subscription
        # via the Claude Agent SDK. `deep_think_provider_override` covers the
        # deep nodes (Research / Portfolio Manager); `quick_think_provider_override`
        # covers the quick nodes (7 tool-using analysts + Bull/Bear / trader /
        # risk debaters). Both on ⇒ every node runs on the subscription. Off by
        # default — behaviour is unchanged when both are None.
        deep_on = self.config.get("deep_think_provider_override") == "claude_agent_sdk"
        quick_on = self.config.get("quick_think_provider_override") == "claude_agent_sdk"

        # F-004 guardrail: ANTHROPIC_API_KEY outranks the subscription OAuth token
        # and would silently bill the pay-per-token API instead of the subscription.
        # Refuse to start rather than surprise-bill the user.
        if (deep_on or quick_on) and os.getenv("ANTHROPIC_API_KEY"):
            # 该 key 优先级高于订阅凭据，泄进 Agent SDK 子进程就会悄悄走按 token
            # 计费的 API。客户端已在子进程环境里把它显式置空，所以这里**不再一律
            # 中止**——否则把 anthropic 用作降级 provider 就成了死结：留着 key 启动
            # 被拦，删掉 key 又会在撞额度真要降级时认证失败。
            logger.warning(
                "ANTHROPIC_API_KEY is set while the claude_agent_sdk override is on. "
                "It is stripped from the Agent SDK subprocess so subscription quota is "
                "used, and kept in this process only so an `anthropic` fallback can "
                "still authenticate. If you did not intend to keep a paid Anthropic "
                "fallback, unset it."
            )

        # 降级配置必须成对给：只改 provider 不改 model，会把主 provider 的模型名
        # 配到另一家去（如 AnthropicClient(model="deepseek-chat")），而这条路径
        # **恰好在撞额度、最需要它工作的时候才被走到**——那时再炸就太晚了。
        # 启动时就校验，而不是留到运行中。
        _fb_provider = self.config.get("agent_sdk_fallback_provider")
        _fb_model = self.config.get("agent_sdk_fallback_model")
        if (deep_on or quick_on) and bool(_fb_provider) != bool(_fb_model):
            missing = "agent_sdk_fallback_model" if _fb_provider else "agent_sdk_fallback_provider"
            given = "agent_sdk_fallback_provider" if _fb_provider else "agent_sdk_fallback_model"
            raise ValueError(
                f"{given} is set but {missing} is not — the two must be configured "
                f"together. Otherwise the fallback pairs one provider with another "
                f"provider's model name and fails exactly when the subscription hits "
                f"its quota. Set both, or leave both unset to fall back to "
                f"llm_provider + its own model."
            )

        def _make_client(override_on, sdk_model_key, fallback_model_key):
            """Build a subscription-backed client when overridden, else the normal
            llm_provider client. Fallback rejoins the paid provider on quota/failure."""
            if override_on:
                # backend_url 是为 llm_provider 配的端点。显式指定了**另一家**
                # provider 做降级时不能把它带过去（例如把 anthropic 降级请求发到
                # MiniMax 网关），否则同样是撞额度那一刻才炸。None ⇒ 该 provider
                # 用自己的默认端点。
                cross_provider = bool(_fb_provider) and _fb_provider != self.config["llm_provider"]
                fallback_spec = {
                    "provider": _fb_provider or self.config["llm_provider"],
                    "model": _fb_model or self.config[fallback_model_key],
                    "base_url": None if cross_provider else self.config.get("backend_url"),
                    # 带上 callbacks：降级意味着**开始计费**，此时统计/成本回调
                    # 反而看不到这些调用的话，恰好在花钱的时候统计是瞎的。
                    **({"callbacks": self.callbacks} if self.callbacks else {}),
                    # 用户显式配的输出上限也要带过去。否则撞额度降级之后，降级
                    # provider 用它自己的默认上限，报告照样被截断——而这正是
                    # 用户配 max_tokens 想避免的事（#91）。
                    **({"max_tokens": self.config["max_tokens"]}
                       if self.config.get("max_tokens") else {}),
                }
                return create_llm_client(
                    provider="claude_agent_sdk",
                    model=self.config[sdk_model_key],
                    base_url=self.config.get("backend_url"),
                    fallback_spec=fallback_spec,
                )
            return create_llm_client(
                provider=self.config["llm_provider"],
                model=self.config[fallback_model_key],
                base_url=self.config.get("backend_url"),
                **llm_kwargs,
            )

        deep_client = _make_client(deep_on, "agent_sdk_model", "deep_think_llm")
        quick_client = _make_client(quick_on, "agent_sdk_quick_model", "quick_think_llm")

        self.deep_thinking_llm = deep_client.get_llm()
        self.quick_thinking_llm = quick_client.get_llm()

        # 可选：给单个角色指定模型（#39）。不配 = 完全维持 quick/deep 两档的原行为。
        self.role_llms = self._build_role_llms(
            llm_kwargs, deep_on or quick_on, selected_analysts
        )

        self.memory_log = TradingMemoryLog(self.config)

        # Create tool nodes
        self.tool_nodes = self._create_tool_nodes()

        # Initialize components
        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config["max_debate_rounds"],
            max_risk_discuss_rounds=self.config["max_risk_discuss_rounds"],
        )
        self.graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.tool_nodes,
            self.conditional_logic,
            resolve_llm=self.role_llms.get,
        )

        self.propagator = Propagator()
        self.reflector = Reflector(self.quick_thinking_llm)
        self.signal_processor = SignalProcessor(self.quick_thinking_llm)

        # State tracking
        self.curr_state = None
        self.ticker = None
        self.log_states_dict = {}  # date to full state dict

        # Set up the graph: keep the workflow for recompilation with a checkpointer.
        self.workflow = self.graph_setup.setup_graph(selected_analysts)
        self.graph = self.workflow.compile()
        self._checkpointer_ctx = None

    def _build_role_llms(
        self,
        llm_kwargs: Dict[str, Any],
        subscription_on: bool,
        selected_analysts=None,
    ) -> Dict[str, Any]:
        """按 `config["role_llms"]` 给单个角色单独建 LLM（#39）。

        默认是空表 —— 不配任何角色时行为与以前完全一致（全部走 quick/deep 两档）。
        配了才有意义：让多空辩手用不同厂商的模型，避免同源模型互相不反驳。

        相同 (provider, model, endpoint) 的角色复用同一个实例，不会因为写了 7 个
        角色就建 7 条连接。
        """
        specs = self.config.get("role_llms") or {}
        if not specs:
            return {}

        unknown = sorted(set(specs) - set(ROLE_KEYS))
        if unknown:
            raise ValueError(
                f"role_llms 里有无法识别的角色名：{unknown}。"
                f"合法角色：{', '.join(ROLE_KEYS)}。"
                f"（写错的角色名如果被静默忽略，你会以为配置生效了，实际没有。）"
            )

        # 没被选中的分析师不会进图，就别为它建模型：那会让一个**永远不执行**的节点
        # 因为缺 API key 或缺可选依赖，把一次本来完全正常的分析在启动时就打断。
        if selected_analysts is not None:
            active = set(selected_analysts)
            skipped = [r for r in specs if r in _ANALYST_ROLES and r not in active]
            if skipped:
                specs = {k: v for k, v in specs.items() if k not in skipped}
                logger.info(
                    "role_llms: 跳过未选中的分析师角色 %s（不建模型）",
                    ", ".join(sorted(skipped)),
                )
            if not specs:
                return {}

        if subscription_on:
            # 订阅覆盖是为了不产生 API 账单，这里显式点名哪些角色会绕开它去计费，
            # 不能让人以为"全部走订阅"却在某几个角色上悄悄花钱。
            logger.warning(
                "role_llms 为以下角色单独指定了模型，它们会绕开 claude_agent_sdk "
                "订阅覆盖、按 token 计费：%s", ", ".join(sorted(specs)),
            )

        main_provider = self.config["llm_provider"]
        cache: Dict[tuple, Any] = {}
        resolved: Dict[str, Any] = {}
        for role, spec in specs.items():
            if not isinstance(spec, dict) or not spec.get("model"):
                raise ValueError(
                    f"role_llms['{role}'] 必须是带 model 的字典，"
                    f'例如 {{"provider": "deepseek", "model": "deepseek-chat"}}。'
                )
            provider = spec.get("provider") or main_provider
            # backend_url 是给主 provider 配的端点。换了厂商还把它带过去，请求就会
            # 发到另一家的网关（和 agent_sdk 降级那里同一个坑）。None = 用该
            # provider 自己的默认端点。
            if "backend_url" in spec:
                base_url = spec["backend_url"]
            elif provider.lower() == str(main_provider).lower():
                base_url = self.config.get("backend_url")
            else:
                base_url = None

            # 主 provider 的**专属**参数不能带给另一家：openai 的
            # `reasoning_effort`、google 的 `thinking_level`、anthropic 的 `effort`
            # 都是各家私有的，塞进 qwen / glm / 自建网关的请求体里可能直接被拒。
            # 通用参数（max_tokens / callbacks 等）保留。
            role_kwargs = (
                llm_kwargs if provider.lower() == str(main_provider).lower()
                else {k: v for k, v in llm_kwargs.items()
                      if k not in _PROVIDER_SPECIFIC_KWARGS}
            )

            key = (provider.lower(), spec["model"], base_url)
            if key not in cache:
                cache[key] = create_llm_client(
                    provider=provider,
                    model=spec["model"],
                    base_url=base_url,
                    **role_kwargs,
                ).get_llm()
            resolved[role] = cache[key]

        logger.info(
            "role_llms: %d 个角色单独配置，实际建了 %d 个模型实例",
            len(resolved), len(cache),
        )
        return resolved

    def _get_provider_kwargs(self) -> Dict[str, Any]:
        """Get provider-specific kwargs for LLM client creation."""
        kwargs = {}
        provider = self.config.get("llm_provider", "").lower()

        # 与 provider 无关：单次回复的输出上限。撞上它就是报告写一半被截断（#91）。
        max_tokens = self.config.get("max_tokens")
        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        if provider == "google":
            thinking_level = self.config.get("google_thinking_level")
            if thinking_level:
                kwargs["thinking_level"] = thinking_level

        elif provider == "openai":
            reasoning_effort = self.config.get("openai_reasoning_effort")
            if reasoning_effort:
                kwargs["reasoning_effort"] = reasoning_effort

        elif provider == "anthropic":
            effort = self.config.get("anthropic_effort")
            if effort:
                kwargs["effort"] = effort

        return kwargs

    def _create_tool_nodes(self) -> Dict[str, ToolNode]:
        """Create tool nodes for different data sources using abstract methods."""
        return {
            "market": ToolNode(
                [
                    # Core stock data tools
                    get_stock_data,
                    # Technical indicators
                    get_indicators,
                ]
            ),
            "social": ToolNode(
                [
                    # 情绪分析不只读新闻：资金流是最硬的情绪证据，量价给强度，
                    # 强势股榜给热度归因，新闻负责解释成因（#61）。
                    get_news,
                    get_fund_flow,
                    get_hot_stocks,
                    get_stock_data,
                ]
            ),
            "news": ToolNode(
                [
                    # News and insider information
                    get_news,
                    get_global_news,
                    get_insider_transactions,
                ]
            ),
            "fundamentals": ToolNode(
                [
                    get_fundamentals,
                    get_balance_sheet,
                    get_cashflow,
                    get_income_statement,
                    get_profit_forecast,
                    get_industry_comparison,
                ]
            ),
            "policy": ToolNode(
                [
                    get_news,
                    get_global_news,
                ]
            ),
            "hot_money": ToolNode(
                [
                    get_stock_data,
                    get_news,
                    get_insider_transactions,
                    get_hot_stocks,
                    get_northbound_flow,
                    get_concept_blocks,
                    get_fund_flow,
                    get_dragon_tiger_board,
                    get_industry_comparison,
                ]
            ),
            "lockup": ToolNode(
                [
                    get_insider_transactions,
                    get_news,
                    get_fundamentals,
                    get_lockup_expiry,
                ]
            ),
        }

    def _fetch_returns(
        self, ticker: str, trade_date: str, holding_days: int = 5
    ) -> Tuple[Optional[float], Optional[float], Optional[int]]:
        """Fetch raw and alpha return for ticker over holding_days from trade_date.

        Returns (raw_return, alpha_return, actual_holding_days) or
        (None, None, None) if price data is unavailable (too recent, delisted,
        or network error).
        """
        try:
            start = datetime.strptime(trade_date, "%Y-%m-%d")
            end = start + timedelta(days=holding_days + 7)  # buffer for weekends/holidays
            end_str = end.strftime("%Y-%m-%d")

            yf_symbol = _normalize_yfinance_ticker(ticker)
            if _is_unsupported_by_yfinance(yf_symbol):
                # Say why instead of leaving a silent forever-pending entry.
                logger.warning(
                    "Cannot resolve outcome for %s: Yahoo Finance has no Beijing "
                    "Stock Exchange coverage under any suffix, so this entry stays "
                    "pending. Use a non-BSE ticker if you need memory reflection.",
                    ticker,
                )
                return None, None, None

            stock = yf.Ticker(yf_symbol).history(start=trade_date, end=end_str)
            benchmark = yf.Ticker("000300.SS").history(start=trade_date, end=end_str)

            if len(stock) < 2 or len(benchmark) < 2:
                return None, None, None

            actual_days = min(holding_days, len(stock) - 1, len(benchmark) - 1)
            raw = float(
                (stock["Close"].iloc[actual_days] - stock["Close"].iloc[0])
                / stock["Close"].iloc[0]
            )
            bench_ret = float(
                (benchmark["Close"].iloc[actual_days] - benchmark["Close"].iloc[0])
                / benchmark["Close"].iloc[0]
            )
            alpha = raw - bench_ret
            return raw, alpha, actual_days
        except Exception as e:
            logger.warning(
                "Could not resolve outcome for %s on %s (will retry next run): %s",
                ticker, trade_date, e,
            )
            return None, None, None

    def _resolve_pending_entries(self, ticker: str) -> None:
        """Resolve pending log entries for ticker at the start of a new run.

        Fetches returns for each same-ticker pending entry, generates reflections,
        then writes all updates in a single atomic batch write to avoid redundant I/O.
        Skips entries whose price data is not yet available (too recent or delisted).

        Trade-off: only same-ticker entries are resolved per run.  Entries for
        other tickers accumulate until that ticker is run again.
        """
        pending = [e for e in self.memory_log.get_pending_entries() if e["ticker"] == ticker]
        if not pending:
            return

        updates = []
        for entry in pending:
            raw, alpha, days = self._fetch_returns(ticker, entry["date"])
            if raw is None:
                continue  # price not available yet — try again next run
            reflection = self.reflector.reflect_on_final_decision(
                final_decision=entry.get("decision", ""),
                raw_return=raw,
                alpha_return=alpha,
            )
            updates.append({
                "ticker": ticker,
                "trade_date": entry["date"],
                "raw_return": raw,
                "alpha_return": alpha,
                "holding_days": days,
                "reflection": reflection,
            })

        if updates:
            self.memory_log.batch_update_with_outcomes(updates)

    def propagate(self, company_name, trade_date):
        """Run the trading agents graph for a company on a specific date.

        When ``checkpoint_enabled`` is set in config, the graph is recompiled
        with a per-ticker SqliteSaver so a crashed run can resume from the last
        successful node on a subsequent invocation with the same ticker+date.
        """
        return self._run_graph(company_name, trade_date)

    def prepare_graph_run(
        self,
        company_name,
        trade_date,
        callbacks: Optional[List] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any], Optional[int]]:
        """Prepare graph input/args for a fresh or resumed run.

        Returns ``(initial_state, args, checkpoint_step)``. When a checkpoint
        already exists, ``initial_state`` is ``None`` so LangGraph resumes the
        existing thread instead of replaying completed nodes.
        """
        self.ticker = company_name

        # Resolve any pending memory-log entries for this ticker before the pipeline runs.
        self._resolve_pending_entries(company_name)

        checkpoint_enabled = self.config.get("checkpoint_enabled")
        resume_step = None

        # Recompile with a checkpointer if the user opted in.
        if checkpoint_enabled:
            self._checkpointer_ctx = get_checkpointer(
                self.config["data_cache_dir"], company_name
            )
            saver = self._checkpointer_ctx.__enter__()
            self.graph = self.workflow.compile(checkpointer=saver)

            resume_step = checkpoint_step(
                self.config["data_cache_dir"], company_name, str(trade_date)
            )
            if resume_step is not None:
                logger.info(
                    "Resuming from step %d for %s on %s",
                    resume_step,
                    company_name,
                    trade_date,
                )
            else:
                logger.info("Starting fresh for %s on %s", company_name, trade_date)

        args = self.propagator.get_graph_args(callbacks=callbacks)

        # Inject thread_id so same ticker+date resumes, different date starts fresh.
        if checkpoint_enabled:
            tid = thread_id(company_name, str(trade_date))
            args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = tid

        if checkpoint_enabled and resume_step is not None:
            return None, args, resume_step

        # Initialize state only for fresh runs. Passing a new initial state to
        # LangGraph would start a new run and replay completed nodes.
        past_context = self.memory_log.get_past_context(company_name)
        init_agent_state = self.propagator.create_initial_state(
            company_name, trade_date, past_context=past_context
        )
        return init_agent_state, args, resume_step

    def finalize_graph_run(self, company_name, trade_date, final_state):
        """Persist a completed run and clear its checkpoint."""
        self.curr_state = final_state

        # Log state to disk.
        self._log_state(trade_date, final_state)

        # Store decision for deferred reflection on the next same-ticker run.
        self.memory_log.store_decision(
            ticker=company_name,
            trade_date=trade_date,
            final_trade_decision=final_state["final_trade_decision"],
        )

        # Clear checkpoint on successful completion to avoid stale state.
        if self.config.get("checkpoint_enabled"):
            clear_checkpoint(
                self.config["data_cache_dir"], company_name, str(trade_date)
            )

        return self.process_signal(final_state["final_trade_decision"])

    def close_graph_run(self) -> None:
        """Close the active checkpointer context, if any."""
        if self._checkpointer_ctx is not None:
            self._checkpointer_ctx.__exit__(None, None, None)
            self._checkpointer_ctx = None
            self.graph = self.workflow.compile()

    def _run_graph(self, company_name, trade_date):
        """Execute the graph and write the resulting state to disk and memory log."""
        init_agent_state, args, _ = self.prepare_graph_run(company_name, trade_date)

        try:
            if self.debug:
                trace = []
                for chunk in self.graph.stream(init_agent_state, **args):
                    if len(chunk["messages"]) == 0:
                        pass
                    else:
                        chunk["messages"][-1].pretty_print()
                        trace.append(chunk)
                final_state = trace[-1]
            else:
                final_state = self.graph.invoke(init_agent_state, **args)

            signal = self.finalize_graph_run(company_name, trade_date, final_state)
            return final_state, signal
        finally:
            self.close_graph_run()

    def _log_state(self, trade_date, final_state):
        """Log the final state to a JSON file."""
        self.log_states_dict[str(trade_date)] = {
            "company_of_interest": final_state["company_of_interest"],
            "trade_date": final_state["trade_date"],
            "market_report": final_state["market_report"],
            "sentiment_report": final_state["sentiment_report"],
            "news_report": final_state["news_report"],
            "fundamentals_report": final_state["fundamentals_report"],
            "policy_report": final_state.get("policy_report", ""),
            "hot_money_report": final_state.get("hot_money_report", ""),
            "lockup_report": final_state.get("lockup_report", ""),
            "investment_debate_state": {
                "bull_history": final_state["investment_debate_state"]["bull_history"],
                "bear_history": final_state["investment_debate_state"]["bear_history"],
                "history": final_state["investment_debate_state"]["history"],
                "current_response": final_state["investment_debate_state"][
                    "current_response"
                ],
                "judge_decision": final_state["investment_debate_state"][
                    "judge_decision"
                ],
            },
            "trader_investment_decision": final_state["trader_investment_plan"],
            "risk_debate_state": {
                "aggressive_history": final_state["risk_debate_state"]["aggressive_history"],
                "conservative_history": final_state["risk_debate_state"]["conservative_history"],
                "neutral_history": final_state["risk_debate_state"]["neutral_history"],
                "history": final_state["risk_debate_state"]["history"],
                "judge_decision": final_state["risk_debate_state"]["judge_decision"],
            },
            "investment_plan": final_state["investment_plan"],
            "final_trade_decision": final_state["final_trade_decision"],
        }

        # Save to file. Reject ticker values that would escape the
        # results directory when joined as a path component.
        safe_ticker = safe_ticker_component(self.ticker)
        directory = Path(self.config["results_dir"]) / safe_ticker / "TradingAgentsStrategy_logs"
        directory.mkdir(parents=True, exist_ok=True)

        log_path = directory / f"full_states_log_{trade_date}.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(self.log_states_dict[str(trade_date)], f, indent=4)

    def process_signal(self, full_signal):
        """Process a signal to extract the core decision."""
        return self.signal_processor.process_signal(full_signal)
