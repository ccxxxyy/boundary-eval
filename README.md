# FaultLine

**An eval for code that is correct until the process dies.**

Frontier models write payment, queue and outbox code that is clean, idiomatic,
and passes the tests a developer would write for it. FaultLine asks a different
question: does that code still hold when the process is killed between two
operations, or when a network call times out after it has already taken effect?

Every task is a small piece of business logic with one invariant that must hold
no matter what fails. The grader runs each candidate solution through *every*
reachable combination of crash point and timeout outcome, and when it finds a
violation it prints the exact execution that caused it.

## The limitation being measured

Take task 1: charge a customer exactly once, against a gateway that
deduplicates on an idempotency key and may time out after the charge has
already gone through.

The instinct every payment integration guide encourages — generate a fresh
unique idempotency key for the request — produces this:

```python
key = new_id()
charge_id = gateway.charge(idempotency_key=key, amount_cents=amount_cents)
store.put(f"order:{order_id}:charge", charge_id)
```

It passes every public scenario in this repository, including a redelivery
test. It also charges the customer twice, and `make demo` prints the three-line
execution that proves it:

```
  attempt 1 (crashes before op #2):
    #0  store.get                key='order:ord_7F3A91:charge'  -> ok (None)
    #1  gateway.charge           key='id-a1-1' amount=4999  -> ok (ch_1)
    #2  store.put                key='order:...:charge' value='ch_1'  -> CRASH
  attempt 2 (runs to completion):
    ...
  charges on the gateway: ch_1(4999, key=id-a1-1), ch_2(4999, key=id-a2-1)
  VIOLATION: the customer was charged 2 times (expected exactly one)
```

The key only ever existed in memory. The restarted process mints a new one, and
the gateway has no way to connect the two attempts. The fix is one line of
reordering — durably claim the key *before* spending it — and it is invisible to
any test that does not kill the process at that exact point.

That is the shape of every task here: a real, well-understood engineering
requirement, a defensible single correct answer, and a failure mode that normal
testing cannot see.

## Who this is for

Anyone evaluating a model for backend work where retries and restarts are
facts of life: payment flows, queue consumers, outbox publishers, job runners.
Functional correctness benchmarks do not cover this, and in production it is
where the expensive incidents come from.

## Why the failures are real and not a trick

- **The fault model is fully disclosed.** Each task prompt lists exhaustively
  what can go wrong, including that the process can die before any durable
  write and that the queue redelivers. Nothing is hidden except the enumeration
  of crash points.
- **Solutions get what a developer gets.** Before grading, each candidate is
  run against a set of public scenarios covering normal delivery, redelivery
  and both flavours of timeout. Failures are reported back and the model may
  revise. Fault-injection output is never fed back, so no model can grind
  against the grader.
- **Every task is solvable.** Each ships a reference solution plus at least one
  known-correct solution of a deliberately different shape, and the test suite
  fails if any of them is reported unsafe.
- **The grader is tested, not asserted.** See below.

## Grader validation

The grader's reliability is itself under test, because a counterexample is only
worth anything if it is both real and reproducible:

| Guarantee | How it is checked |
|---|---|
| No false failures | Reference and alternate solutions must all be reported crash-safe |
| Not shape-specific | Alternates deliberately differ (one never touches the store, one never calls `lookup`) |
| No false passes | Every known-broken solution must be reported unsafe |
| Failing for the right reason | Each broken solution declares its expected violation; the grader must report that one |
| Adds real signal | At least one broken solution must pass every public scenario and still be caught |
| Deterministic | Two runs must produce identical trace counts and an identical counterexample |
| Contained | Code that never terminates, does not import, or catches the crash itself must be reported, not tolerated |

```
make validate-grader
```

No API key, no network, no cost. Runs in about two seconds.

## Running it

```bash
uv sync --extra dev          # or: pip install -e ".[dev]"

make validate-grader         # grader's own test suite
make demo                    # reference solution, then the counterexample
make reproduce               # the above plus the model results, from cache
```

To grade a single file:

```bash
python -m faultline.grade \
  --task tasks/t01_idempotent_charge \
  --solution path/to/your_module.py
```

### Running models yourself

```bash
export OPENROUTER_API_KEY=...      # never stored in this repository
python -m faultline.models_check   # confirm the configured slugs still exist
python -m faultline.run_eval --set dev --seeds 1      # cheap smoke test
python -m faultline.run_eval --set frontier           # reporting run
```

Every response is cached under `results/raw/` keyed by the exact request, so
`--offline` replays the shipped results for free and produces identical
numbers. Models are configured in `config/models.yaml`.

## Cost and runtime

| | |
|---|---|
| `make validate-grader` | ~2 s, free |
| `make reproduce` | under a minute, free (replays the cache) |
| Full frontier run | see `results/` for the recorded spend |

## Layout

```
faultline/
  world.py        deterministic store, gateway and crash points
  faults.py       what can go wrong in one attempt, and in one trace
  injector.py     adaptive exhaustive fault injection, counterexample minimisation
  selftest.py     the public scenarios a solution author is given
  grade.py        grade one solution against one task
  sandbox.py      grade model-written code in its own process
  openrouter.py   cached, cost-accounted model client
  run_eval.py     prompt, repair loop, grade, record
tasks/<task>/
  prompt.md       the contract, as the model sees it
  task.py         entrypoint wiring and the invariant check
  reference.py    known-correct
  alternates/     known-correct, different shape
  broken/         known-broken, each declaring its expected violation
validation/       the grader's own test suite
```

## Originality

Built from scratch for the micro1 Eval Hackathon. No code in this repository
predates the event; the repository's first commit is part of the submission.
