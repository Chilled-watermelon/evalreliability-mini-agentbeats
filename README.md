# EvalReliability-Mini v0.3 RC1 + AgentBeats Adapter

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

## AgentBeats official-A2A evidence

The adapter follows the official [AgentBeats Green Agent template](https://github.com/RDI-Foundation/green-agent-template) and [Purple Agent template](https://github.com/RDI-Foundation/agent-template): an A2A `AgentExecutor` receives the platform request, the Green evaluator calls the Purple subject through its advertised Agent Card, and both return structured `DataPart` artifacts. The checked-in Amber manifests declare one required `subject` A2A slot and no secret configuration.

Install the adapter's exact lock and run the core RC plus two positive A2A assessments and one schema-corruption negative control:

```bash
uv sync --locked --project agentbeats
uv run --locked --project agentbeats python run_agentbeats.py
```

The positive assessments must be byte-identical and retain the fixed RC metrics. The negative assessment changes one `graph_invoked.details` object to an array and must return `FAIL` with `278/279` schema-valid events rather than throw an exception.

Build the CPU-only `linux/amd64` images and repeat the assessment in three independent fresh container/network states:

```bash
docker build --platform linux/amd64 -f agentbeats/Dockerfile.green -t evalreliability-agentbeats-green:local .
docker build --platform linux/amd64 -f agentbeats/Dockerfile.purple -t evalreliability-agentbeats-purple:local .
uv run --locked --project agentbeats python -m agentbeats_adapter.docker_assessment
```

The image base is pinned by digest, runtime dependencies are locked in `agentbeats/uv.lock`, the containers run as an unprivileged user, and no key or paid API is used. Setup and image build may download the declared public dependencies; assessment runtime only uses local A2A traffic and deterministic tools.

### Public verification evidence

- [Public repository](https://github.com/Chilled-watermelon/evalreliability-mini-agentbeats)
- [Verified adapter commit](https://github.com/Chilled-watermelon/evalreliability-mini-agentbeats/commit/f844a2df96ef89e810463fe76f50c192394a5a1d)
- [Successful standard GitHub Actions run](https://github.com/Chilled-watermelon/evalreliability-mini-agentbeats/actions/runs/29512904514)
- [Machine-readable positive result JSON](https://raw.githubusercontent.com/Chilled-watermelon/evalreliability-mini-agentbeats/f844a2df96ef89e810463fe76f50c192394a5a1d/artifacts/agentbeats/reference/positive-run-1.json)
- Green image: `ghcr.io/chilled-watermelon/evalreliability-mini-agentbeats/green@sha256:9e9093ab86a28f392bbe4ee23b6aaf1f75a29877846b64a37853271b174d03e9`
- Purple image: `ghcr.io/chilled-watermelon/evalreliability-mini-agentbeats/purple@sha256:b33738e739d49cc3aa0c8a0fc594412310962a4e17a838f9b9437348542eee48`

The Actions run and anonymously pullable images prove public reproducibility of this fixed adapter assessment. They do not imply AgentBeats leaderboard completion, third-party adoption, or production readiness.

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
| Automated tests | 20/20 | Fails on any `unittest` failure; includes four adapter/schema boundary tests |

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
- `artifacts/agentbeats/reference/positive-run-1.json`: tracked positive Green result from a fresh Docker assessment.
- `artifacts/agentbeats/reference/negative-details-array.json`: tracked machine-readable negative result.
- `artifacts/agentbeats/reference/assessment-summary.json`, `SHA256SUMS`: repeatability verdict, image IDs, and evidence hashes.

## CI and local equivalent

The standard `ubuntu-latest` workflow runs the locked local A2A command, builds both `linux/amd64` images, performs all three fresh-state Docker assessments, uploads the machine JSON, and publishes commit-addressed GHCR images only after verification. It does not enumerate repository secrets, use a larger runner, call an LLM, or use a paid API.

The linked public Actions run completed successfully on a standard GitHub-hosted runner. No result is called AgentBeats-completed or leaderboard-listed unless the platform itself exposes that record.

## Claim boundary

This is a **research/portfolio RC**, not production-grade infrastructure.

- No LLM is used; tools and cases are local and deterministic.
- `InMemorySaver` is process-local and does not survive process termination.
- The JSON ledger is a local evidence mechanism, not a transactional database or distributed checkpoint store.
- The RC does not demonstrate distributed reliability, production SLA, enterprise authentication, concurrency safety, multi-Agent orchestration, real-model behavior, real user traffic, or external adoption.
- `12/12`, `9/9`, `279/279`, `6/6`, and `2/2` apply only to this fixed deterministic synthetic plan.
- The Green/Purple split is a benchmark transport boundary, not evidence of a general multi-Agent system.

## License

MIT. See `LICENSE`.
