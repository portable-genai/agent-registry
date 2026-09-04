# Features FAQ

## What does `agent-registry` own?

It owns agent discovery metadata: stable names, owners, lifecycle, scopes, protocols, skills and
endpoints. It does not proxy MCP or A2A task traffic.

## Which adjacent systems own runtime controls?

`agent-guardrail-gateway` owns safety, `enterprise-knowledge-base` knowledge, `model-quality-gate` promotion, `agent-observability` and `human-review-console` manual review. `agent-registry` records
the agent metadata those controls use.

## Are retired agents deleted?

No. They remain resolvable for governance and graceful degradation while discovery clients can
exclude them from production routing.
