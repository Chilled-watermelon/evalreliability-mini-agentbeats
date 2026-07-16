# RELEASE EVIDENCE - AgentBeats Adapter

## Scope and provenance

- RC baseline commit: `746794a2f20753dcf94e3ce3f7c7c11b60ae6eb9`
- Resolve the checked-out adapter commit with: `git rev-parse HEAD`
- Official Green contract source: `https://github.com/RDI-Foundation/green-agent-template`
- Official Purple contract source: `https://github.com/RDI-Foundation/agent-template`
- Protocol implementation: `a2a-sdk[http-server]==0.3.20`
- Unique local A2A verification command: `uv run --locked --project agentbeats python run_agentbeats.py`
- Fresh Docker command: `uv run --locked --project agentbeats python -m agentbeats_adapter.docker_assessment`

## Machine results

| Gate | Result |
|---|---:|
| Core and adapter tests | 20/20 |
| Positive fresh-container assessments | 2/2 byte-identical |
| Baseline | 3/12 success, 0/9 recovered |
| Recovery | 12/12 success, 9/9 recovered |
| Trace schema | 279/279 |
| Recovery transition legality | 9/9 |
| Success-path negative controls | 6/6 |
| Replay idempotency | 2/2 modes |
| Corrupted `details` negative control | `FAIL`, 278/279 valid events |

The tracked AgentBeats evidence is under `artifacts/agentbeats/reference/`. `SHA256SUMS` is the source of truth for individual file hashes. Live local and Docker reruns go to ignored sibling directories.

## Adapter flow

```text
AgentBeats assessment request
        |
        v
Green A2A AgentExecutor ----A2A----> Purple deterministic subject
        |                                   |
        |                         unchanged 12-case RC run
        |                                   |
        +<-------- raw JSON artifacts -------+
        |
        v
original trace validator -> structured result JSON
```

The Purple subject executes the unchanged LangGraph plan in a fresh temporary directory. The Green evaluator verifies every artifact hash, rebuilds the original validation report, checks the fixed metric schema and claim boundary, then emits a structured A2A `DataPart`.

## Container evidence

- Platform: `linux/amd64`, CPU only.
- Green local image ID: `sha256:e3e958f90734953cea315c335087034d1ce13e0c536c2138e554d748bcd205df`
- Purple local image ID: `sha256:7eb844f697c20825129dba749fc10df7773cd37f86dc960a53e4d30484f3fffd`
- Positive result SHA-256: `e1c65eddc36e9e81527315a5cb28be49ee9a6a5791eede0136b0260f11119e44`
- Fresh-state evidence: three separate container/network lifecycles; two positive runs are byte-identical and the third is the required failure control.

Local image IDs are not registry publication digests. Public repository, Actions, GHCR, result JSON, and AgentBeats URLs are evidence only after those resources actually exist and are independently openable.

## Public external evidence

- Repository: `https://github.com/Chilled-watermelon/evalreliability-mini-agentbeats`
- Verified adapter commit: `https://github.com/Chilled-watermelon/evalreliability-mini-agentbeats/commit/f844a2df96ef89e810463fe76f50c192394a5a1d`
- Successful standard GitHub Actions run: `https://github.com/Chilled-watermelon/evalreliability-mini-agentbeats/actions/runs/29512904514`
- Positive result JSON: `https://raw.githubusercontent.com/Chilled-watermelon/evalreliability-mini-agentbeats/f844a2df96ef89e810463fe76f50c192394a5a1d/artifacts/agentbeats/reference/positive-run-1.json`
- Green image: `ghcr.io/chilled-watermelon/evalreliability-mini-agentbeats/green@sha256:9e9093ab86a28f392bbe4ee23b6aaf1f75a29877846b64a37853271b174d03e9`
- Purple image: `ghcr.io/chilled-watermelon/evalreliability-mini-agentbeats/purple@sha256:b33738e739d49cc3aa0c8a0fc594412310962a4e17a838f9b9437348542eee48`
- Anonymous pull check: passed for both digest-pinned images in an empty Docker credential directory.
- Online result comparison: positive runs and the negative control are byte-identical to the tracked local reference; the positive result SHA-256 remains `e1c65eddc36e9e81527315a5cb28be49ee9a6a5791eede0136b0260f11119e44`.

No AgentBeats completed assessment or leaderboard record is claimed in this file unless a separately linked platform record exists.

## Claim and non-claim boundary

This is a **research/portfolio RC** using **no LLM**, local deterministic tools, 12 deterministic synthetic cases, and a process-local `InMemorySaver` checkpoint. It is **not production-grade**. It does not prove distributed reliability, a production SLA, enterprise authentication, real-LLM behavior, multi-Agent reliability, real user traffic, or external adoption. The Green/Purple split proves compatibility with the benchmark transport contract, not a general multi-Agent capability.
