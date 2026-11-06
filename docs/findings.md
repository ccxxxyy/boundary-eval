# Findings

This is the analysis the video walks through. Numbers below that come
from a model run are labelled with the model, the seed, and whether the
prompts were the de-hinted versions shipped in this repository.

Frontier-model numbers are **not** in this file yet. OpenRouter credits
are at zero (FAQ 23: the organisers do not provide model credits). The
harness, the tasks, and the cheap-model pipeline are otherwise complete.
Re-run `python -m faultline.run_eval --set frontier` after credits are
added; the client caches every response under `results/raw/`, so a
partial run can be resumed without paying twice.

## What the eval claims

A model can write payment, queue and outbox code that:

1. is clean and idiomatic,
2. passes every test a careful developer would write (redelivery, each
   disclosed remote-call outcome),
3. and is still wrong the first time the process dies between two
   durable writes, or the first time a timeout is actually an applied
   request whose response was lost.

That third state is the number that matters. The summary column is
**passed own tests but unsafe**. Scoring a truncated reply or a syntax
error as a crash-safety failure would overstate the finding, so those
runs are reported separately as **unusable**.

## Grader, independent of any model

```
make validate-grader     # 40 tests, ~20 s, no network
make matrix
```

`make matrix` currently reports:

- 5 tasks
- 13 known-correct solutions accepted
- 27 known-broken solutions rejected, each for the violation its
  docstring names
- 11 broken solutions that pass every public scenario and are still
  caught by fault injection
- no false passes and no false failures

The headline counterexample is task 3, `make demo`:

| solution | public self-check | exhaustive injection |
|---|---|---|
| mark seen, then apply | 7/7 | balance `-77500` instead of `172500` (`m_payroll` looks lost) |
| apply, then mark seen | 7/7 | balance `422500` instead of `172500` (`m_payroll` applied twice) |
| reference (one atomic record) | 7/7 | crash-safe |

Both broken orderings are code a reviewer would approve. They fail in
opposite directions, which is why this is a real limitation and not a
gotcha about a missing import.

## Cheap-model pipeline check (DeepSeek V4 Flash, 1 seed)

Built and tested on a cheap OpenRouter model first, as the event
instructions recommend. Prompts were then stripped of the sentence that
handed the model the key insight ("you cannot write two keys in one
atomic step"). After that de-hinting:

| task | first try | after 2 repair rounds | passed own tests but unsafe |
|---|---|---|---|
| t01 idempotent charge | public 5/7, unsafe | 7/7, crash-safe | no |
| t02 outbox | public 4/7, unsafe | unusable (truncated / no module) | no |
| t03 ledger | 7/7, crash-safe | (no repair needed) | no |
| t04 legacy payout | public 5/7, unsafe | 7/7, crash-safe | no |
| t05 saga | public 6/11, unsafe | unusable (indent error after repair) | no |

Cost of this run: about **$0.04**.

What this does and does not show:

- The pipeline works: prompt, extract, public self-check, repair,
  hidden injection, cost accounting, disk cache.
- A strong cheap model can land the single-key ledger trick on the
  first try (task 3). That task is still the right task: the two
  broken orderings above are what most production code actually does,
  and they still fool the public tests. A model passing it is a true
  pass, not a leak.
- Repair rounds help on the calibration task and on the legacy-payout
  task. They do not automatically produce crash-safe code; they
  sometimes produce truncated or syntactically broken revisions, which
  we refuse to count as "the model cannot do crash safety".
- The headline column is 0/5 on this model. That is expected of a
  cheap smoke test. The question the judges care about is whether a
  *frontier* model hands over code that is green on its own tests and
  still loses or doubles money. That run is what the credits are for.

## Gemini free tier (Gemini 3.5 Flash and Gemini 3 Flash, 1 seed)

Run through Google AI Studio, which is reachable from networks where
OpenRouter's frontier providers are not. 7 of 10 runs completed before
the key's credits were exhausted; the other 3 failed with HTTP 402 and
503 and are recorded as unusable, not as model failures.

| | completed | crash-safe | passed own tests but unsafe |
|---|---|---|---|
| Gemini 3.5 Flash | 3 | 3 | 0 |
| Gemini 3 Flash | 4 | 4 | 0 |

**This is a negative result for the eval, and it is the important one.**
Both models were crash-safe on every task they finished, mostly on the
first attempt. Inspecting what they wrote confirms the passes are real,
not a grader leak: on task 3 the model wrote the composite single-key
compare-and-set with a retry loop, and on task 2 it persisted the
`event_id` through compare-and-set before publishing and marked the
publish durable afterwards.

### Why the tasks turned out to be too easy

Under crash-only, single-threaded fault injection, *any* task whose
entire state fits in one key has a universal solution: read the key,
compute, write the key back in one atomic put. The composite blob is
textbook, and current models reproduce it on demand.

The tasks that are not reducible to one blob are the ones with an
external effect that cannot live inside it: the charge in task 1, the
transfer in task 4, the seat hold in task 5. Those are the right shape,
but the guarding pattern ("write the idempotency key durably before
spending it") is equally well memorized.

So the eval as it stands measures recall of three known patterns. That
is not a frontier limitation. Two changes follow from this, and both
are testable without spending anything, because the reference and
known-broken solutions are in the repository:

1. **Bound the size of a stored value.** A store that refuses values
   over a few hundred bytes is realistic - no production system keeps
   every processed message id in one row forever - and it removes the
   universal blob solution, forcing the dedup marker and the data it
   guards to be reconciled some other way.
2. **Add takeover, not just crashes.** At-least-once queues redeliver
   to a *second* worker while the first is merely stalled, not dead.
   Exactly-once then needs a fencing token that gates every durable
   write and every external effect. A crash-only harness cannot see
   this class of bug at all, and it is where production incidents
   actually come from.

Task 5 (saga compensation) is the one task no model has yet completed
cleanly: DeepSeek produced a syntax error after repair and both Gemini
models hit 402 before finishing. It has 11 public scenarios and about
1200 schedules. It may already carry signal that has not been measured.

## Failure-mode taxonomy (from known-broken solutions, not from models)

These are the ways production code actually goes wrong. Each has a
fixture under `tasks/*/broken/` that the grader must catch.

1. **Wrong order of two durable facts.** Mark-then-apply loses work;
   apply-then-mark duplicates it. Task 3.
2. **Idempotency key held only in memory.** A crash mints a new key and
   a second charge. Task 1.
3. **"Already done" returns early.** Shipped is not notified. Task 2.
4. **Retrying a non-idempotent legacy call.** At-most-once plus
   escalation is the honest protocol; a retry loop is not. Task 4.
5. **Treating timeout as success, or as decline.** One over-charges,
   the other releases a seat the customer paid for. Task 5.
6. **Compensating before the outcome is durable.** A crash after
   release and before the status write leaks the seat. Task 5.
7. **Swallowing the crash.** A bare `except Exception` that continues
   is a different process than the one that died. The harness reports
   this as a violation, not as crash-safety.

## What still has to be true for the submission

- Frontier models (Opus 5.5, GPT-5.6 Sol Pro, Gemini 3.1 Pro, Grok 4.7)
  run at 1 seed first, then 3 seeds if the 1-seed table already shows
  the headline column above zero.
- `docs/findings.md` updated with those numbers and one counterexample
  trace per failing task.
- `README.md` cost/runtime table filled in from the recorded spend.
- `results/raw/` shipped in the ZIP so `make reproduce` is offline and
  free for judges.
