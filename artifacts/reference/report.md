# EvalReliability-Mini v0.3 RC1 Verification Report

- Framework: LangGraph 1.1.6 (`StateGraph` + `InMemorySaver`)
- Cases: 12 deterministic synthetic replay cases; same case and fault plan in both modes
- Baseline: 3/12 success; recovery 0/9
- Recovery: 12/12 success; recovery 9/9
- Trace schema: 279/279 valid
- Recovery transitions: 9/9 legal
- Success-path negative controls: 6/6 zero-regression
- Replay idempotency: 2/2 modes preserve terminal and side-effect counts
- Baseline replay: terminal 12 -> 12; side effects 6 -> 6
- Recovery replay: terminal 12 -> 12; side effects 12 -> 12
- Model/API: no LLM; local deterministic tools; no network, account, key, paid API, or external service

## Claim boundary

Research/portfolio RC using real LangGraph with deterministic synthetic cases, local deterministic tools, no LLM, and a process-local checkpoint; not production-grade and not evidence of distributed reliability, a production SLA, enterprise authentication, multi-Agent orchestration, real external adoption, or general Agent reliability.
