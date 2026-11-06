"""A client for any OpenAI-compatible chat-completions endpoint.

Several frontier labs expose the same wire format on their own domains, which
matters here for a practical reason: the eval has to be runnable from networks
where some providers are unreachable. One client with a configurable base URL
covers DeepSeek, Alibaba's Qwen, Moonshot's Kimi and Zhipu's GLM, so adding a
model family is a config change rather than new code.

The base URL and the environment variable holding the key both come from the
model set in `config/models.yaml`. Keys are read from the environment only.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from .llm import CachedClient, Completion, LLMError

__all__ = ["OpenAICompatibleClient", "OpenAICompatibleError"]


class OpenAICompatibleError(LLMError):
    pass


class OpenAICompatibleClient(CachedClient):
    provider = "openai-compatible"
    env_var = "OPENAI_COMPATIBLE_API_KEY"

    def __init__(
        self,
        *args: Any,
        base_url: str = "",
        env_var: str | None = None,
        max_retries: int = 6,
        **kwargs: Any,
    ) -> None:
        if env_var:
            # Set before super().__init__ so the base class reads the right one.
            self.env_var = env_var
        super().__init__(*args, max_retries=max_retries, **kwargs)
        self.base_url = base_url.rstrip("/")
        if not self.api_key:
            self.api_key = os.environ.get(self.env_var)

    def build_payload(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        seed: int | None,
        reasoning_effort: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            # Part of the cache key, so a run against a different endpoint can
            # never collide with a cached response from another provider.
            "_endpoint": self.base_url,
        }
        if seed is not None:
            payload["seed"] = seed
        if reasoning_effort is not None:
            payload["reasoning_effort"] = reasoning_effort
        return payload

    def send(self, payload: dict[str, Any]) -> httpx.Response:
        body = {k: v for k, v in payload.items() if not k.startswith("_")}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self.timeout) as client:
            return client.post(
                f"{self.base_url}/chat/completions", headers=headers, json=body
            )

    def parse(self, model: str, body: dict[str, Any], cached_hit: bool) -> Completion:
        if "error" in body and not body.get("choices"):
            raise OpenAICompatibleError(str(body["error"]))
        choices = body.get("choices") or []
        if not choices:
            raise OpenAICompatibleError(f"{model} returned no choices: {str(body)[:300]}")

        message = choices[0].get("message") or {}
        text = message.get("content") or ""
        if not text and message.get("reasoning_content"):
            # Some reasoning models put everything in a separate channel when
            # they exhaust the output budget; surfacing it beats an empty answer.
            text = message["reasoning_content"]

        usage = body.get("usage") or {}
        return Completion(
            text=text,
            model=body.get("model") or model,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            cost_usd=0.0,  # these endpoints do not return a cost; see `price`
            cached=cached_hit,
            finish_reason=str(choices[0].get("finish_reason") or ""),
            raw=body,
        )
