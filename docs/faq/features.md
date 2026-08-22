# Features FAQ

## What does Hrz3 own?

It owns agent discovery metadata: stable names, owners, lifecycle, scopes, protocols, skills and
endpoints. It does not proxy MCP or A2A task traffic.

## Which adjacent systems own runtime controls?

Hrz1 owns safety, Hrz2 knowledge, Hrz4 promotion, Hrz5 audit and Hrz7 manual review. Hrz3 records
the agent metadata those controls use.

## Are retired agents deleted?

No. They remain resolvable for governance and graceful degradation while discovery clients can
exclude them from production routing.
