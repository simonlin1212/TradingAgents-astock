"""Isolated contract tests for the optional Codex CLI adapter."""

from __future__ import annotations

import json
import os
import signal
import sys
import time

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from tradingagents.agents.schemas import PortfolioDecision
from tradingagents.llm_clients import codex_cli_client as codex
from tradingagents.llm_clients.factory import create_llm_client


class _Args(BaseModel):
    ticker: str = Field(pattern=r"^\d{6}$")


def _get_stock_data(ticker: str) -> str:
    return f"synthetic {ticker}"


def _tool():
    return StructuredTool.from_function(
        _get_stock_data,
        name="get_stock_data",
        description="Read synthetic stock data.",
        args_schema=_Args,
    )


@pytest.mark.unit
def test_factory_routes_codex_cli_lazily(monkeypatch):
    client = create_llm_client("codex_cli", "", auth_mode="chatgpt")
    assert isinstance(client, codex.CodexCLIClient)
    assert client.validate_model()


@pytest.mark.unit
def test_jsonl_final_message_extraction_and_empty_output():
    payload = '\n'.join([
        json.dumps({"type": "thread.started"}),
        json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "OK"}}),
    ])
    assert codex._extract_final(payload) == "OK"
    with pytest.raises(codex.CodexCLIError, match="no final message"):
        codex._extract_final('{"type":"turn.completed"}')

    failed_turn = "\n".join([
        json.dumps({"type": "item.completed", "item": {"type": "error", "message": "non-fatal warning"}}),
        json.dumps({"type": "turn.failed", "error": {"message": "actual request failure"}}),
    ])
    with pytest.raises(codex.CodexCLIError, match="actual request failure"):
        codex._extract_final(failed_turn)


@pytest.mark.unit
def test_jsonl_usage_is_exposed_and_builtin_tool_events_are_rejected():
    payload = "\n".join([
        json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "OK"}}),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 17, "output_tokens": 5}}),
    ])
    assert codex._extract_response(payload) == (
        "OK", {"input_tokens": 17, "output_tokens": 5, "total_tokens": 22}
    )
    command = json.dumps({
        "type": "item.started",
        "item": {"type": "command_execution", "command": "cat ~/.ssh/id_rsa"},
    })
    with pytest.raises(codex.CodexCLIError, match="built-in tool"):
        codex._extract_response(command)


@pytest.mark.unit
def test_pydantic_schema_is_made_strict_and_local_refs_are_inlined():
    schema = codex._schema_for(PortfolioDecision)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert "time_horizon" in schema["required"]
    assert "$defs" not in schema

    def assert_closed_objects(value):
        if isinstance(value, dict):
            if value.get("type") == "object" or "properties" in value:
                assert value.get("additionalProperties") is False
                assert set(value.get("required", [])) == set(value.get("properties", {}))
            assert "$ref" not in value
            for child in value.values():
                assert_closed_objects(child)
        elif isinstance(value, list):
            for child in value:
                assert_closed_objects(child)

    assert_closed_objects(schema)


@pytest.mark.unit
def test_chatgpt_mode_clears_api_credentials_and_rejects_wrong_login(monkeypatch):
    client = codex.CodexCLIClient("", auth_mode="chatgpt")
    monkeypatch.setenv("OPENAI_API_KEY", "sensitive-test-key")
    monkeypatch.setenv("CODEX_API_KEY", "also-sensitive")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "other-provider-secret")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "market-adjacent-secret")
    env = client._environment()
    assert "OPENAI_API_KEY" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert "DEEPSEEK_API_KEY" not in env
    assert set(env).issubset({
        "PATH", "HOME", "USERPROFILE", "CODEX_HOME", "TMPDIR", "TMP", "TEMP",
        "LANG", "LC_ALL", "LC_CTYPE", "SSL_CERT_FILE", "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE", "NODE_EXTRA_CA_CERTS", "SYSTEMROOT", "WINDIR",
        "APPDATA", "LOCALAPPDATA",
    })

    def fake_run(args, **kwargs):
        if args[1:3] == ["features", "list"]:
            output = "\n".join(f"{name} stable false" for name in codex._REQUIRED_DISABLED_FEATURES)
            return 0, output, ""
        return 0, "Logged in using API key", ""

    monkeypatch.setattr(codex, "_run_process", fake_run)
    with pytest.raises(codex.CodexCLIAuthError, match="API key"):
        client._preflight()


