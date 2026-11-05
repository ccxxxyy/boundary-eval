"""Verify the configured model slugs against the live OpenRouter catalogue.

Worth running before a reporting run: slugs get renamed and retired, and an
eval whose headline table names a model that no longer exists is not
reproducible. Needs no API key.

    python -m faultline.models_check
"""

from __future__ import annotations

import sys

import httpx

from .run_eval import load_config

CATALOGUE = "https://openrouter.ai/api/v1/models"


def main() -> int:
    config = load_config()
    with httpx.Client(timeout=60.0) as client:
        catalogue = client.get(CATALOGUE).json()["data"]
    prices = {
        entry["id"]: (
            float(entry["pricing"]["prompt"]) * 1e6,
            float(entry["pricing"]["completion"]) * 1e6,
        )
        for entry in catalogue
    }

    missing = []
    for group in ("dev", "frontier"):
        print(f"[{group}]")
        for model in config[group]:
            slug = model["id"]
            if slug in prices:
                prompt, completion = prices[slug]
                print(f"  ok       {slug:<36} ${prompt:g}/${completion:g} per M tokens")
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
