"""Google AI Studio (Gemini API) client. Caching and retries live in `llm.py`.

Why a second provider: OpenRouter's frontier models are not reachable from
every network, and the AI Studio free tier does serve current-generation
models. The eval is provider-agnostic on purpose - the grader never sees
which service produced the code.

Two differences from the OpenAI-style wire format that matter here:

  * There is no `system` role. The system prompt becomes `systemInstruction`,
    and the assistant turns of the repair loop become role `model`.
  * Gemini 3 models always reason, and the reasoning is billed and returned as
    parts flagged `thought`. Those parts are excluded from the answer text but
    counted in the token totals, so the recorded cost is honest.
"""

from __future__ import annotations

from typing import Any

import httpx

from .llm import CachedClient, Completion, LLMError

BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# The free tier serves these; the Pro models answer 429 without billing.
MAX_OUTPUT_TOKENS = 65536

__all__ = ["GeminiClient", "GeminiError"]


class GeminiError(LLMError):
    pass


def to_gemini_messages(
    messages: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    system: list[str] = []
    contents: list[dict[str, Any]] = []
    for message in messages:
        role = message["role"]
        if role == "system":
            system.append(message["content"])
            continue
        contents.append(
            {
                "role": "model" if role == "assistant" else "user",
                "parts": [{"text": message["content"]}],
            }
        )
    instruction = {"parts": [{"text": "\n\n".join(system)}]} if system else None
    return contents, instruction


class GeminiClient(CachedClient):
    provider = "gemini"
    env_var = "GEMINI_API_KEY"

    def __init__(self, *args: Any, max_retries: int = 8, **kwargs: Any) -> None:
        # Connections to this endpoint are dropped mid-handshake on some
        # networks, and the free tier rate-limits by the minute. Both are
        # transient, so retry further than the default before giving up.
        super().__init__(*args, max_retries=max_retries, **kwargs)

    def build_payload(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        seed: int | None,
        reasoning_effort: str | None,
    ) -> dict[str, Any]:
        contents, instruction = to_gemini_messages(messages)
        generation: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": min(max_tokens, MAX_OUTPUT_TOKENS),
        }
        if seed is not None:
            generation["seed"] = seed
        if reasoning_effort is not None:
            generation["thinkingConfig"] = {"thinkingLevel": reasoning_effort}
        payload: dict[str, Any] = {
            "model": model,
            "contents": contents,
            "generationConfig": generation,
        }
        if instruction is not None:
            payload["systemInstruction"] = instruction
        return payload

    def send(self, payload: dict[str, Any]) -> httpx.Response:
        body = {k: v for k, v in payload.items() if k != "model"}
        url = f"{BASE}/{payload['model']}:generateContent"
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        with httpx.Client(timeout=self.timeout) as client:
            return client.post(url, headers=headers, json=body)

    def parse(self, model: str, body: dict[str, Any], cached_hit: bool) -> Completion:
        if "error" in body and not body.get("candidates"):
            raise GeminiError(str(body["error"]))
        candidates = body.get("candidates") or []
        if not candidates:
            feedback = body.get("promptFeedback") or {}
            raise GeminiError(f"{model} returned no candidates: {str(feedback)[:300]}")

        candidate = candidates[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text:
            # Ran out of budget inside the reasoning channel. Surfacing it beats
            # reporting an empty answer, and run_eval records it as unusable.
            text = "".join(p.get("text", "") for p in parts)

        usage = body.get("usageMetadata") or {}
        completion_tokens = int(usage.get("candidatesTokenCount") or 0) + int(
            usage.get("thoughtsTokenCount") or 0
        )
        return Completion(
            text=text,
            model=body.get("modelVersion") or model,
            prompt_tokens=int(usage.get("promptTokenCount") or 0),
            completion_tokens=completion_tokens,
            cost_usd=0.0,  # free tier; a paid run should fill this in
            cached=cached_hit,
            finish_reason=str(candidate.get("finishReason") or ""),
            raw=body,
        )
