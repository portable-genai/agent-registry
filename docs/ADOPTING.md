# Adopting Hrz3

Hrz3 can be consumed as the shared platform registry or forked when an institution needs
independent ownership, naming or release cadence. Prefer configuration and adapter replacement
over changing the AgentCard contract.

| Mode | Use when | Institution-owned changes |
|---|---|---|
| Consume Hrz3 | The shared REST and AgentCard contract fits | S2S identity, managed store, Terraform values |
| Fork Hrz3 | Registry ownership or release cadence must be independent | Rename, adapters, deployment and regulator crosswalk |
| Implement the port | An existing catalog remains authoritative | New `AgentRegistryPort` adapter and explicit profile binding |

Keep `models.py`, `cards.py`, `ports/`, `schemas.py` and the HTTP routes stable. Institution-owned
surfaces are settings, adapters, identity policy, managed data infrastructure and the compliance
crosswalk. Hrz3 owns agent identity, ownership, scopes and lifecycle metadata. Hrz1 owns runtime
safety, Hrz2 governed knowledge, Hrz4 promotion, Hrz5 audit and Hrz7 human decisions.

## Preview and apply a rename

```bash
python scripts/rename_fork.py \
  --package bank_agent_catalog \
  --cli bank-agent-catalog \
  --env-prefix BANK_CATALOG \
  --resource bank-agent-catalog \
  --include-docs --dry-run

python scripts/rename_fork.py \
  --package bank_agent_catalog \
  --cli bank-agent-catalog \
  --env-prefix BANK_CATALOG \
  --resource bank-agent-catalog \
  --include-docs --yes
```

The utility checks the package destination before any write and previews by default. The CLI and
resource stems must match because both use the upstream `agent-registry` name. The utility and its
unit test retain upstream names so the post-rename regression gate remains meaningful. Recreate the
editable environment after applying, then run `make check`.

## Upstream and exit discipline

Add this repository as an `upstream` remote and integrate one released version at a time. Resolve
contract files before institution-owned adapters and never overwrite local identity, database or
infrastructure policy. An on-prem claim requires a working adapter, export/import reconciliation,
backup/restore proof and the complete contract/eval/portability gate. The current on-prem adapter
is intentionally fail-fast.
