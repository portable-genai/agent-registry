# Contributing to Hrz3 Agent Registry

Thanks for your interest. This is an engineering-portfolio reference repo; the bar is that
every change keeps the offline gate green and respects the hexagonal boundaries.

## Setup

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"     # NO Google Cloud SDK : local/test profile
```

The default profile for development and CI is `local` (SDK-free SQLite catalog). The
managed adapters live behind the `[gcp]` extra and are only needed for the `gcp` profile.

## The gate (must be green before you push)

```bash
ruff check src tests            # lint
ruff format --check src tests   # formatting
mypy src                        # type-check
pytest -q                       # unit + contract
python eval/run_eval.py         # eval gate (catalog-correctness invariants, exit 0)
make demo-selftest              # live walkthrough transcript assertions
make portability-demo           # bounded profile and exit proof
```

All seven must pass. The eval gate scores deterministic registry invariants
(`upsert_idempotency` / `roundtrip_fidelity` / `resolve_accuracy` / `governance_preserved`);
there is no LLM and no Hrz4 promotion split, by design.

## Architecture rules (hexagon)

- **The domain is pure.** No cloud/framework imports in `models.py` / `cards.py`; every
  external edge is a `@runtime_checkable` Protocol port with `local` / `gcp` / `onprem`
  bindings (enforced by `test_contract.py`).
- **GCP imports are lazy.** Inside methods or under `TYPE_CHECKING`, never at module top.
- **One construction convention.** Every adapter is `Adapter(settings: Settings)`.
- **Adding a port:** declare the Protocol, add the three profile bindings in
  `config/settings.yaml`, provide the on-prem stub, and extend the contract test.
- **The shared service layer comes from the commons.** Inbound S2S verification and the
  fail-closed bind guard are `hex-service-kit` (pinned by tag in `pyproject.toml`, exact
  SHA in the lockfiles). Fix shared behaviour there, then bump the pin; do not re-inline
  a copy here.

## Conventions

- Ruff is pinned exactly; formatter output drifts between releases. Bump deliberately.
- Use obviously-fictional identifiers in fixtures and examples.
- No em-dashes in Markdown or commit messages; commits are authored solely by the repo
  owner (no co-author trailers).
