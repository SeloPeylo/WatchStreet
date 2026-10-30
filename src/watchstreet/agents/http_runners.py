"""LLM backends reached over HTTP: Anthropic Messages API and OpenAI-compatible servers."""

from typing import Any

import httpx

from watchstreet.agents.base import AgentError, AgentRequest

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
    """Works with OpenAI, Ollama, LM Studio, vLLM and other /chat/completions servers."""

    name = "openai"

    def __init__(self, base_url: str, model: str, api_key: str, timeout_s: float) -> None:
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._model = model
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.Client(timeout=timeout_s)

    def complete(self, request: AgentRequest) -> str:
        data = _post(
            self._client,
            self._url,
            self._headers,
            {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": request.system},
                    {"role": "user", "content": request.prompt},
                ],
            },
        )
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            msg = "Unexpected chat completion response shape"
            raise AgentError(msg) from exc
