"""Claude Agent SDK provider — route deep-thinking nodes through a personal
Claude Pro/Max subscription instead of the pay-per-token Anthropic API.

Personal use only. The Claude Agent SDK / ``claude -p`` consume the logged-in
user's subscription quota (obtained via ``claude setup-token`` →
``CLAUDE_CODE_OAUTH_TOKEN``). Publishing this as a product that routes *other*
users' subscription credentials requires Anthropic approval — out of scope.

``claude-agent-sdk`` requires ``httpx>=0.28.1``, which conflicts with mootdx's
``httpx==0.25.2`` pin, so it is an *optional* dependency (the ``[agentsdk]``
extra). The import below is guarded so the base install never breaks; the
error surfaces only when this provider is actually selected.

Scope: originally the ``deep_thinking_llm`` nodes (Research Manager / Portfolio
Manager) which call ``.invoke(str)`` / ``.with_structured_output`` directly.
``bind_tools`` is now also supported for the tool-using analysts: their
LangChain tools are bridged to Agent SDK in-process MCP tools and the SDK runs
the ReAct loop internally, returning a final report (no tool_calls) so
LangGraph treats the analyst as done. On failure/quota the fallback provider's
``bind_tools`` rejoins LangGraph's normal external ToolNode loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
from typing import Any, Optional

from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable

from .base_client import BaseLLMClient

logger = logging.getLogger(__name__)

OAUTH_ENV = "CLAUDE_CODE_OAUTH_TOKEN"

# Tool-loop knobs. When the deep-thinking nodes call plain .invoke there are no
# tools and a single turn suffices; the tool-using analysts need the Agent SDK
# to run a multi-turn agentic loop internally (call tool → read result → …).
_MCP_SERVER_NAME = "astock_tools"
_TOOL_MAX_TURNS = 30           # generous: an analyst may pull ~8 indicators + data
_TOOL_RESULT_CAP = 60_000      # per-tool result char cap (safety, not normally hit)

try:  # optional dependency — see module docstring
    import claude_agent_sdk as _sdk
    from claude_agent_sdk import (
        ClaudeAgentOptions,
        ClaudeSDKError,
        create_sdk_mcp_server,
        tool as _sdk_tool,
    )
    _IMPORT_ERROR: Optional[Exception] = None
except Exception as exc:  # ImportError or any transitive import failure
    _sdk = None
    ClaudeAgentOptions = None
    create_sdk_mcp_server = None
    _sdk_tool = None
    ClaudeSDKError = Exception  # placeholder so `except` clauses never NameError
    _IMPORT_ERROR = exc


class _RateLimitHit(Exception):
    """Raised when the subscription hit a rate/quota limit — triggers fallback."""


class _SDKResultError(Exception):
    """Raised when the Agent SDK returns an error ResultMessage — triggers fallback."""


# Errors that mean "the subscription path could not serve this call" → fall back.
_FALLBACK_ERRORS = (ClaudeSDKError, _RateLimitHit, _SDKResultError)


# --------------------------------------------------------------------------- #
# prompt/message helpers
# --------------------------------------------------------------------------- #

def _msg_role_content(message: Any):
    """Extract (role, content) from a LangChain BaseMessage or a plain dict."""
    if isinstance(message, dict):
        return message.get("role"), str(message.get("content", ""))
    role = getattr(message, "type", None)  # BaseMessage.type: 'system'/'human'/'ai'
    content = getattr(message, "content", "")
    return role, content if isinstance(content, str) else str(content)


def _split_prompt(prompt: Any):
    """Return (system_prompt_or_None, user_text) from whatever the agents pass.

    The deep-thinking agents pass a plain string, but accept PromptValue and
    message lists defensively so this never crashes on an unexpected shape.
    """
    if isinstance(prompt, str):
        return None, prompt

    to_messages = getattr(prompt, "to_messages", None)
    if callable(to_messages):
        messages = to_messages()
    elif isinstance(prompt, (list, tuple)):
        messages = list(prompt)
    else:
        return None, str(prompt)

    system_parts, other_parts = [], []
    for m in messages:
        role, content = _msg_role_content(m)
        if role == "system":
            system_parts.append(content)
        elif role in (None, "human", "user", "ai", "assistant"):
            other_parts.append(content)
        else:
            other_parts.append(f"[{role}] {content}")
    system = "\n".join(p for p in system_parts if p) or None
    return system, "\n".join(p for p in other_parts if p)


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> str:
    """Best-effort: pull the first {...} block out of a text response."""
    match = _JSON_RE.search(text or "")
    if not match:
        raise ValueError("no JSON object found in Agent SDK text response")
    return match.group(0)


def _run_async(coro):
    """Run an async coroutine to completion from a synchronous caller.

    ``trading_graph`` drives LangGraph synchronously, so normally there is no
    running loop and ``asyncio.run`` works. If a loop is already running, run
    the coroutine on a dedicated thread with its own loop so we never disturb
    the caller's loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    box: dict[str, Any] = {}

    def _worker():
        try:
            box["value"] = asyncio.run(coro)
        except BaseException as exc:  # propagate to the calling thread, don't swallow
            box["error"] = exc

    thread = threading.Thread(target=_worker)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box["value"]


