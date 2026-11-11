import sys

import httpx
import pytest

from watchstreet.agents.base import AgentError, AgentRequest
from watchstreet.agents.cli_runner import CliRunner
from watchstreet.agents.factory import build_runner
from watchstreet.agents.http_runners import AnthropicRunner, OpenAICompatibleRunner
from watchstreet.agents.offline import OfflineRunner
from watchstreet.config import Settings

REQ = AgentRequest("topic_analysis", "sys", "prompt")


def test_offline_runner_never_invents_an_answer():
    assert OfflineRunner().complete(REQ) == "" and OfflineRunner.name == "offline"


def test_anthropic_runner_parses_text_blocks(monkeypatch):
    runner = AnthropicRunner("key", "model", 5)
    transport = httpx.MockTransport(
        lambda r: (
            httpx.Response(200, json={"content": [{"type": "text", "text": "hi"}]})
            if r.headers["x-api-key"] == "key"
            else httpx.Response(401)
        ),
    )
    monkeypatch.setattr(runner, "_client", httpx.Client(transport=transport))
    assert runner.complete(REQ) == "hi"
    with pytest.raises(AgentError):
        AnthropicRunner("", "m", 5)


def test_openai_runner_and_failure(monkeypatch):
    runner = OpenAICompatibleRunner("http://x/v1/", "m", "", 5)
    ok = httpx.MockTransport(
        lambda _r: httpx.Response(200, json={"choices": [{"message": {"content": "yo"}}]}),
    )
    monkeypatch.setattr(runner, "_client", httpx.Client(transport=ok))
    assert runner.complete(REQ) == "yo"
    bad = httpx.MockTransport(lambda _r: httpx.Response(500))
    monkeypatch.setattr(runner, "_client", httpx.Client(transport=bad))
    with pytest.raises(AgentError):
        runner.complete(REQ)


def test_cli_runner_roundtrip_and_errors():
    echo = CliRunner(f'{sys.executable} -c "import sys; print(sys.stdin.read().upper())"', 10)
    assert "PROMPT" in echo.complete(REQ)
    with pytest.raises(AgentError):
        CliRunner(f'{sys.executable} -c "import sys; sys.exit(3)"', 10).complete(REQ)
    with pytest.raises(AgentError):
        CliRunner("definitely-not-a-binary-xyz", 10).complete(REQ)
    with pytest.raises(AgentError):
        CliRunner("", 10)


def test_factory():
    assert build_runner(Settings(agent_runner="offline")).name == "offline"
    assert build_runner(Settings(agent_runner="openai")).name == "openai"
    assert build_runner(Settings(agent_runner="cli")).name == "cli"
    with pytest.raises(AgentError):
        build_runner(Settings(agent_runner="anthropic"))
    with pytest.raises(AgentError):
        build_runner(Settings(agent_runner="nope"))
