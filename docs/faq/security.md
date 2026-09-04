# Security FAQ

## Can callers assert an actor or ACL in an AgentCard?

No. `agent-registry` verifies the calling workload server-side. AgentCard governance fields describe the
registered agent; they do not authenticate the request.

## Does `agent-registry` enforce every registered scope?

`agent-registry` is the source of truth for agent scopes and lifecycle. Runtime enforcement belongs at the
calling platform boundary, with `agent-guardrail-gateway` handling safety and `agent-observability` retaining evidence.

## Is the on-prem profile permissive?

No. Its adapter raises on every operation until the institution implements and validates it.
