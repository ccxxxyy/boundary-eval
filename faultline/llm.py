"""Shared plumbing for the model clients.

Two properties matter more than features here:

  * **Caching.** Every response is written to disk keyed by the exact request.
    Re-running the eval therefore costs nothing and produces byte-identical
    numbers, which is what makes the headline results checkable by someone who
    does not want to spend money on API calls.
  * **Accounting.** Token counts and cost come back with every call, so the
    README can state what a full run actually costs instead of guessing.

API keys are read from the environment only. Nothing in this repository should
ever contain one.
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

CACHE_DIR = Path(__file__).resolve().parent.parent / "results" / "raw"

RETRYABLE_STATUS = (408, 429, 500, 502, 503, 504)


class LLMError(RuntimeError):
    pass


@dataclass
class Completion:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    cached: bool = False
    finish_reason: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


def request_key(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:40]


class CachedClient:
    """Cache-first request/response loop. Subclasses supply the wire format."""

    provider = "llm"
    env_var = ""

    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: Path | None = None,
        timeout: float = 600.0,
        max_retries: int = 5,
        offline: bool = False,
    ) -> None:
        self.api_key = api_key or (os.environ.get(self.env_var) if self.env_var else None)
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.max_retries = max_retries
        self.offline = offline
        self.spent_usd = 0.0

    # -- subclass hooks --------------------------------------------------

    def build_payload(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        seed: int | None,
        reasoning_effort: str | None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def send(self, payload: dict[str, Any]) -> httpx.Response:
        raise NotImplementedError

    def parse(self, model: str, body: dict[str, Any], cached_hit: bool) -> Completion:
        raise NotImplementedError

    # -- the loop --------------------------------------------------------

    def complete(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 8000,
        seed: int | None = None,
        reasoning_effort: str | None = None,
    ) -> Completion:
        payload = self.build_payload(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            seed=seed,
            reasoning_effort=reasoning_effort,
        )
        key = request_key(payload)

        cached = self._read_cache(key)
        if cached is not None:
            return self.parse(model, cached, cached_hit=True)

        if self.offline:
            raise LLMError(
                f"offline mode: no cached response for {model} (request {key}). "
                "Run without --offline to populate the cache."
            )
        if not self.api_key:
            raise LLMError(f"{self.env_var} is not set")

        body = self._send_with_retries(payload, model)
        self._write_cache(key, body, payload)
        return self.parse(model, body, cached_hit=False)

    def _send_with_retries(self, payload: dict[str, Any], model: str) -> dict[str, Any]:
        last: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = self.send(payload)
                if response.status_code == 200:
                    return response.json()
                detail = f"HTTP {response.status_code}: {response.text[:300]}"
                if response.status_code in RETRYABLE_STATUS:
                    last = LLMError(detail)
                else:
                    raise LLMError(detail)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last = exc
            time.sleep(min(60.0, 2.0**attempt) + random.uniform(0, 1.5))
        raise LLMError(f"giving up on {model} after {self.max_retries} tries: {last}")

    # -- cache -----------------------------------------------------------

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
