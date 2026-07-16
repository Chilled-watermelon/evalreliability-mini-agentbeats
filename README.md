# EvalReliability-Mini v0.3 RC1

A deterministic research/portfolio release candidate for verifying recovery traces from a real **LangGraph 1.1.6** `StateGraph` workflow.

## The 30-second counterexample

An Agent tool writes a durable side effect, then the process is interrupted before the framework checkpoints node completion. A naive retry may report final success while writing the side effect twice, resuming in the wrong order, or silently regressing a no-fault path. A success rate alone cannot distinguish a legal recovery from a lucky terminal result.

## Single contribution

This RC adds one machine-verifiable gate over the existing real LangGraph execution path:

> Validate every trace event against a deterministic schema, prove legal fault-to-recovery transitions, keep no-fault paths as negative controls, and reject terminal or side-effect duplication on completed-case replay.

It does not add a second Agent framework, change the 12-case plan, or inflate the fixed result set.

## Quickstart

```bash
python3 run.py
```

The command runs the experiment, rebuilds the validator report from raw traces and ledgers, runs the complete `unittest` suite, validates all generated artifacts, and writes a stable `SHA256SUMS`. It exits non-zero on an experiment, schema, transition, regression, idempotency, artifact, or test failure.

Live output is regenerated under ignored `artifacts/live/`. The tracked release snapshot is under `artifacts/reference/`.

The repository uses Python's standard library plus the pinned `langgraph==1.1.6` dependency in `requirements.txt`. On the original verification machine, `run.py` may re-execute with an already-installed local Python runtime when the shell Python cannot import LangGraph. It does not install packages, alter `PYTHONPATH`, use a key, or access the network at runtime.

## Reference results

| Gate | Result | Denominator and failure condition |
|---|---:|---|
| Baseline success | 3/12 | Fails if the fixed fail-fast behavior changes |
| Recovery success | 12/12 | Fails if any fixed case misses its expected receipt |
| Fault recovery | 9/9 | Fails if any faulted recovery case does not recover |
| Trace schema validity | 279/279 | Fails on a missing/type-invalid field, manifest mismatch, unstable timing field, or sequence gap |
| Recovery transition legality | 9/9 | Fails unless inject -> schedule -> resume -> retry -> success is legal for every faulted case |
| Success-path negative control | 6/6 | Three no-fault cases x two modes; fails on any fault/resume event or terminal regression |
| Replay idempotency | 2/2 modes | Fails if terminal or side-effect counts grow, a completed case re-executes, or a side effect is duplicated |
| Automated tests | 16/16 | Fails on any `unittest` failure |

These values apply only to the fixed deterministic synthetic plan in this repository.

## Real framework path

`LangGraphEvalRunner` builds and compiles this workflow with a real `StateGraph`:

```text
START -> fetch -> transform -> commit -> END
```

LangGraph schedules nodes, carries typed state, checkpoints through `InMemorySaver`, and resumes a failed thread with `graph.invoke(None, config)`. The nodes call local deterministic fetch, transform, and commit tools.

For interruption cases, `commit` writes once and fails before LangGraph checkpoints completion. Recovery re-enters `commit`; the local idempotency key returns the existing receipt and records a reuse instead of another write.

## Architecture and data flow

```text
fixed case manifest (12 cases, 3 faults)
                    |
                    v
     LangGraph StateGraph + InMemorySaver
          | raw trace        | local ledger
          +------------------+
                    |
                    v
       schema + transition validator
                    |
          +---------+---------+
          v                   v
      summary.json      validator_report.json
          |                   |
          +---------+---------+
                    v
          tests snapshot + SHA256SUMS
```

## Fixed cases and faults

Baseline and recovery use the same 12 deterministic synthetic cases and fault plan.

| Cases | Fault | Injection point | Count |
|---|---|---|---:|
| `case-001` to `case-003` | none | no injection | 3 |
| `case-004` to `case-006` | timeout | before `transform`, attempt 1 | 3 |
| `case-007` to `case-009` | tool error | before `fetch`, attempt 1 | 3 |
| `case-010` to `case-012` | interruption | after durable `commit` side effect, attempt 1 | 3 |

- **baseline:** one graph invocation; an injected fault becomes a failed terminal result.
- **recovery:** one resume using the same LangGraph thread and process-local checkpoint.

## Validator definitions

- **Schema valid rate:** trace events satisfying required fields, types, case-manifest identity, contiguous sequence, and deterministic-field policy / all trace events.
- **Recovery transition legal rate:** faulted recovery cases with one legal inject -> schedule -> resume -> retry -> success chain / all faulted recovery cases.
- **Success-path zero regression:** no-fault paths with no fault or resume event, one graph invocation, expected node order, and correct terminal receipt / all no-fault paths in both modes.
- **Replay idempotency:** modes preserving terminal and side-effect counts while every completed case produces one replay-skip event / baseline and recovery.

Wall-clock timestamps and measured latency are intentionally excluded from release evidence because they would make hashes machine-dependent. The project does not replace them with fabricated fixed timings.

## Artifacts

Each output directory contains:

- `traces.jsonl`: raw LangGraph node, fault, resume, side-effect, terminal, and replay-skip events.
- `validator_report.json`: schema, transition, negative-control, fail-fast, and idempotency checks with per-case outcomes.
- `summary.json`: result counts plus the validator metrics.
- `baseline_ledger.json`, `recovery_ledger.json`: attempts, invocations, resumes, terminal records, and idempotent side effects.
- `case_manifest.json`, `feasibility.json`: fixed plan and real-framework runtime probe.
- `report.md`, `test-results.txt`, `SHA256SUMS`: concise report, stable test snapshot, and hashes for every other artifact.

## CI and local equivalent

The workflow in `.github/workflows/ci.yml` installs only the pinned minimal requirement and runs:

```bash
python3 run.py
```

The CI-equivalent local command has been verified. No online CI run or badge is claimed in this RC.

## Claim boundary

This is a **research/portfolio RC**, not production-grade infrastructure.

- No LLM is used; tools and cases are local and deterministic.
- `InMemorySaver` is process-local and does not survive process termination.
- The JSON ledger is a local evidence mechanism, not a transactional database or distributed checkpoint store.
- The RC does not demonstrate distributed reliability, production SLA, enterprise authentication, concurrency safety, multi-Agent orchestration, real-model behavior, real user traffic, or external adoption.
- `12/12`, `9/9`, `279/279`, `6/6`, and `2/2` apply only to this fixed deterministic synthetic plan.

## License

MIT. See `LICENSE`.
