"""Minimal OpenRouter client.

Two properties matter more than features here:

  * **Caching.** Every response is written to disk keyed by the exact request.
    Re-running the eval therefore costs nothing and produces byte-identical
    numbers, which is what makes the headline results checkable by someone who
    does not want to spend money on API calls.
  * **Accounting.** Token counts and cost come back with every call, so the
    README can state what a full run actually costs instead of guessing.

The API key is read from the environment only. Nothing in this repository
should ever contain one.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
CACHE_DIR = Path(__file__).resolve().parent.parent / "results" / "raw"


class OpenRouterError(RuntimeError):
    pass


@dataclass
class Completion:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    cached: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


def _request_key(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:40]


class OpenRouterClient:
    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: Path | None = None,
        timeout: float = 600.0,
        max_retries: int = 5,
        offline: bool = False,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.max_retries = max_retries
        self.offline = offline
        self.spent_usd = 0.0

    def complete(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 8000,
        seed: int | None = None,
        reasoning_effort: str | None = None,
    ) -> Completion:
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

        key = _request_key(payload)
        cached = self._read_cache(key)
        if cached is not None:
            return self._to_completion(model, cached, cached_hit=True)

        if self.offline:
            raise OpenRouterError(
                f"offline mode: no cached response for {model} (request {key}). "
                "Run without --offline to populate the cache."
            )
        if not self.api_key:
            raise OpenRouterError("OPENROUTER_API_KEY is not set")

        body = self._post_with_retries(payload, key)
        self._write_cache(key, body, payload)
        return self._to_completion(model, body, cached_hit=False)

    # -- plumbing --------------------------------------------------------

    def _post_with_retries(self, payload: dict[str, Any], key: str) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": "FaultLine eval",
        }
        last: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(ENDPOINT, headers=headers, json=payload)
                if response.status_code == 200:
                    body = response.json()
                    if "error" in body and not body.get("choices"):
                        raise OpenRouterError(str(body["error"]))
                    return body
                if response.status_code in (408, 429, 500, 502, 503, 504):
                    last = OpenRouterError(f"HTTP {response.status_code}: {response.text[:300]}")
                else:
                    raise OpenRouterError(f"HTTP {response.status_code}: {response.text[:600]}")
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last = exc
            sleep_for = min(60.0, 2.0**attempt) + random.uniform(0, 1.5)
            time.sleep(sleep_for)
        raise OpenRouterError(f"giving up on {payload['model']} after {self.max_retries} tries: {last}")

    def _to_completion(self, model: str, body: dict[str, Any], cached_hit: bool) -> Completion:
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
            raw=body,
        )

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _read_cache(self, key: str) -> dict[str, Any] | None:
        path = self._cache_path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))["response"]
        except (json.JSONDecodeError, KeyError):
            return None

    def _write_cache(self, key: str, body: dict[str, Any], payload: dict[str, Any]) -> None:
        self._cache_path(key).write_text(
            json.dumps({"request": payload, "response": body}, indent=1, ensure_ascii=False),
            encoding="utf-8",
        )
