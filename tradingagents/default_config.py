import os

_TRADINGAGENTS_HOME = os.path.join(os.path.expanduser("~"), ".tradingagents")

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", os.path.join(_TRADINGAGENTS_HOME, "logs")),
    "data_cache_dir": os.getenv("TRADINGAGENTS_CACHE_DIR", os.path.join(_TRADINGAGENTS_HOME, "cache")),
    "memory_log_path": os.getenv("TRADINGAGENTS_MEMORY_LOG_PATH", os.path.join(_TRADINGAGENTS_HOME, "memory", "trading_memory.md")),
    # Optional cap on the number of resolved memory log entries. When set,
    # the oldest resolved entries are pruned once this limit is exceeded.
    # Pending entries are never pruned. None disables rotation entirely.
    "memory_log_max_entries": None,
    # LLM settings
    "llm_provider": "deepseek",
    "deep_think_llm": "deepseek-v4-pro",
    "quick_think_llm": "deepseek-chat",
    # When None, each provider's client falls back to its own default endpoint
    # (api.openai.com for OpenAI, generativelanguage.googleapis.com for Gemini, ...).
    # The CLI overrides this per provider when the user picks one. Keeping a
    # provider-specific URL here would leak (e.g. OpenAI's /v1 was previously
    # being forwarded to Gemini, producing malformed request URLs).
    "backend_url": None,
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    "anthropic_effort": None,           # "high", "medium", "low"
    # Claude Agent SDK provider (personal Pro/Max subscription; optional [agentsdk] extra).
    # When set to "claude_agent_sdk", ONLY the deep_thinking_llm nodes (Research
    # Manager / Portfolio Manager) route through the subscription. None = unchanged.
    "deep_think_provider_override": None,
    # Same, but for the QUICK nodes (7 tool-using analysts + Bull/Bear / trader /
    # risk debaters). Set to "claude_agent_sdk" to run those on the subscription
    # too; combined with deep_think_provider_override this puts ALL nodes on the
    # personal subscription. None = analysts stay on llm_provider (unchanged).
    "quick_think_provider_override": None,
    # The Claude model id the Agent SDK uses. MUST be a real Claude model — do
    # NOT reuse deep_think_llm (default "deepseek-v4-pro" is a DeepSeek model id).
    "agent_sdk_model": "claude-opus-4-8",
    # Claude model for the QUICK/analyst nodes when quick_think_provider_override
    # is on. Subscription bills quota not tokens, so Opus is fine; pick a faster
    # Claude here if you prefer snappier analyst turns.
    "agent_sdk_quick_model": "claude-opus-4-8",
    # Fallback when the subscription call fails / hits quota. None → fall back to
    # llm_provider + deep_think_llm (a real, separately-billed provider).
    "agent_sdk_fallback_provider": None,
    "agent_sdk_fallback_model": None,
    # Checkpoint/resume: when True, LangGraph saves state after each node
    # so a crashed run can resume from the last successful step.
    "checkpoint_enabled": False,
    # Output language for analyst reports and final decision
    # Internal agent debate stays in English for reasoning quality
    "output_language": "Chinese",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "a_stock",        # Options: a_stock, alpha_vantage, yfinance
        "technical_indicators": "a_stock",   # Options: a_stock, alpha_vantage, yfinance
        "fundamental_data": "a_stock",       # Options: a_stock, alpha_vantage, yfinance
        "news_data": "a_stock",              # Options: a_stock, alpha_vantage, yfinance
        "signal_data": "a_stock",            # A-stock only: topic attribution, capital flow, consensus
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },
}