def _sdk_tools_from_langchain(lc_tools):
    """Wrap LangChain tools as Agent SDK in-process MCP tools.

    The analysts drive tools via LangGraph's external ReAct loop (return
    tool_calls → ToolNode executes → repeat). The Agent SDK instead runs the
    whole loop *internally*, so we register each LangChain tool as an SDK tool
    whose async handler invokes the original tool on a worker thread (the data
    layer is synchronous and hits the network — never block the SDK's loop).
    """
    sdk_tools = []
    for lc in lc_tools:
        schema = (
            lc.args_schema.model_json_schema()
            if getattr(lc, "args_schema", None) is not None
            else {"type": "object", "properties": {}}
        )

        @_sdk_tool(lc.name, (lc.description or lc.name)[:1000], schema)
        async def _handler(args, _lc=lc):  # _lc default-arg pins the loop var
            try:
                result = await asyncio.to_thread(_lc.invoke, dict(args))
            except Exception as exc:  # tool failure is data for the model, not a crash
                result = f"[tool error] {exc}"
            return {"content": [{"type": "text", "text": str(result)[:_TOOL_RESULT_CAP]}]}

        sdk_tools.append(_handler)
    return sdk_tools


# --------------------------------------------------------------------------- #
# adapters returned to the agents
# --------------------------------------------------------------------------- #

class _StructuredAgentSDK:
    """What ``with_structured_output(schema)`` returns — exposes ``.invoke``."""

    def __init__(self, adapter: "AgentSDKChatModel", schema):
        self._adapter = adapter
        self._schema = schema

    def invoke(self, prompt: Any, *args, **kwargs):
        try:
            return self._adapter._client._invoke_structured(self._schema, prompt)
        except _FALLBACK_ERRORS as exc:
            fallback = self._adapter._get_fallback()
            if fallback is None:
                raise
            logger.warning(
                "claude_agent_sdk: structured call failed (%s); "
                "falling back to provider '%s'",
                exc, self._adapter._fallback_desc(),
            )
            return fallback.with_structured_output(self._schema).invoke(prompt, *args, **kwargs)


class _BoundAgentSDK(Runnable):
    """What ``bind_tools(tools)`` returns — a Runnable so ``prompt | bound`` works.

    ``.invoke`` runs the Agent SDK's internal tool loop on the subscription and
    returns the final report as an ``AIMessage`` with no ``tool_calls``. On a
    subscription failure/quota it defers to the fallback provider, whose
    ``bind_tools`` returns real ``tool_calls`` and so rejoins LangGraph's normal
    external ToolNode loop — no graph change needed either way.
    """

    def __init__(self, adapter: "AgentSDKChatModel", tools):
        self._adapter = adapter
        self._tools = tools

    def invoke(self, input, config=None, **kwargs):
        try:
            return self._adapter._client._invoke_with_tools(self._tools, input)
        except _FALLBACK_ERRORS as exc:
            fallback = self._adapter._get_fallback()
            if fallback is None:
                raise
            logger.warning(
                "claude_agent_sdk: tool invoke failed (%s); "
                "falling back to provider '%s'",
                exc, self._adapter._fallback_desc(),
            )
            return fallback.bind_tools(self._tools).invoke(input, config, **kwargs)


