"""Verify the configured model ids against each provider's live catalogue.

Worth running before a reporting run: ids get renamed and retired, and an
eval whose headline table names a model that no longer exists is not
reproducible.

    python -m faultline.models_check

OpenRouter's catalogue is public. Google's needs `GEMINI_API_KEY`; without it
that set is skipped rather than failed.
"""

from __future__ import annotations

import os
import sys

import httpx

from .run_eval import load_config

OPENROUTER_CATALOGUE = "https://openrouter.ai/api/v1/models"
GEMINI_CATALOGUE = "https://generativelanguage.googleapis.com/v1beta/models"


def openrouter_prices() -> dict[str, tuple[float, float]]:
    with httpx.Client(timeout=60.0) as client:
        catalogue = client.get(OPENROUTER_CATALOGUE).json()["data"]
    return {
        entry["id"]: (
            float(entry["pricing"]["prompt"]) * 1e6,
            float(entry["pricing"]["completion"]) * 1e6,
        )
        for entry in catalogue
    }


def gemini_models() -> set[str] | None:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    with httpx.Client(timeout=60.0) as client:
        body = client.get(GEMINI_CATALOGUE, headers={"x-goog-api-key": key}).json()
    return {
        entry["name"].removeprefix("models/")
        for entry in body.get("models", [])
        if "generateContent" in entry.get("supportedGenerationMethods", [])
    }


def main() -> int:
    config = load_config()
    prices: dict[str, tuple[float, float]] | None = None
    gemini: set[str] | None = None
    missing: list[str] = []

    for name, group in config.items():
        if name == "defaults":
            continue
        entries = group["models"] if isinstance(group, dict) else group
        provider = group.get("provider", "openrouter") if isinstance(group, dict) else "openrouter"
        print(f"[{name}]  provider={provider}")

        if provider == "openrouter":
            if prices is None:
                prices = openrouter_prices()
            for model in entries:
                slug = model["id"]
                if slug in prices:
                    prompt, completion = prices[slug]
                    print(f"  ok       {slug:<36} ${prompt:g}/${completion:g} per M tokens")
                else:
                    missing.append(slug)
                    print(f"  MISSING  {slug}")
        elif provider == "gemini":
            if gemini is None:
                gemini = gemini_models()
            if gemini is None:
                print("  skipped  GEMINI_API_KEY is not set")
            else:
                for model in entries:
                    slug = model["id"]
                    if slug in gemini:
                        print(f"  ok       {slug}")
                    else:
                        missing.append(slug)
                        print(f"  MISSING  {slug}")
        print()

    if missing:
        print(f"{len(missing)} configured model(s) are not in the catalogue: {', '.join(missing)}")
        return 1
    print("all configured models exist")
    return 0


if __name__ == "__main__":
    sys.exit(main())
