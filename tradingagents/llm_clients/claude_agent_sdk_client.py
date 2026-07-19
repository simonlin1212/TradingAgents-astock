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

Scope (POC): serves the ``deep_thinking_llm`` nodes (Research Manager /
Portfolio Manager) which call ``.invoke(str)`` and ``.with_structured_output``
directly and never ``bind_tools``. Tool-using analysts must use another
provider — ``bind_tools`` raises here on purpose.
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

from .base_client import BaseLLMClient

logger = logging.getLogger(__name__)

OAUTH_ENV = "CLAUDE_CODE_OAUTH_TOKEN"

try:  # optional dependency — see module docstring
    import claude_agent_sdk as _sdk
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKError
    _IMPORT_ERROR: Optional[Exception] = None
except Exception as exc:  # ImportError or any transitive import failure
    _sdk = None
    ClaudeAgentOptions = None
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

    def bind_tools(self, *args, **kwargs):
        raise NotImplementedError(
            "claude_agent_sdk provider does not support bind_tools. This POC "
            "serves only the structured/plain deep-thinking nodes; route "
            "tool-using analysts through another provider (e.g. deepseek)."
        )


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
            raise RuntimeError(
                f"{OAUTH_ENV} is not set. Log in to your Claude Pro/Max account and "
                "run `claude setup-token`, then export the token before selecting the "
                "claude_agent_sdk provider."
            )
        return AgentSDKChatModel(self, self.fallback_spec)

    def validate_model(self) -> bool:
        # Any Claude model id is accepted; validity is enforced by the SDK/CLI.
        return True

    # -- internal call path -------------------------------------------------- #

    def _build_options(self, system_prompt: Optional[str],
                       output_format: Optional[dict] = None):
        opts: dict[str, Any] = {
            "model": self.model,
            "max_turns": 1,           # approximate a single completion
            "allowed_tools": [],      # no built-in tools (Read/Write/Bash/…)
            "setting_sources": [],    # don't load filesystem settings/skills/CLAUDE.md
            "permission_mode": "bypassPermissions",
            "env": {OAUTH_ENV: os.environ.get(OAUTH_ENV, "")},
        }
        if system_prompt:
            opts["system_prompt"] = system_prompt
        if output_format is not None:
            opts["output_format"] = output_format
        return ClaudeAgentOptions(**opts)

    async def _query(self, prompt: str, options):
        text_parts: list[str] = []
        result_msg = None
        async for message in _sdk.query(prompt=prompt, options=options):
            if isinstance(message, _sdk.RateLimitEvent):
                # RateLimitEvent fires on ANY status change, including
                # "allowed_warning" (near the limit but STILL SERVING) and
                # "allowed" (recovered). Only "rejected" means the call was
                # actually blocked. Raising on a warning would discard a
                # successful subscription response and silently fall back to
                # the paid API — the opposite of this feature's purpose.
                info = getattr(message, "rate_limit_info", None)
                if getattr(info, "status", None) == "rejected" or \
                        getattr(info, "overage_status", None) == "rejected":
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
        if result_msg is not None:
            if getattr(result_msg, "is_error", False):
                raise _SDKResultError(
                    f"stop_reason={getattr(result_msg, 'stop_reason', None)} "
                    f"api_error_status={getattr(result_msg, 'api_error_status', None)}"
                )
            structured = getattr(result_msg, "structured_output", None)
            if not text_parts and getattr(result_msg, "result", None):
                text_parts.append(result_msg.result)
        return "".join(text_parts), structured

    def _invoke_raw(self, prompt: Any) -> AIMessage:
        system_prompt, user_text = _split_prompt(prompt)
        options = self._build_options(system_prompt)
        text, _ = _run_async(self._query(user_text, options))
        return AIMessage(content=text)

    def _invoke_structured(self, schema, prompt: Any):
        system_prompt, user_text = _split_prompt(prompt)
        output_format = {"type": "json_schema", "schema": schema.model_json_schema()}
        options = self._build_options(system_prompt, output_format=output_format)
        text, structured = _run_async(self._query(user_text, options))
        data = structured if structured is not None else json.loads(_extract_json(text))
        return schema.model_validate(data)
