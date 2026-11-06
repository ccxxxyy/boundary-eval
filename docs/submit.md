# Submission checklist

Deadline: **9 November 2026, 05:15 GMT** (13:15 Beijing). One eval, ZIP
plus video link plus short description. Latest complete submission
counts.

## Three artefacts (FAQ 30)

1. **ZIP**, code only, max 50 MB. No video inside. No API keys.
2. **Video link**, ≤ 5 minutes, opens without permission.
3. **Short description** on the event page.

## ZIP contents

Include:

- `faultline/`, `tasks/`, `validation/`, `config/`
- `README.md`, `docs/`, `Makefile`, `pyproject.toml`
- `results/*.jsonl` and `results/solutions/` (the graded outputs)
- `results/raw/` (the response cache that makes `--offline` work)

Exclude:

- `.venv/`, `__pycache__/`, `.pytest_cache/`, `.git/`
- `.env`, any file containing `sk-or-` or `OPENROUTER_API_KEY=`
- `*.zip`, the video file itself

```
python scripts/secret_scan.py
python scripts/package.py
```

Then open the ZIP on a machine (or a fresh folder) that is not this
working tree and run:

```
uv sync --extra dev
make validate-grader
make matrix
make reproduce
```

## Short description (draft, fill numbers after the frontier run)

FaultLine tests whether a model can write crash-safe exactly-once
business logic: charges, outbox publishes, ledger consumers, legacy
payouts, saga compensation. Models get the same tests a developer
would write, and a chance to repair. The grade is exhaustive
deterministic fault injection, which the model never sees. The grader
itself is tested: 13 known-correct solutions pass, 27 known-broken
solutions fail for the declared reason, 11 of those look correct on
the public tests. [Frontier result one-liner goes here.]

## Things the FAQ forbids

- Credentials in the ZIP (FAQ 24, 39)
- Confidential employer or client data (FAQ 27)
- More than one eval, or a second account (FAQ 4, 38, 50)
- Fabricated model results (FAQ 50)
- Claiming pre-existing code as work for this event (FAQ 28)
