# Video walkthrough (≤ 5 minutes)

Host on YouTube, Drive, Loom or Vimeo. Anyone with the link must be able
to open it without requesting permission. Face and own voice are
optional; an AI voice is allowed.

Do not put the video inside the ZIP.

## Script (about 4 minutes)

**0:00–0:25 — The problem.**
"Frontier models write payment and queue code that passes its tests and
is still wrong the first time the process dies. This eval measures that."

Show the README title and the one-sentence claim.

**0:25–1:20 — The clearest example (task 3).**
Run `make demo` in a clean terminal.

- Point at the two broken orderings: both 7/7 on the public self-check.
- Show the counterexample: crash before the balance write, redelivery,
  `m_payroll` gone, balance off by 250000.
- One sentence on why the other ordering is the opposite bug
  (double-count, not loss).
- One sentence on the fix: the marker and the data have to be one
  atomic write, because the store has no multi-key transaction.

This is the clip judges will remember. Do not rush it.

**1:20–2:10 — Not a trick.**
Three facts, one sentence each, while scrolling the prompt:

1. The fault model is fully disclosed in the prompt.
2. The model gets the public scenarios and a repair loop, like a
   developer. Fault-injection output is never fed back.
3. Every task ships a reference plus a differently-shaped correct
   solution; the test suite fails if the grader rejects them.

**2:10–2:50 — The grader is tested.**
Run `make matrix` (or show a pre-recorded ending if time is tight).
Land on the last three lines:

```
5 tasks
11 broken solutions pass every public scenario and are still caught
no false passes and no false failures
```

Mention `make validate-grader` is 40 tests, ~20 seconds, no API key.

**2:50–4:00 — What models do.**
Show the summary table from `python -m faultline.run_eval`.

The column to highlight is **passed own tests but unsafe**. That is
code a reviewer would have merged.

If a frontier run is in the repo, pick one counterexample from a
frontier model, not from a cheap model, and read the violation out
loud. If only the cheap run is in, say so honestly and show that the
pipeline is identical for the frontier set (`config/models.yaml`).

**4:00–4:30 — How to reproduce.**
Three commands, no commentary beyond "this is what the judges run":

```
uv sync --extra dev
make validate-grader
make reproduce
```

`make reproduce` is offline once `results/raw/` is in the ZIP.

**4:30–4:50 — Close.**
"The limitation is not that models cannot write Python. It is that they
write the code we already ship, and that code loses money when the
process dies."

## Recording notes

- Terminal: large font, no secrets in the environment display.
- Do not paste or show `OPENROUTER_API_KEY`.
- If a command is slow, cut to a finished scroll rather than waiting
  in silence.
- Watch the whole video once as a stranger with the link in an
  incognito window before submitting.
