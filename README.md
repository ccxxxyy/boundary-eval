# FaultLine

**An eval for code that is correct until the process dies.**

Frontier models write payment, queue and outbox code that is clean, idiomatic,
and passes the tests a developer would write for it. FaultLine asks a different
question: does that code still hold when the process is killed between two
operations, or when a network call times out after it has already taken effect?

Each of the five tasks is a small piece of business logic with invariants that
must hold no matter what fails. The grader runs every candidate solution
through *every* reachable combination of crash point and remote-call outcome,
and when it finds a violation it prints the exact execution that caused it.

## The clearest example

Task 3 is a ledger consumer behind an at-least-once queue. The store has no
multi-key transaction, so the deduplication marker and the balance it guards
have to become durable separately. There are two obvious orderings, and both
are wrong -- in opposite directions:

| | public self-check | exhaustive fault injection |
|---|---|---|
| mark the message seen, then add the amount | **7/7 passed** | balance is `-77500`, expected `172500`, off by `-250000` (*m_payroll looks lost*) |
| add the amount, then mark the message seen | **7/7 passed** | balance is `422500`, expected `172500`, off by `+250000` (*m_payroll looks applied one time too many*) |

One silently loses money, the other silently double-counts it, and both pass
every test a careful developer would write. The way through is to stop treating
them as two facts and put the dedup state and the data it guards in a single
atomic write.

`make demo` runs the reference and both broken orderings, and prints the
counterexample trace for each:

```
  attempt 1 (crashes before op #3):
    #0  store.get              key='seen:m_payroll'  -> ok (None)
    #1  store.put              key='seen:m_payroll' value='yes'
    #2  store.get              key='balance'  -> ok (None)
    #3  store.put              key='balance' value='250000'  -> CRASH (never applied)
    -- process died here; the queue will redeliver
  attempt 2 (runs to completion):
    ...
  VIOLATION: balance is -77500, expected 172500, off by -250000 (m_payroll looks lost)
```

## The tasks

| | Task | The limitation it measures |
|---|---|---|
| 1 | Charge a customer exactly once | Fixing the idempotency key durably *before* spending it. A key held in memory is regenerated after a crash and buys a second charge. |
| 2 | Ship an order and notify downstream | "Already shipped" is not "already notified". The textbook idempotency guard returns early and loses the event forever. |
| 3 | Apply each ledger message exactly once | With no multi-key transaction, neither ordering of "mark" and "apply" is safe. The dedup state has to live with the data. |
| 4 | Pay out through a legacy system | Against a system with no idempotency key and no way to query it, exactly-once is unreachable. The answer is at-most-once plus an honest escalation, not a retry loop. |
| 5 | Book a seat, or give it back | A decline is final; a timeout is not. Compensating on both releases a seat the customer already paid for. Recording the outcome before the compensation leaks the seat forever. |

Task 1 is deliberately the calibration task: deriving the key from the order id
is correct and simple, so a model with the right instinct passes it. It
discriminates between two implementations that are both common in the wild,
rather than between right and ridiculous.

## Who this is for

Anyone evaluating a model for backend work where retries and restarts are facts
of life: payment flows, queue consumers, outbox publishers, job runners,
settlement pipelines. Functional-correctness benchmarks do not cover this, and
in production it is where the expensive incidents come from.

## Why the failures are real and not a trick

- **The fault model is fully disclosed.** Each prompt lists exhaustively what
  can go wrong, including that the process can die before any durable write and
  that the queue redelivers. Nothing is hidden except the enumeration of crash
  points.
- **Each task is graded only against the faults its own prompt declared.** A
  task that introduces a new failure mode declares it, and both the public
  self-check and the fault injection are derived from that same declaration.
- **Solutions get what a developer gets.** Before grading, each candidate runs
  against the public scenarios: normal delivery, redelivery, and each
  remote-call outcome the prompt lists. Failures are reported back and the model
  may revise. Fault-injection output is never fed back, so no model can grind
  against the grader.
- **Every task is solvable.** Each ships a reference solution plus at least one
  known-correct solution of a deliberately different shape, and the test suite
  fails if any of them is reported unsafe.
- **The grader is tested, not asserted.** See below.

