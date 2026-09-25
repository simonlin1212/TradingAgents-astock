"""Requesty provider: client wiring and CLI model listing."""

from unittest.mock import MagicMock, patch

import pytest

from cli.utils import _fetch_requesty_models
from tradingagents.llm_clients.factory import create_llm_client


@pytest.mark.unit
def test_requesty_uses_its_own_endpoint_and_key(monkeypatch):
    monkeypatch.setenv("REQUESTY_API_KEY", "rqsty-test")
    llm = create_llm_client("requesty", "openai/gpt-4o-mini").get_llm()
    assert str(llm.openai_api_base) == "https://router.requesty.ai/v1"
    assert llm.openai_api_key.get_secret_value() == "rqsty-test"


@pytest.mark.unit
def test_requesty_missing_key_names_env_var(monkeypatch):
    monkeypatch.delenv("REQUESTY_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="REQUESTY_API_KEY"):
        create_llm_client("requesty", "openai/gpt-4o-mini").get_llm()


def _response(data):
    resp = MagicMock()
    resp.json.return_value = {"object": "list", "data": data}
    resp.raise_for_status.return_value = None
    return resp


@pytest.mark.unit
def test_fetch_requesty_models_uses_managed_list_newest_first():
    data = [
        {"id": "gpt-5.4-mini", "api": "chat", "created": 1},
        {"id": "text-embedding-3-small", "api": "embedding", "created": 3},
        {"id": "claude-sonnet-4-5", "api": "chat", "created": 2},
    ]
    with patch("requests.get", return_value=_response(data)) as get:
        models = _fetch_requesty_models()
    assert get.call_args_list[0].args[0] == "https://router.requesty.ai/v1/models/managed"
    assert models == [
        ("claude-sonnet-4-5", "claude-sonnet-4-5"),
        ("gpt-5.4-mini", "gpt-5.4-mini"),
    ]


@pytest.mark.unit
def test_fetch_requesty_models_falls_back_to_full_catalog():
    full = _response([{"id": "openai/gpt-4o-mini", "api": "chat", "created": 1}])
    with patch("requests.get", side_effect=[Exception("boom"), full]) as get:
        models = _fetch_requesty_models()
    assert get.call_args_list[1].args[0] == "https://router.requesty.ai/v1/models"
    assert models == [("openai/gpt-4o-mini", "openai/gpt-4o-mini")]