@pytest.mark.unit
def test_api_key_mode_requires_explicit_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    client = codex.CodexCLIClient("", auth_mode="api_key")
    with pytest.raises(codex.CodexCLIAuthError, match="API billing"):
        client._environment()


@pytest.mark.unit
def test_api_key_mode_passes_only_explicit_openai_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "api-billing-key")
    monkeypatch.setenv("OPENAI_ORG_ID", "not-passed")
    monkeypatch.setenv("GOOGLE_API_KEY", "not-passed-either")
    env = codex.CodexCLIClient("", auth_mode="api_key")._environment()
    assert env["CODEX_API_KEY"] == "api-billing-key"
    assert "OPENAI_API_KEY" not in env
    assert "OPENAI_ORG_ID" not in env
    assert "GOOGLE_API_KEY" not in env


@pytest.mark.unit
def test_codex_api_key_takes_precedence_over_openai_alias(monkeypatch):
    monkeypatch.setenv("CODEX_API_KEY", "codex-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-alias")
    env = codex.CodexCLIClient("", auth_mode="api_key")._environment()
    assert env["CODEX_API_KEY"] == "codex-key"


@pytest.mark.unit
def test_process_timeout_covers_blocked_stdin_write(tmp_path):
    start = time.monotonic()
    with pytest.raises(codex.CodexCLIError, match="exceeded the configured timeout"):
        codex._run_process(
            [sys.executable, "-c", "import time; time.sleep(1); print('late')"],
            prompt="x" * (4 * 1024 * 1024),
            cwd=str(tmp_path), env=dict(os.environ), timeout=0.1,
        )
    assert time.monotonic() - start < 0.8


@pytest.mark.unit
def test_process_early_exit_reports_return_code_without_broken_pipe(tmp_path):
    code, stdout, stderr = codex._run_process(
        [sys.executable, "-c", "import sys; sys.exit(3)"],
        prompt="x" * (4 * 1024 * 1024),
        cwd=str(tmp_path), env=dict(os.environ), timeout=2,
    )
    assert code == 3
    assert stdout == stderr == ""


@pytest.mark.unit
def test_process_rejects_truncated_stdout_after_an_earlier_final(tmp_path):
    script = (
        "import json,sys; "
        "print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'old'}})); "
        "sys.stdout.write('x' * 1100000)"
    )
    with pytest.raises(codex.CodexCLIError, match="stdout exceeded the output limit"):
        codex._run_process(
            [sys.executable, "-c", script], prompt="", cwd=str(tmp_path),
            env=dict(os.environ), timeout=3,
        )


@pytest.mark.unit
def test_chatgpt_login_is_checked_again_before_later_requests(monkeypatch):
    client = codex.CodexCLIClient("", auth_mode="chatgpt")
    checks = []

    def fake_run(args, **kwargs):
        checks.append(args[1:3])
        if args[1:3] == ["features", "list"]:
            return 0, "\n".join(f"{name} stable false" for name in codex._REQUIRED_DISABLED_FEATURES), ""
        status = "Logged in using ChatGPT" if checks.count(["login", "status"]) == 1 else "Logged in using API key"
        return 0, status, ""

    monkeypatch.setattr(codex, "_run_process", fake_run)
    client._preflight()
    with pytest.raises(codex.CodexCLIAuthError, match="API key"):
        client._preflight()
    assert checks.count(["features", "list"]) == 1
    assert checks.count(["login", "status"]) == 2


