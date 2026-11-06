"""OpenRouter client. Shared caching and retry logic lives in `llm.py`."""

from __future__ import annotations

from typing import Any

import httpx

from .llm import CachedClient, Completion, LLMError

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

__all__ = ["Completion", "OpenRouterClient", "OpenRouterError"]


class OpenRouterError(LLMError):
    pass


class OpenRouterClient(CachedClient):
    provider = "openrouter"
    env_var = "OPENROUTER_API_KEY"

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
        }
        if seed is not None:
            payload["seed"] = seed
        if reasoning_effort is not None:
            payload["reasoning"] = {"effort": reasoning_effort}
        return payload

    def send(self, payload: dict[str, Any]) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": "FaultLine eval",
        }
        with httpx.Client(timeout=self.timeout) as client:
            return client.post(ENDPOINT, headers=headers, json=payload)

    def parse(self, model: str, body: dict[str, Any], cached_hit: bool) -> Completion:
        if "error" in body and not body.get("choices"):
            raise OpenRouterError(str(body["error"]))
        choices = body.get("choices") or []
        if not choices:
            raise OpenRouterError(f"{model} returned no choices: {str(body)[:300]}")
        message = choices[0].get("message") or {}
        text = message.get("content") or ""
        if not text and message.get("reasoning"):
            # Some models put everything in the reasoning channel when they run
            # out of output budget; surfacing it beats reporting an empty answer.
            text = message["reasoning"]
        usage = body.get("usage") or {}
        cost = float(usage.get("cost") or 0.0)
        if not cached_hit:
            self.spent_usd += cost
        return Completion(
            text=text,
            model=body.get("model") or model,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            cost_usd=cost,
            cached=cached_hit,
            finish_reason=str(choices[0].get("finish_reason") or ""),
            raw=body,
        )
