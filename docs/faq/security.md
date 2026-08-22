# Security FAQ

## Can callers assert an actor or ACL in an AgentCard?

No. Hrz3 verifies the calling workload server-side. AgentCard governance fields describe the
registered agent; they do not authenticate the request.

## Does Hrz3 enforce every registered scope?

Hrz3 is the source of truth for agent scopes and lifecycle. Runtime enforcement belongs at the
calling platform boundary, with Hrz1 handling safety and Hrz5 retaining evidence.

## Is the on-prem profile permissive?

No. Its adapter raises on every operation until the institution implements and validates it.
