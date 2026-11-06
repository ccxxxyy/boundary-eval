# Originality and prior work

This repository is original work built for the micro1 Eval Hackathon.
No code in it predates the event. The first commit is part of the
submission.

## What this eval is not

It is not a copy of an existing coding benchmark, and it is not a
repackaging of a known leaderboard.

- **SWE-bench / HumanEval / MBPP** grade functional correctness against
  unit tests. FaultLine's public self-check is deliberately that kind of
  test, and it is not the grade. The grade is whether the same code still
  holds when the process is killed between two durable writes.
- **Jepsen** tests real distributed systems with wall-clock time, real
  networks and real disks. FaultLine tests a *function a model just
  wrote*, inside a simulated world with no clock, no network and no
  filesystem, so a failing trace is a counterexample that replays
  identically.
- **Chaos engineering / fault-injection frameworks** (Chaos Monkey,
  Toxiproxy, litmus) operate on running services. They are not an eval
  of whether a language model can write crash-safe business logic.
- **Idempotency-key / outbox tutorials** describe the patterns. They do
  not measure whether a model will apply them when the prompt describes
  the failure modes and a public test suite looks green.

## What it draws on, and what is new

The *phenomena* are well known: at-least-once delivery, ambiguous
timeouts, the dual-write problem, saga compensation, fencing. They show
up in Kleppmann, in Stripe's idempotency-key documentation, and in every
serious post-mortem of a payment or queue consumer.

What is new is the measurement:

1. A simulated world whose crash points are placed only before mutating
   operations, so the search is exhaustive for a declared crash depth
   without wasting schedules that cannot be distinguished.
2. Per-attempt re-instantiation of the solution module, so in-memory
   state cannot secretly survive a crash.
3. A public self-check derived from the same fault-model declaration the
   prompt discloses, with a repair loop that gives the model what a
   developer gets, and a hidden exhaustive search whose output is never
   fed back.
4. A grader that is itself under test: no false passes, no false
   failures, failing for the declared reason, shape-independence,
   determinism, and containment of adversarial input.

The claim is not "nobody has thought about exactly-once semantics". The
claim is that frontier models still write the code that *looks* like
exactly-once semantics and is not, and that this can be shown with a
grader a judge can re-run in a clean environment for free.
