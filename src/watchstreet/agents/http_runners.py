"""LLM backends reached over HTTP: Anthropic Messages API and OpenAI-compatible servers."""

import json
from collections.abc import Sequence
from typing import Any

import httpx

from watchstreet.agents.base import AgentError, AgentRequest
from watchstreet.agents.tools import Tool, ToolError, ToolRun
from watchstreet.constants import MAX_TOOL_STEPS, TOOL_RESULT_MAX_CHARS

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_MAX_TOKENS = 4096


def _post(client: httpx.Client, url: str, headers: dict[str, str], body: dict[str, Any]) -> Any:
    try:
        response = client.post(url, headers=headers, json=body)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        msg = f"LLM request failed: {exc}"
        raise AgentError(msg) from exc


class AnthropicRunner:
    name = "anthropic"

    def __init__(self, api_key: str, model: str, timeout_s: float) -> None:
        if not api_key:
            msg = "ANTHROPIC_API_KEY is not set"
            raise AgentError(msg)
        self._model = model
        self._headers = {"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION}
        self._client = httpx.Client(timeout=timeout_s)

    def complete(self, request: AgentRequest) -> str:
        data = _post(
            self._client,
            ANTHROPIC_URL,
            self._headers,
            {
                "model": self._model,
                "max_tokens": ANTHROPIC_MAX_TOKENS,
                "system": request.system,
                "messages": [{"role": "user", "content": request.prompt}],
            },
        )
        try:
            return "".join(b["text"] for b in data["content"] if b.get("type") == "text")
        except (KeyError, TypeError) as exc:
            msg = "Unexpected Anthropic response shape"
            raise AgentError(msg) from exc


class OpenAICompatibleRunner:
    """Works with llama.cpp server, Ollama, LM Studio, vLLM, OpenAI: any /chat/completions API.

    With ``tools_enabled`` it also drives a tool-calling loop (the server must support the
    ``tools`` parameter; llama.cpp needs ``--jinja``).
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        timeout_s: float,
        *,
        name: str = "openai",
        tools_enabled: bool = False,
    ) -> None:
        self.name = name
        self.supports_tools = tools_enabled
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._model = model
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.Client(timeout=timeout_s)

    def _chat(self, messages: list[dict[str, Any]], tools: Sequence[Tool] = ()) -> dict[str, Any]:
        body: dict[str, Any] = {"model": self._model, "messages": messages}
        if tools:
            body["tools"] = [t.spec() for t in tools]
        data: dict[str, Any] = _post(self._client, self._url, self._headers, body)
        return data

    def complete(self, request: AgentRequest) -> str:
        data = self._chat(
            [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.prompt},
            ],
        )
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            msg = "Unexpected chat completion response shape"
            raise AgentError(msg) from exc

    def run_with_tools(self, system: str, prompt: str, tools: Sequence[Tool]) -> ToolRun:
        by_name = {t.name: t for t in tools}
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        calls = prompt_tokens = completion_tokens = 0
        for step in range(1, MAX_TOOL_STEPS + 1):
            data = self._chat(messages, tools)
            usage = data.get("usage") or {}
            prompt_tokens += int(usage.get("prompt_tokens", 0))
            completion_tokens += int(usage.get("completion_tokens", 0))
            try:
                message = data["choices"][0]["message"]
            except (KeyError, IndexError, TypeError) as exc:
                msg = "Unexpected chat completion response shape"
                raise AgentError(msg) from exc
            requested = message.get("tool_calls") or []
            if not requested:
                return ToolRun(
                    str(message.get("content") or ""),
                    step,
                    calls,
                    prompt_tokens,
                    completion_tokens,
                )
            messages.append(message)
            for call in requested:
                calls += 1
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", ""),
                        "content": _execute(by_name, call.get("function") or {}),
                    },
                )
        note = f"(Tool-Schleife nach {MAX_TOOL_STEPS} Schritten beendet)"
        return ToolRun(note, MAX_TOOL_STEPS, calls, prompt_tokens, completion_tokens)


def _execute(tools: dict[str, Tool], function: dict[str, Any]) -> str:
    """Run one requested tool call; every problem is reported back to the model as text."""
    name = str(function.get("name", ""))
    tool = tools.get(name)
    if tool is None:
        return f"ERROR: unknown tool '{name}'. Available: {', '.join(tools)}"
    try:
        arguments = json.loads(function.get("arguments") or "{}")
    except json.JSONDecodeError as exc:
        return f"ERROR: arguments are not valid JSON: {exc}"
    if not isinstance(arguments, dict):
        return "ERROR: arguments must be a JSON object"
    try:
        return tool.handler(arguments)[:TOOL_RESULT_MAX_CHARS]
    except ToolError as exc:
        return f"ERROR: {exc}"
