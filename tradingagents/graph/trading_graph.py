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
from tradingagents.dataflows.missing_data import (
    attach_missing_data_snapshot,
    mark_resolved_tasks_consumed,
    make_tool_call_recorder,
    reset_missing_tasks_for_run,
)

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
from .setup import GraphSetup
from .propagation import Propagator
from .reflection import Reflector
from .signal_processing import SignalProcessor


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

        deep_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["deep_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )
        quick_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["quick_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )

        self.deep_thinking_llm = deep_client.get_llm()
        self.quick_thinking_llm = quick_client.get_llm()
        
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

    def _get_provider_kwargs(self) -> Dict[str, Any]:
        """Get provider-specific kwargs for LLM client creation."""
        kwargs = {}
        provider = self.config.get("llm_provider", "").lower()

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
                    get_northbound_flow,
                ],
                wrap_tool_call=make_tool_call_recorder("market"),
            ),
            "social": ToolNode(
                [
                    # News tools for social media analysis
                    get_news,
                ],
                wrap_tool_call=make_tool_call_recorder("social"),
            ),
            "news": ToolNode(
                [
                    # News and insider information
                    get_news,
                    get_global_news,
                    get_insider_transactions,
                ],
                wrap_tool_call=make_tool_call_recorder("news"),
            ),
            "fundamentals": ToolNode(
                [
                    get_fundamentals,
                    get_balance_sheet,
                    get_cashflow,
                    get_income_statement,
                    get_profit_forecast,
                    get_industry_comparison,
                ],
                wrap_tool_call=make_tool_call_recorder("fundamentals"),
            ),
            "policy": ToolNode(
                [
                    get_news,
                    get_global_news,
                ],
                wrap_tool_call=make_tool_call_recorder("policy"),
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
                ],
                wrap_tool_call=make_tool_call_recorder("hot_money"),
            ),
            "lockup": ToolNode(
                [
                    get_insider_transactions,
                    get_news,
                    get_fundamentals,
                    get_lockup_expiry,
                ],
                wrap_tool_call=make_tool_call_recorder("lockup"),
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

            stock = yf.Ticker(ticker).history(start=trade_date, end=end_str)
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
        reset_missing_tasks_for_run(company_name, str(trade_date))
        past_context = self.memory_log.get_past_context(company_name)
        init_agent_state = self.propagator.create_initial_state(
            company_name, trade_date, past_context=past_context
        )
        return init_agent_state, args, resume_step

    def finalize_graph_run(self, company_name, trade_date, final_state):
        """Persist a completed run and clear its checkpoint."""
        attach_missing_data_snapshot(final_state, company_name, str(trade_date))
        self.curr_state = final_state

        # Log state to disk.
        self._log_state(trade_date, final_state)
        mark_resolved_tasks_consumed(company_name, str(trade_date))

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
            "data_quality_summary": final_state.get("data_quality_summary", ""),
            "missing_data_tasks": final_state.get("missing_data_tasks", []),
            "missing_data_complete": final_state.get("missing_data_complete", True),
            "missing_data_resolved_count": final_state.get("missing_data_resolved_count", 0),
            "missing_data_requires_reanalysis": final_state.get("missing_data_requires_reanalysis", False),
            "missing_data_updated_at": final_state.get("missing_data_updated_at"),
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