class AgentSDKChatModel:
    """Duck-typed LangChain-compatible chat model backed by the Claude Agent SDK.

    Only the surface the deep-thinking agents use is implemented: ``invoke``,
    ``with_structured_output`` and ``bind_tools`` (the last raises on purpose).
    Cross-provider fallback (F-005) is self-contained here so callers never see
    a subscription quota error.
    """

    def __init__(self, client: "ClaudeAgentSDKClient", fallback_spec: Optional[dict]):
        self._client = client
        self._fallback_spec = fallback_spec or None
        self._fallback_llm = None  # built lazily on first failure

    def _fallback_desc(self) -> str:
        return (self._fallback_spec or {}).get("provider", "none")

    def _get_fallback(self):
        if self._fallback_spec is None:
            return None
        if self._fallback_llm is None:
            from .factory import create_llm_client
            self._fallback_llm = create_llm_client(**self._fallback_spec).get_llm()
        return self._fallback_llm

    def invoke(self, prompt: Any, *args, **kwargs):
        try:
            return self._client._invoke_raw(prompt)
        except _FALLBACK_ERRORS as exc:
            fallback = self._get_fallback()
            if fallback is None:
                raise
            logger.warning(
                "claude_agent_sdk: invoke failed (%s); falling back to provider '%s'",
                exc, self._fallback_desc(),
            )
            return fallback.invoke(prompt, *args, **kwargs)

    def with_structured_output(self, schema, **kwargs):
        return _StructuredAgentSDK(self, schema)

    def bind_tools(self, tools, **kwargs):
        # The tool-using analysts compose `prompt | llm.bind_tools(tools)`, so
        # this must return a Runnable. The Agent SDK runs the tool loop
        # internally and returns a final report (no tool_calls) — LangGraph
        # then treats the analyst as done. On failure/quota, the fallback
        # provider's bind_tools rejoins the normal external ToolNode loop.
        return _BoundAgentSDK(self, list(tools))


# --------------------------------------------------------------------------- #
# client
# --------------------------------------------------------------------------- #

