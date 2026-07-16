# RELEASE EVIDENCE - EvalReliability-Mini v0.3 RC1

## Identity and reproduction

- Baseline commit: `7d1d8773a8539705f5d0328f45fcaf00cabdd9d4`
- Release branch: `flagship-v0.3-rc1`
- Resolve the current release commit after checkout with: `git rev-parse HEAD`
- Unique verification command: `python3 run.py`
- CI-equivalent local command: `python3 run.py`
- Local verification status: command returned zero and all 20 tests passed, including four AgentBeats adapter boundary tests.
- Online CI status: a standard GitHub-hosted run completed successfully at `https://github.com/Chilled-watermelon/evalreliability-mini-agentbeats/actions/runs/29512904514`.

The final commit hash is intentionally not embedded in this file because a commit cannot stably contain its own hash.

## Tracked reference evidence

| Evidence | Repository-relative path | SHA-256 |
|---|---|---|
| Raw trace | `artifacts/reference/traces.jsonl` | `9ce3a133b7e27dbd6da16ad52adb76961632f21143daade62a4c717b786090b3` |
| Baseline raw ledger | `artifacts/reference/baseline_ledger.json` | `9bd7d533ba351af2d814e4b9dedd65cc414718f7d423c02a0ac0bdbff2c142c9` |
| Recovery raw ledger | `artifacts/reference/recovery_ledger.json` | `8b32d54e1665b89d9d76d2ce5d23f6cc3655ee10f9467bc3b87e8b8a64d39984` |
| Summary | `artifacts/reference/summary.json` | `b599a70be5620d7c0bf649d971e5631486466c3606985d13e2030b00d85c2ca3` |
| Validator report | `artifacts/reference/validator_report.json` | `edea216d739ef9f12c0aa1ef78c44f59a7476d0c280d6dcdb41189cf29f3c784` |
| Tests snapshot | `artifacts/reference/test-results.txt` | `2481e094f073b9602ea47c596a40ca1c73aa8f200adbfae8522e6c341bf3fdd0` |
| Stable hash manifest | `artifacts/reference/SHA256SUMS` | `61434315c73e02850caacc27ce1a54962da24e0c827a77511eb1d9dcc72021e6` |

Wall-clock timestamps and measured latency are excluded from these deterministic release artifacts. No fixed latency is fabricated in their place.

## Verified metrics

| Metric | Result | Definition and failure condition |
|---|---:|---|
| Trace schema validity | 279/279 | Every raw event satisfies the v0.3-rc1 schema, case-manifest identity, contiguous sequence, and deterministic-field policy; any invalid event fails the run |
| Recovery transition legality | 9/9 | Every faulted recovery case follows inject -> schedule -> resume -> retry -> success with the expected fault node and attempt; any illegal case fails the run |
| Success-path negative control | 6/6 | Three no-fault cases in two modes have no fault or resume event, one graph invocation, expected node order, and correct terminal receipt; any regression fails the run |
| Replay idempotency | 2/2 modes | Baseline and recovery preserve terminal and side-effect counts and skip all 12 completed cases on replay; any count growth or duplicate write fails the run |
| Baseline behavior | 3/12 success, 0/9 recovered | Fixed fail-fast control |
| Recovery behavior | 12/12 success, 9/9 recovered | Fixed checkpoint/resume comparison |
| Automated tests | 20/20 | Core schema, transitions, non-object details, controls, idempotency, artifact validation, plus adapter result, tamper, negative-control, and claim-boundary checks |

## Direct evidence for the ByteIntern Agent framework role

- A real LangGraph 1.1.6 `StateGraph` performs node scheduling and typed state propagation.
- A real `InMemorySaver` performs process-local checkpoint/resume on the same graph thread.
- The raw JSONL trace and validator prove schema-conformant node, fault, resume, retry, side-effect, terminal, and replay-skip events.
- Negative controls and explicit corruption tests turn the artifact into a regression gate rather than a success-rate-only demo.
- The single command regenerates evidence, runs tests, validates outputs, and emits stable hashes.

## Remaining gaps for that role

- No high-performance multi-language Agent framework.
- No distributed or cross-process checkpoint store.
- No production observability, incident response, enterprise authentication, authorization, or governance.
- No multi-Agent orchestration, real LLM, real user traffic, production load, or external adoption.

## Claim and non-claim boundary

This is a **research/portfolio RC** on 12 deterministic synthetic cases using local deterministic tools and a real LangGraph runtime. It uses **no LLM**. The checkpoint is **process-local**. It is **not production-grade** and is not evidence of distributed reliability, a production SLA, enterprise authentication, multi-Agent orchestration, real external adoption, or general Agent reliability.
