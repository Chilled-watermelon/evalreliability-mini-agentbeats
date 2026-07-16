# EvalReliability-Mini v0.2 Real-Framework Report

- Framework: LangGraph 1.1.6 (`StateGraph` + `InMemorySaver`)
- Cases: 12 deterministic synthetic replay cases; same case and fault plan in both modes
- Baseline: 3/12 success; recovery 0/9
- Recovery: 12/12 success; recovery 9/9
- Baseline replay: terminal 12 -> 12; side effects 6 -> 6
- Recovery replay: terminal 12 -> 12; side effects 12 -> 12
- Model/API: no LLM; local deterministic tools; no network, account, key, paid API, or external service

## Claim boundary

Research/portfolio MVP using LangGraph with deterministic synthetic cases and local deterministic tools; not production-grade, not a distributed production system, not a real-SLA or real-model claim, and not evidence that general Agent reliability is solved.