class ClaudeAgentSDKClient(BaseLLMClient):
    """LLM client that calls Claude via the Agent SDK on a personal subscription.

    ``fallback_spec`` (``{"provider", "model", "base_url"}``) is injected at
    construction so the adapter can rebuild a fallback LLM internally without
    reaching back into ``trading_graph``.
    """

    def __init__(self, model: str, base_url: Optional[str] = None,
                 fallback_spec: Optional[dict] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)
        self.fallback_spec = fallback_spec

    def get_llm(self) -> AgentSDKChatModel:
        if _sdk is None:
            raise ImportError(
                "claude-agent-sdk is not installed. Install the optional extra:\n"
                '    pip install -e ".[agentsdk]"\n'
                f"(original import error: {_IMPORT_ERROR})"
            )
        if not os.getenv(OAUTH_ENV):
            # No explicit subscription token — the Agent SDK spawns the `claude`
            # CLI, which inherits the ambient logged-in session (macOS Keychain /
            # ~/.claude credentials). That is the SAME personal subscription path;
            # `claude setup-token` merely pins an explicit, portable token needed
            # on headless/CI boxes with no logged-in CLI. Proceed and let the SDK
            # surface an auth error at call time (F-005 fallback catches it)
            # rather than block a machine that is already logged in.
            logger.info(
                "%s not set — using the ambient logged-in `claude` session "
                "(personal subscription). Run `claude setup-token` to pin an "
                "explicit token for headless use.",
                OAUTH_ENV,
            )
        return AgentSDKChatModel(self, self.fallback_spec)

    def validate_model(self) -> bool:
        # Any Claude model id is accepted; validity is enforced by the SDK/CLI.
        return True

    # -- internal call path -------------------------------------------------- #

    def _build_options(self, system_prompt: Optional[str],
                       output_format: Optional[dict] = None,
                       sdk_tools: Optional[list] = None,
                       tool_names: Optional[list] = None):
        opts: dict[str, Any] = {
            "model": self.model,
            "max_turns": 1,           # approximate a single completion
            "allowed_tools": [],      # no built-in tools (Read/Write/Bash/…)
            "setting_sources": [],    # don't load filesystem settings/skills/CLAUDE.md
            "permission_mode": "bypassPermissions",
        }
        token = os.environ.get(OAUTH_ENV)
        if token:
            # Pin the explicit subscription token when provided; otherwise let the
            # SDK fall back to the ambient logged-in CLI session (Keychain) —
            # passing an empty token here is unnecessary and only muddies intent.
            opts["env"] = {OAUTH_ENV: token}
        if sdk_tools:
            # Register the bridged analyst tools and let the SDK run the loop
            # internally over multiple turns (only these tools are allowed).
            server = create_sdk_mcp_server(_MCP_SERVER_NAME, "1.0.0", tools=sdk_tools)
            opts["mcp_servers"] = {_MCP_SERVER_NAME: server}
            opts["allowed_tools"] = [
                f"mcp__{_MCP_SERVER_NAME}__{n}" for n in (tool_names or [])
            ]
            opts["max_turns"] = _TOOL_MAX_TURNS
        if system_prompt:
            opts["system_prompt"] = system_prompt
        if output_format is not None:
            opts["output_format"] = output_format
        return ClaudeAgentOptions(**opts)

    async def _query(self, prompt: str, options, prefer_result: bool = False):
        text_parts: list[str] = []
        result_msg = None
        async for message in _sdk.query(prompt=prompt, options=options):
            if isinstance(message, _sdk.RateLimitEvent):
                # RateLimitEvent fires on ANY status change, including
                # "allowed_warning" (near the limit but STILL SERVING) and
                # "allowed" (recovered). Only status=="rejected" means THIS call
                # was actually blocked. Raising on anything else discards a
                # successful subscription response and silently falls back to
                # the paid provider — the opposite of this feature's purpose.
                #
                # In particular, DO NOT key off overage_status: it is a separate
                # axis describing whether *overage* (paid usage beyond the plan)
                # is available. When an org disables overage it reports
                # overage_status="rejected"/"org_level_disabled" on EVERY event,
                # including status=="allowed" ones the plan served within
                # allowance — so keying fallback off it downgraded 100% of
                # subscription calls to the paid fallback. (regression:
                # test_query_allowed_with_overage_rejected_does_not_fall_back)
                info = getattr(message, "rate_limit_info", None)
                if getattr(info, "status", None) == "rejected":
                    raise _RateLimitHit(str(info))
                logger.warning(
                    "claude_agent_sdk: rate-limit status=%s (still serving); continuing",
                    getattr(info, "status", None),
                )
                continue
            if isinstance(message, _sdk.AssistantMessage):
                for block in message.content:
                    if isinstance(block, _sdk.TextBlock):
                        text_parts.append(block.text)
            elif isinstance(message, _sdk.ResultMessage):
                result_msg = message

        structured = None
        text = "".join(text_parts)
        if result_msg is not None:
            if getattr(result_msg, "is_error", False):
                raise _SDKResultError(
                    f"stop_reason={getattr(result_msg, 'stop_reason', None)} "
                    f"api_error_status={getattr(result_msg, 'api_error_status', None)}"
                )
            structured = getattr(result_msg, "structured_output", None)
            final = getattr(result_msg, "result", None)
            # In a tool loop the intermediate turns emit reasoning text before
            # each tool call; ResultMessage.result holds the authoritative final
            # answer, so prefer it there. For single-turn calls fall back to it
            # only when no assistant text was streamed.
            if final and (prefer_result or not text):
                text = final
        return text, structured

    def _invoke_raw(self, prompt: Any) -> AIMessage:
        system_prompt, user_text = _split_prompt(prompt)
        options = self._build_options(system_prompt)
        text, _ = _run_async(self._query(user_text, options))
        return AIMessage(content=text)

    def _invoke_with_tools(self, lc_tools, prompt: Any) -> AIMessage:
        """Run the SDK's internal tool loop over the bridged analyst tools and
        return the final report as an AIMessage (no tool_calls)."""
        system_prompt, user_text = _split_prompt(prompt)
        sdk_tools = _sdk_tools_from_langchain(lc_tools)
        tool_names = [t.name for t in lc_tools]
        options = self._build_options(
            system_prompt, sdk_tools=sdk_tools, tool_names=tool_names
        )
        text, _ = _run_async(self._query(user_text, options, prefer_result=True))
        return AIMessage(content=text)

    def _invoke_structured(self, schema, prompt: Any):
        system_prompt, user_text = _split_prompt(prompt)
        output_format = {"type": "json_schema", "schema": schema.model_json_schema()}
        options = self._build_options(system_prompt, output_format=output_format)
        text, structured = _run_async(self._query(user_text, options))
        data = structured if structured is not None else json.loads(_extract_json(text))
        return schema.model_validate(data)
