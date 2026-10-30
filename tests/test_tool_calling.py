import itertools
import json

import httpx
from sqlalchemy import select

from watchstreet.agents.http_runners import OpenAICompatibleRunner
from watchstreet.domain import TicketStatus
from watchstreet.models import Insight, Stock, Thesis, Ticket
from watchstreet.services import portfolio
from watchstreet.worker import drain_queue

_ids = itertools.count()


def call(name, **arguments):
    return {
        "id": f"c{next(_ids)}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


def reply(message, prompt=10, completion=5):
    return {
        "choices": [{"message": message}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
    }


class FakeLlm:
    """Plays back scripted assistant turns and records what the harness sent."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.requests = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        turn = (
            self.turns.pop(0) if self.turns else reply({"role": "assistant", "content": "fertig"})
        )
        return httpx.Response(200, json=turn)


def use_llm(container, llm, monkeypatch):
    runner = OpenAICompatibleRunner("http://llm/v1", "m", "", 5, name="llama", tools_enabled=True)
    monkeypatch.setattr(runner, "_client", httpx.Client(transport=httpx.MockTransport(llm)))
    container.runner = runner


def holding(container):
    with container.session_factory() as s:
        portfolio.add_holding(s, container.market, portfolio.NewHolding("AAPL", 5, 100.0))
        s.commit()


def test_agent_uses_tools_and_guardrails_answer_immediately(container, monkeypatch):
    llm = FakeLlm(
        [
            reply(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        call("get_price_summary", interval="1d"),
                        call("get_fundamentals"),
                        call("add_insight", category="risk", text="Hohe Bewertung"),
                        call("set_goal", text="Position halten"),
                        call("set_thesis", text="Qualitätswachstum", status="active"),
                        call(
                            "propose_followup",
                            workflow="topic_analysis",
                            topic="Wettbewerb",
                            reason="r",
                        ),
                        call(
                            "propose_followup",
                            workflow="topic_analysis",
                            topic="wettbewerb",
                            reason="dup",
                        ),
                        call(
                            "propose_followup", workflow="initial_holding", reason="nicht erlaubt"
                        ),
                        call("add_insight", category="bogus", text="x"),
                        call("no_such_tool"),
                    ],
                },
                prompt=100,
                completion=40,
            ),
            reply({"role": "assistant", "content": "Solide Position, Risiken beobachten."}, 50, 20),
        ]
    )
    use_llm(container, llm, monkeypatch)
    holding(container)
    drain_queue(container)

    answers = [m["content"] for m in llm.requests[1]["messages"] if m["role"] == "tool"]
    assert len(answers) == 10
    assert answers[5].startswith("accepted")
    assert answers[6] == "ERROR: rejected by guardrails: duplicate"
    assert answers[7].startswith("ERROR: rejected by guardrails: workflow must be one of")
    assert answers[8].startswith("ERROR: 'category' must be one of")
    assert answers[9].startswith("ERROR: unknown tool 'no_such_tool'")

    with container.session_factory() as s:
        first = s.scalars(select(Ticket).order_by(Ticket.id)).first()
        assert first.status == TicketStatus.DONE
        assert first.summary == "Solide Position, Risiken beobachten."
        data = first.result["data"]
        assert data["mode"] == "tools" and data["runner"] == "llama"
        assert data["tool_calls"] == 10 and data["steps"] == 2
        assert (data["prompt_tokens"], data["completion_tokens"]) == (150, 60)
        stock = s.scalar(select(Stock))
        texts = {(i.category, i.text) for i in s.scalars(select(Insight))}
        assert ("risk", "Hohe Bewertung") in texts and ("goal", "Position halten") in texts
        assert s.scalars(select(Thesis)).first().text == "Qualitätswachstum"
        children = s.scalars(select(Ticket).where(Ticket.parent_id == first.id)).all()
        assert [(t.workflow, t.params["topic"]) for t in children] == [
            ("topic_analysis", "Wettbewerb")
        ]
        assert stock.scores  # deterministic scores persisted by the harness, not the model


def test_prompt_is_compact_and_tools_are_offered(container, monkeypatch):
    llm = FakeLlm([reply({"role": "assistant", "content": "ok"})])
    use_llm(container, llm, monkeypatch)
    holding(container)
    drain_queue(container)
    first = llm.requests[0]
    names = {t["function"]["name"] for t in first["tools"]}
    assert {"get_price_summary", "add_insight", "propose_followup", "set_thesis"} <= names
    user_prompt = first["messages"][1]["content"]
    assert "valuation_v1" in user_prompt  # deterministic scores are handed over
    assert "fundamentals" not in user_prompt  # details are pulled on demand


def test_tool_mode_falls_back_to_json_when_server_rejects_tools(container, monkeypatch):
    analysis = {"summary": "per JSON", "insights": [{"category": "note", "text": "n"}]}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "tools" in body:
            return httpx.Response(400, json={"error": "tools unsupported"})
        return httpx.Response(200, json=reply({"content": json.dumps(analysis)}))

    runner = OpenAICompatibleRunner("http://llm/v1", "m", "", 5, tools_enabled=True)
    monkeypatch.setattr(runner, "_client", httpx.Client(transport=httpx.MockTransport(handler)))
    container.runner = runner
    holding(container)
    drain_queue(container)
    with container.session_factory() as s:
        first = s.scalars(select(Ticket).order_by(Ticket.id)).first()
        assert first.status == TicketStatus.DONE and first.summary == "per JSON"
        assert first.result["data"]["mode"] == "json"


def test_tool_loop_stops_after_max_steps(container, monkeypatch):
    forever = [reply({"role": "assistant", "content": None, "tool_calls": [call("get_news")]})] * 20
    llm = FakeLlm(forever)
    use_llm(container, llm, monkeypatch)
    holding(container)
    drain_queue(container)
    with container.session_factory() as s:
        first = s.scalars(select(Ticket).order_by(Ticket.id)).first()
        assert first.status == TicketStatus.DONE
        assert "Tool-Schleife" in first.summary and first.result["data"]["steps"] == 8
