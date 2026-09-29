"""Phase 1A: an LLM failure must fail the extraction run; mock output only when explicitly configured."""
import json
import logging

import httpx
import pytest

from app.config.settings import settings
from app.pipeline.llm_client import LLMClient, LLMConfigurationError, LLMError, llm_client

ZERO = {"entities": 0, "aliases": 0, "mentions": 0, "facts": 0, "fact_versions": 0, "relationships": 0,
        "relationship_versions": 0, "events": 0, "event_participants": 0, "contradictions": 0}


def test_ollama_failure_raises_and_never_returns_mock_output(monkeypatch):
    monkeypatch.setattr(llm_client, "provider", "ollama")
    monkeypatch.setattr(llm_client, "_call_ollama", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("refused")))
    mock_calls = []
    monkeypatch.setattr(llm_client, "_mock_extraction", lambda *a, **k: mock_calls.append(1) or "{}")

    with pytest.raises(LLMError, match="Ollama request failed"):
        llm_client.generate("Chapter 1 text")
    assert mock_calls == []


def test_openai_failure_does_not_switch_provider(monkeypatch):
    monkeypatch.setattr(llm_client, "provider", "openai")
    monkeypatch.setattr(llm_client, "openai_key", "sk-test")
    monkeypatch.setattr(llm_client, "_call_openai", lambda *a, **k: (_ for _ in ()).throw(httpx.ReadTimeout("slow")))
    ollama_calls, mock_calls = [], []
    monkeypatch.setattr(llm_client, "_call_ollama", lambda *a, **k: ollama_calls.append(1) or "{}")
    monkeypatch.setattr(llm_client, "_mock_extraction", lambda *a, **k: mock_calls.append(1) or "{}")

    with pytest.raises(LLMError, match="OpenAI request failed"):
        llm_client.generate("text")
    assert ollama_calls == [] and mock_calls == []


def test_missing_key_and_unknown_provider_are_configuration_errors(monkeypatch):
    monkeypatch.setattr(llm_client, "provider", "openai")
    monkeypatch.setattr(llm_client, "openai_key", "")
    with pytest.raises(LLMConfigurationError):
        llm_client.generate("text")

    monkeypatch.setattr(llm_client, "provider", "carrier-pigeon")
    with pytest.raises(LLMConfigurationError, match="Unknown LLM_PROVIDER"):
        llm_client.generate("text")


def test_empty_llm_response_is_an_error(monkeypatch):
    monkeypatch.setattr(llm_client, "provider", "ollama")
    monkeypatch.setattr(llm_client, "_call_ollama", lambda *a, **k: "   ")
    with pytest.raises(LLMError, match="empty response"):
        llm_client.generate("text")


def test_mock_provider_works_only_when_explicit_and_is_loud(monkeypatch, caplog):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    with caplog.at_level(logging.WARNING, logger="app.pipeline.llm_client"):
        client = LLMClient()
        out = client.generate("Alice Sterling met Bob Marsh.")
    assert '"entities"' in out
    assert "LLM_PROVIDER=mock" in caplog.text


def test_default_provider_is_not_mock():
    assert settings.LLM_PROVIDER.lower() != "mock"


# ---- end to end through the real extraction task ---------------------------------------------

def test_llm_failure_fails_run_and_job_and_writes_no_world_state(phase1_env, monkeypatch):
    env = phase1_env
    monkeypatch.setattr(llm_client, "provider", "ollama")
    monkeypatch.setattr(llm_client, "_call_ollama", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("down")))
    data = env.make_world("A", chapters=1)

    result = env.execute(data["world_id"], data["job_id"], data["runs"][1])

    assert result["status"] == "failed"
    status, error = env.run(data["runs"][1]["run_id"])
    assert status == "failed" and "Ollama request failed" in error
    job = env.job(data["job_id"])
    assert job["status"] == "failed" and job["completed"] == 0
    assert env.world_rows(data["world_id"]) == ZERO  # nothing fabricated by a mock engine


def test_explicit_mock_mode_still_extracts_end_to_end(phase1_env, monkeypatch):
    env = phase1_env
    monkeypatch.setattr(llm_client, "provider", "mock")
    data = env.make_world("A", chapters=1)

    result = env.execute(data["world_id"], data["job_id"], data["runs"][1])

    assert result["status"] == "success"
    assert env.run(data["runs"][1]["run_id"])[0] == "done"
    assert env.job(data["job_id"])["status"] == "done"
    assert env.world_rows(data["world_id"])["entities"] > 0


def test_unparseable_llm_output_fails_the_run_instead_of_finishing_empty(phase1_env, monkeypatch):
    env = phase1_env
    monkeypatch.setattr(llm_client, "generate", lambda *a, **k: "I'm sorry, I cannot help with that.")
    data = env.make_world("A", chapters=1)

    result = env.execute(data["world_id"], data["job_id"], data["runs"][1])

    assert result["status"] == "failed"
    status, error = env.run(data["runs"][1]["run_id"])
    assert status == "failed" and "unusable LLM output" in error
    assert env.world_rows(data["world_id"]) == ZERO


def test_ollama_extraction_request_sets_context_and_output_limits(monkeypatch):
    """The real request body: Ollama's defaults (4096-token context, unbounded output) are not relied on."""
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": '{"ok": true}'}})

    real_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(llm_client, "provider", "ollama")
    assert llm_client.generate(prompt="p", system_prompt="s", json_mode=True, temperature=0.0) == '{"ok": true}'
    [body] = sent
    assert body["options"] == {"temperature": 0.0, "num_ctx": settings.OLLAMA_NUM_CTX,
                               "num_predict": settings.OLLAMA_NUM_PREDICT}
    assert (settings.OLLAMA_NUM_CTX, settings.OLLAMA_NUM_PREDICT) == (8192, 4096)
    assert body["format"] == "json" and body["messages"][0] == {"role": "system", "content": "s"}
