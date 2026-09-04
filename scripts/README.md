# Demo scripts - `agent-registry` governed agent registry

These scripts are SDK-free and run against the offline `local` stack (SQLite catalog, no
Google Cloud, no API key, no emulator). There is **no web UI**: `agent-registry` is a platform service
(REST API + CLI), so the demo is a terminal walkthrough plus raw curl/CLI commands.

Run from the repo root with the package on the path:

```bash
export PYTHONPATH=src
```

| Script | What it does |
|--------|--------------|
| `registry_demo.py` | Presenter-controlled terminal walkthrough of the real registry: serve the self-card, register a synthetic Horizon-platform gallery (CLI + REST), discover, govern (version-bump upsert + retire + the unowned-card R4 signal), and the onprem fail-fast. Offline; deterministic. |
| `demo_selftest.py` | Runs the walkthrough unattended and validates every live transcript outcome. |
| `portability_demo.py` | Bounded proof of exact profiles, deterministic local behavior, managed construction and fail-fast exit seams. |
| `rename_fork.py` | Dry-run-first mechanical rename for an institutional fork. |
| `lock.py` | Compiles both lockfiles and puts the header back, because `uv pip compile` REPLACES the output file: it writes its own two-line provenance comment and destroys the `tag = commit` map the pin tests check against. `make lock` runs this rather than uv directly. |

## Guided, presenter-controlled walkthrough (recommended)

The script narrates each step and **waits for you to press Enter** before running the real
CLI/API call, so you control the pace.

```bash
PYTHONPATH=src python scripts/registry_demo.py
```

It steps through, pausing for Enter each time:

1. **Self-describing registry** - `GET /.well-known/agent-card.json` returns `agent-registry`'s own card
   (skills: register / resolve / discover) before any agent registers.
2. **Register the gallery** - publish four FICTIONAL agents (one via the `agent-registry`
   CLI, the rest via `POST /v1/agents`), each carrying `agent-registry` governance metadata.
3. **Discover** - `GET /v1/agents` lists the gallery; `GET /v1/agents/{name}` and the A2A
   `/card` passthrough resolve a single agent.
4. **Govern (rule R4)** - re-publishing is an idempotent upsert keyed on `name` (version
   bumps in place, no duplicate row); retiring an agent (`lifecycle -> retired`) drops it
   from production discovery while it stays resolvable; the **unowned** card is the
   shadow-AI signal a platform owner triages.
5. **Reversibility (P-02)** - the same command under `AGENT_REGISTRY_PROFILE=onprem` fails
   fast (exit 2) with the migration message.

The REST calls run against an **in-process FastAPI `TestClient`** (no network, no running
server) and the CLI runs in-process too. Both share one ephemeral temp SQLite catalog
(`$TMPDIR/hrz-registry-demo.db`), removed when the script exits - nothing touches your real
`~/.agent_registry/local.db`.

## Self-running (recording / smoke)

Set `DEMO_AUTO=1` to advance without prompts, and pass an output path to also write the
gallery + transcript JSON:

```bash
make demo-selftest
make portability-demo
```

`make demo` runs the guided walkthrough (`AGENT_REGISTRY_PROFILE=local PYTHONPATH=src python
scripts/registry_demo.py`).

## Environment overrides

| Var | Default | Purpose |
|-----|---------|---------|
| `DEMO_AUTO=1` | off | don't wait for Enter - advance automatically (self-test / recording) |
| `AGENT_REGISTRY_PROFILE` | `local` | the script forces `local`; it flips to `onprem` only for the step-5 fail-fast, then back |

> The walkthrough embeds long AgentCard JSON and narration, so its E501 exception remains.
> CI directly lints and executes the self-test, portability proof and rename utility.