@pytest.mark.unit
@pytest.mark.skipif(os.name != "posix", reason="Process-group cleanup uses POSIX signals")
def test_preflight_timeout_stops_child_process(tmp_path):
    marker = tmp_path / "heartbeat"
    pid_file = tmp_path / "child-pid"
    child_code = (
        "import sys,time; from pathlib import Path; p=Path(sys.argv[1]);\n"
        "while True:\n p.write_text(str(time.time())); time.sleep(0.02)"
    )
    parent_code = (
        "import subprocess,sys,time; from pathlib import Path; "
        "p=Path(sys.argv[1]); pid=Path(sys.argv[2]); "
        f"child=subprocess.Popen([sys.executable,'-c',{child_code!r},str(p)]); "
        "pid.write_text(str(child.pid));\n"
        "while not p.exists(): time.sleep(0.01)\n"
        "time.sleep(30)"
    )
    client = codex.CodexCLIClient("", timeout=0.5)
    try:
        with pytest.raises(codex.CodexCLIError, match="exceeded the configured timeout"):
            client._run_preflight_command(
                [sys.executable, "-c", parent_code, str(marker), str(pid_file)],
                client._environment(),
            )
        before = marker.read_text()
        time.sleep(0.15)
        assert marker.read_text() == before
    finally:
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.unit
def test_invocation_disables_codex_builtin_tools_and_reports_usage(monkeypatch):
    from cli.stats_handler import StatsCallbackHandler

    stats = StatsCallbackHandler()
    client = codex.CodexCLIClient("", auth_mode="chatgpt", callbacks=[stats])
    monkeypatch.setattr(client, "_preflight", lambda: None)
    captured = {}

    def run(args, *, prompt, cwd, env, timeout):
        captured.update(args=args, prompt=prompt, cwd=cwd, env=env)
        return 0, "\n".join([
            json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "OK"}}),
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 12, "output_tokens": 3}}),
        ]), ""

    monkeypatch.setattr(codex, "_run_process", run)
    result = client.get_llm().invoke("synthetic prompt")
    assert result.content == "OK"
    assert result.usage_metadata == {"input_tokens": 12, "output_tokens": 3, "total_tokens": 15}
    assert stats.get_stats() == {"llm_calls": 1, "tool_calls": 0, "tokens_in": 12, "tokens_out": 3}
    assert "--ignore-user-config" in captured["args"]
    assert "--sandbox" in captured["args"] and "read-only" in captured["args"]
    assert "skills.max_context_tokens=1" in captured["args"]
    for feature in codex._REQUIRED_DISABLED_FEATURES:
        assert ["--disable", feature] in [
            captured["args"][index:index + 2]
            for index, value in enumerate(captured["args"][:-1])
            if value == "--disable"
        ]
    assert "OPENAI_API_KEY" not in captured["env"]


@pytest.mark.unit
def test_bound_tools_return_langgraph_calls_and_reject_bad_arguments(monkeypatch):
    llm = codex.CodexCLIChatModel(codex.CodexCLIClient("", auth_mode="chatgpt"))
    bound = llm.bind_tools([_tool()])
    request = json.dumps({
        "kind": "tool_calls", "content": "", "tool_calls": [
            {"name": "get_stock_data", "arguments": {"ticker": "600000"}},
        ],
    })
    monkeypatch.setattr(llm, "_invoke_text", lambda prompt, schema: request)
    result = bound.invoke([HumanMessage(content="lookup")])
    assert isinstance(result, AIMessage)
    assert result.tool_calls[0]["name"] == "get_stock_data"
    assert result.tool_calls[0]["args"] == {"ticker": "600000"}

    monkeypatch.setattr(
        llm, "_invoke_text",
        lambda prompt, schema: json.dumps({
            "kind": "tool_calls", "content": "", "tool_calls": [
                {"name": "get_stock_data", "arguments": {"ticker": "not-a-code"}},
            ],
        }),
    )
    with pytest.raises(codex.CodexCLIError, match="fail validation"):
        bound.invoke([HumanMessage(content="lookup")])


@pytest.mark.unit
def test_serialized_history_keeps_tool_results_for_followup():
    history = [
        HumanMessage(content="lookup"),
        AIMessage(content="", tool_calls=[{
            "name": "get_stock_data", "args": {"ticker": "600000"},
            "id": "call_1", "type": "tool_call",
        }]),
        ToolMessage(content="synthetic quote", tool_call_id="call_1", name="get_stock_data"),
    ]
    result = json.loads(codex._serialize_messages(history))
    assert result[1]["tool_calls"][0]["arguments"] == {"ticker": "600000"}
    assert result[2]["tool_call_id"] == "call_1"
    assert result[2]["content"] == "synthetic quote"

    dict_history = [{"role": "assistant", "content": "", "tool_calls": [{
        "name": "get_stock_data", "arguments": {"ticker": "600000"},
    }]}]
    assert json.loads(codex._serialize_messages(dict_history))[0]["tool_calls"][0]["arguments"] == {
        "ticker": "600000"
    }