## Grader validation

A counterexample is worth nothing unless it is real, reproducible, and about
the thing it claims to be about. So the grader's reliability is itself under
test:

| Guarantee | How it is checked |
|---|---|
| No false failures | All 13 reference and alternate solutions must be reported crash-safe |
| Not shape-specific | Alternates deliberately differ: one never touches the store, one never calls `lookup`, one derives the balance by summing instead of storing it |
| No false passes | All 27 known-broken solutions must be reported unsafe |
| Failing for the right reason | Each broken solution declares its expected violation in its docstring; the grader must report that specific one |
| Adds real signal | Every task must have a broken solution that passes all public scenarios and is still caught |
| Deterministic | Two runs must produce identical trace counts and an identical counterexample |
| Contained | Code that never terminates, does not import, or catches the crash itself must be reported, not tolerated |

```
make validate-grader     # 37 tests, ~20 s, no API key, no network, no cost
make matrix              # the whole picture, task by task
```

`make matrix` ends with the headline number:

```
5 tasks
11 broken solutions pass every public scenario and are still caught by fault injection
no false passes and no false failures
```

## How the fault injection works

The search is adaptive rather than a blind product over a guessed operation
count. Each attempt is first dry-run to discover the operations the solution
actually performs, and only the reachable crash points are branched on, so the
exploration is exhaustive for the declared crash depth without wasting work on
schedules that cannot occur.

Two details keep it both sound and fast:

- **Crash points sit before mutating operations only.** Crashing before a read
  is indistinguishable from crashing before the following write, because a read
  leaves no durable trace, so skipping those points loses no coverage.
- **Solution code is re-instantiated for every attempt.** The process is
  supposed to have died, so anything stashed in a module-level variable must be
  gone. Importing once and reusing the module would let in-memory bookkeeping
  survive a crash and quietly turn an unsafe solution into a passing one.

Per-task crash depth and operation budgets are declared in each `task.py` and
reported in the output.

## Running it

```bash
uv sync --extra dev          # or: pip install -e ".[dev]"

make validate-grader         # the grader's own test suite
make matrix                  # every task, every solution
make demo                    # the headline result with counterexamples
make reproduce               # all of the above plus the model results, from cache
```

To grade a single file:

```bash
python -m faultline.grade \
  --task tasks/t03_at_least_once_ledger \
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
| `make validate-grader` | ~20 s, free |
| `make matrix` | ~15 s, free |
| `make reproduce` | under a minute, free (replays the cache) |
| Cheap-model smoke test | ~$0.04, DeepSeek V4 Flash, 1 seed (see `docs/findings.md`) |
| Full frontier run | pending OpenRouter credits; see `results/` for the recorded spend |

## Layout

```
faultline/
  world.py        per-attempt scratch state; where crash points are placed
  services/       the simulated outside systems
    store.py        durable key-value store, single-key atomicity only
    gateway.py      payment provider with idempotency keys, timeouts, declines
    bus.py          message broker, at-least-once, no deduplication
    legacy.py       transfer API with no idempotency and no way to query it
    inventory.py    seat holds and releases, both idempotent
  faults.py       what can go wrong in one attempt, and in one trace
  injector.py     adaptive exhaustive fault injection, counterexample minimisation
  selftest.py     the public scenarios a solution author is given
  grade.py        grade one solution against one task
  matrix.py       the grader-validation matrix
  sandbox.py      grade model-written code in its own process
  openrouter.py   cached, cost-accounted model client
  run_eval.py     prompt, repair loop, grade, record
tasks/<task>/
  prompt.md       the contract, as the model sees it
  task.py         entrypoint wiring, invariants, and the task's fault model
  reference.py    known-correct
  alternates/     known-correct, deliberately different shape
  broken/         known-broken, each declaring its expected violation
validation/       the grader's own test suite, plus adversarial inputs
```

## Originality

Built from scratch for the micro1 Eval Hackathon. No code in this repository
predates the event; the repository's first commit is part of the submission.
See `docs/prior-work.md` for the comparison with SWE-bench, Jepsen and
idempotency tutorials, `docs/findings.md` for results, and `docs/video.md`
for the walkthrough script.
