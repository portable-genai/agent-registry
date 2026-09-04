"""Presenter-controlled terminal walkthrough of A3 ``agent-registry`` (offline).

Drives the **real** registry through the governed-catalog lifecycle a platform operator
runs every day, entirely on the SDK-free ``local`` profile (SQLite catalog, no Google
Cloud, no API key, no emulator):

1. **Empty catalog, self-describing.** A fresh registry already serves its own AgentCard at
   ``/.well-known/agent-card.json`` (skills: register / resolve / discover). 2. **Register the
   gallery.** Four synthetic Horizon-platform agents publish (upsert) their AgentCards, each
   carrying A3 governance metadata (owner, lifecycle, scopes, protocols). 3. **Discover safely.**
   Governance inventory lists every draft, while public A2A discovery exposes only released agents.
   Direct and passthrough draft resolution both fail closed. 4. **Govern (rule R4 — kill shadow
   AI).** Every external card enters as draft. A dedicated release transition requires an attested
   model-quality-gate EvalRun plus an agent-observability-event reference; an unowned card cannot
   pass that transition. 5. **Reversibility (P-02).** The same command under
   ``AGENT_REGISTRY_PROFILE=onprem`` fails fast (exit 2) with the migration message — the contract
   is identical across profiles.

Two surfaces, same domain: the **CLI** (``agent-registry``) and the **REST API**
(``agent_registry.api.app:app`` via an in-process FastAPI ``TestClient``, so no network /
no running server is needed). The reconciliation here is just catalog CRUD — deterministic
and replayable.

Run it::

    # Guided (waits for Enter between steps):
    PYTHONPATH=src python scripts/registry_demo.py

    # Self-running (no prompts; for recording / CI smoke):
    DEMO_AUTO=1 PYTHONPATH=src python scripts/registry_demo.py [out.json]

It narrates each step, runs a real CLI/API call against an ephemeral in-memory catalog, and
prints the artifact. With an output path it also writes the gallery + transcript JSON. No
browser: this is a platform service (REST + CLI), there is no web UI.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from agent_registry.api.app import create_app
from agent_registry.cli.main import build_parser
from agent_registry.self_card import build_self_card

AUTO = os.environ.get("DEMO_AUTO") == "1"

# ----------------------------------------------------------------------------- #
# Synthetic, FICTIONAL Horizon-platform gallery. None of these are real services.
# Each is a SPEC §6 AgentCard body (A2A discovery contract) plus an additive
# ``governance`` block (A3: owner / lifecycle / scopes / protocols).
# ----------------------------------------------------------------------------- #
SEED_GALLERY: list[dict] = [
    {
        "name": "compliance-advisory",
        "description": "C1 Compliance Assistant — grounded RAG over MAS/HKMA/APRA/FSA rulebooks.",
        "url": "https://compliance-advisory.asia-southeast1.example/a2a",
        "version": "1.2.0",
        "provider": "compliance-advisory",
        "skills": [
            {"id": "answer", "name": "Grounded compliance Q&A", "description": "Cited answers."},
            {"id": "checklist", "name": "Control checklist", "description": "Per use-case."},
        ],
        "governance": {
            "owner": {
                "team": "rsk-compliance",
                "contact": "compliance-eng@horizon.example",
                "organization": "APAC Bank",
            },
            "lifecycle": "draft",
            "scopes": ["a2a:invoke:agent-guardrail-gateway", "mcp:tool:doc_search.query"],
            "protocols": ["a2a", "mcp"],
        },
    },
    {
        "name": "guardrail-gateway",
        "description": "Horizon guardrail gateway — PII screen + redact in front of every model "
        "call.",
        "url": "https://guardrail-gateway.asia-southeast1.example/a2a",
        "version": "0.9.0",
        "provider": "agent-guardrail-gateway",
        "skills": [
            {"id": "screen", "name": "Screen prompt", "description": "Block / allow / redact."},
            {"id": "redact", "name": "Redact PII", "description": "DLP-style de-identification."},
        ],
        "governance": {
            "owner": {
                "team": "platform-trust",
                "contact": "trust-eng@horizon.example",
                "organization": "Horizon Agent Platform",
            },
            "lifecycle": "draft",
            "scopes": ["mcp:tool:dlp.deidentify"],
            "protocols": ["a2a", "mcp"],
        },
    },
    {
        "name": "kyc-doc-extractor",
        "description": "B1 KYC document extractor — Document AI over a customer evidence pack.",
        "url": "https://kyc-doc-extractor.asia-southeast1.example/a2a",
        "version": "2.0.0",
        "provider": "cdd-sow-research",
        "skills": [
            {"id": "extract", "name": "Extract fields", "description": "Cited field extraction."},
        ],
        "governance": {
            "owner": {
                "team": "doc-intelligence",
                "contact": "doc-eng@horizon.example",
                "organization": "APAC Bank",
            },
            "lifecycle": "draft",
            "scopes": ["mcp:tool:documentai.process"],
            "protocols": ["a2a", "mcp"],
        },
    },
    {
        # A deliberately UNOWNED card: the governance signal A3 exists to surface (rule R4).
        "name": "fx-rate-helper",
        "description": "FX rate helper (UNOWNED — stood up by a team without registering an owner).",
        "url": "https://fx-rate-helper.asia-southeast1.example/a2a",
        "version": "0.1.0",
        "provider": "unknown",
        "skills": [
            {"id": "quote", "name": "Quote FX rate", "description": "Indicative spot rate."},
        ],
        # No governance block at all -> owner fields blank, lifecycle defaults to draft.
    },
]

# The agent we will promote using linked model-quality-gate, agent-observability evidence.
BUMP_NAME = "guardrail-gateway"


def _pause(prompt: str) -> None:
    """Wait for the presenter unless DEMO_AUTO=1."""
    if AUTO:
        print(f"\n[auto] {prompt}")
        return
    try:
        input(f"\n>>> {prompt} — press Enter to run...")
    except EOFError:  # piped stdin / non-interactive: behave like AUTO
        print(f"\n[eof] {prompt}")


def _h(title: str) -> None:
    bar = "=" * 78
    print(f"\n{bar}\n{title}\n{bar}")


def _cli(argv: list[str], *, db_path: str, echo: str | None = None) -> int:
    """Run the real ``agent-registry`` CLI in-process against ``db_path`` (local profile).

    The CLI builds its own Container from ``Settings.load()`` (it reads settings.yaml + the
    environment), so we pin ``AGENT_REGISTRY_LOCAL_DB`` to a dedicated temp catalog. Returns the
    exit code; ``SystemExit`` from the CLI boundary is caught so the walkthrough continues.
    """
    print(f"$ {echo or 'agent-registry ' + ' '.join(_quote(a) for a in argv)}")
    prev = os.environ.get("AGENT_REGISTRY_LOCAL_DB")
    os.environ["AGENT_REGISTRY_LOCAL_DB"] = db_path
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except SystemExit as exc:
        return int(exc.code or 0)
    finally:
        if prev is None:
            os.environ.pop("AGENT_REGISTRY_LOCAL_DB", None)
        else:
            os.environ["AGENT_REGISTRY_LOCAL_DB"] = prev


def _quote(arg: str) -> str:
    return f"'{arg}'" if (" " in arg or '"' in arg) else arg


def _show(label: str, obj: object) -> None:
    print(f"\n{label}")
    print(json.dumps(obj, indent=2, sort_keys=True))


def _names_with_lifecycle(cards: list[dict]) -> str:
    return ", ".join(
        f"{c['name']} [{c.get('governance', {}).get('lifecycle', 'draft')}]" for c in cards
    )


def _run_demo(out_path: str | None, demo_db: str) -> None:
    # Pin the whole demo to the offline local profile against ONE ephemeral on-disk catalog
    # (a fresh temp file, deleted at the end). Using a single shared file — for the API's
    # default container AND the CLI's own container — means both surfaces genuinely read and
    # write the same catalog, so the discovery narrative is coherent and deterministic.
    os.environ["AGENT_REGISTRY_PROFILE"] = "local"
    os.environ["AGENT_REGISTRY_LOCAL_DB"] = demo_db

    # The API's dependency container is process-wide and lru_cached; reset it so it binds the
    # local profile + our temp catalog (not whatever a previous import cached), then use the
    # module-level app (create_app() with no args) so the lifespan self-card seed and the
    # request handlers share that one container — no fragile per-app override needed.
    from agent_registry.api import deps

    deps.get_container.cache_clear()
    settings = deps.get_settings()
    cli_db = demo_db  # CLI and API share the same catalog file

    transcript: dict = {"profile": "local", "steps": []}

    _h("A3 agent-registry — governed agent catalog (LOCAL, offline)")
    print(
        f"Profile : local (SQLite catalog, SDK-free; temp file {demo_db})\n"
        "Surfaces: REST API (in-process FastAPI TestClient) + CLI (agent-registry)\n"
        "Data    : synthetic, FICTIONAL Horizon-platform agents\n"
        f"Region  : {settings.region} (configurable; defaults to asia-southeast1)"
    )

    # The in-process client presents itself as a LOOPBACK peer, which is what an offline demo
    # actually is. The app-object exposure guard refuses the zero-secret local posture to any
    # other peer, and TestClient's default peer is the literal host "testclient", which is not a
    # loopback address.
    with TestClient(create_app(), client=("127.0.0.1", 50000)) as api:
        # The lifespan startup hook owns the reserved registry self-card. External callers
        # cannot create or replace it.
        self_card = build_self_card(settings)

        # ---- Step 1: empty catalog is already self-describing --------------------- #
        _h("1. A fresh registry is self-describing (A2A well-known card)")
        print(
            "Even before any agent registers, A3 serves its OWN AgentCard at the A2A "
            "well-known path,\nso an orchestrator can find 'the place to find agents'."
        )
        _pause("GET /.well-known/agent-card.json")
        print("\n$ curl -s localhost:8083/.well-known/agent-card.json")
        well_known = api.get("/.well-known/agent-card.json").json()
        _show("-> registry self-card:", well_known)
        print(
            "\nSkills advertised: "
            + ", ".join(s["id"] for s in well_known["skills"])
            + f"   (lifecycle={well_known['governance']['lifecycle']})"
        )
        transcript["steps"].append({"step": "well_known", "card": well_known})

        # ---- Step 2: register the gallery (CLI + REST) ---------------------------- #
        _h("2. Register the gallery — publish four agents (idempotent upsert)")
        print(
            "Agents publish their AgentCard on deploy. The CLI and the REST API are two\n"
            "surfaces over the SAME catalog and the SAME wire shape. We register the first\n"
            "agent via the CLI, then publish the rest via REST — into the one catalog."
        )
        first, *rest = SEED_GALLERY

        _pause(f"register '{first['name']}' via the agent-registry CLI")
        cli_exit = _cli(["register", "--card", json.dumps(first)], db_path=cli_db)

        # The CLI just wrote to the shared catalog; publish the remaining agents over REST.
        # Same catalog, same wire shape — the only difference is the surface.
        http_statuses = []
        for card in rest:
            _pause(f"POST /v1/agents  ({card['name']})")
            print(
                f'\n$ curl -X POST localhost:8083/v1/agents -d \'{{"name":"{card["name"]}", ...}}\''
            )
            resp = api.post("/v1/agents", json=card)
            http_statuses.append(resp.status_code)
            owner = card.get("governance", {}).get("owner", {}).get("team") or "(UNOWNED)"
            print(f"-> HTTP {resp.status_code}   owner.team={owner}")

        registered_gallery = api.get("/v1/governance/agents").json()
        registered_names = sorted(
            card["name"] for card in registered_gallery if card["name"] != self_card.name
        )
        transcript["steps"].append(
            {
                "step": "register",
                "cli_exit": cli_exit,
                "http_statuses": http_statuses,
                "observed_count": len(registered_names),
                "observed_names": registered_names,
            }
        )

        # ---- Step 3: discover ----------------------------------------------------- #
        _h("3. Discover safely — drafts stay in governance inventory only")
        _pause("compare governance inventory with public A2A discovery")
        print("\n$ curl -s localhost:8083/v1/governance/agents")
        governance_gallery = api.get("/v1/governance/agents").json()
        print(
            f"\n-> governance sees {len(governance_gallery)} agent(s): "
            f"{_names_with_lifecycle(governance_gallery)}"
        )
        print("\n$ curl -s localhost:8083/v1/agents")
        gallery = api.get("/v1/agents").json()
        print(
            f"\n-> public discovery sees {len(gallery)} released agent(s): {_names_with_lifecycle(gallery)}"
        )
        unowned = [c["name"] for c in governance_gallery if not c["governance"]["owner"]["team"]]
        print(
            "   GOVERNANCE SIGNAL (rule R4): unowned card(s) -> "
            + (", ".join(unowned) if unowned else "none")
            + "   (a platform owner triages these)"
        )

        _pause(f"verify draft '{first['name']}' cannot be resolved publicly")
        print(f"\n$ curl -s localhost:8083/v1/agents/{first['name']}")
        draft_lookup = api.get(f"/v1/agents/{first['name']}")
        draft_passthrough = api.get(f"/v1/agents/{first['name']}/card")
        print(
            f"\n-> direct HTTP {draft_lookup.status_code}; A2A passthrough HTTP "
            f"{draft_passthrough.status_code} (both fail closed)"
        )
        transcript["steps"].append(
            {
                "step": "discover",
                "names": [c["name"] for c in gallery],
                "governance_names": [c["name"] for c in governance_gallery],
                "draft_lookup_status": draft_lookup.status_code,
                "draft_a2a_status": draft_passthrough.status_code,
            }
        )

        # ---- Step 4: govern — evidence-gated release ------------------------------ #
        _h("4. Govern — simulate release review without production attestation")
        release_request = {
            "eval_run_id": "eval-demo-guardrail-gateway-0.9.0",
            "audit_event_id": "audit-demo-guardrail-gateway-release",
        }
        _pause(f"simulate release review for '{BUMP_NAME}' with laptop-only evidence")
        release = api.post(
            f"/v1/agents/{BUMP_NAME}/release",
            json=release_request,
        )
        if release.status_code != 200:
            raise RuntimeError(
                f"demo release failed with HTTP {release.status_code}: {release.text}"
            )
        card_now = release.json()
        count_after = len(api.get("/v1/agents").json())
        governance_count_after = len(api.get("/v1/governance/agents").json())
        print(
            f"\n-> HTTP {release.status_code}; '{BUMP_NAME}' lifecycle is now "
            f"'{card_now['governance']['lifecycle']}'."
            f"\n   EvalRun={release_request['eval_run_id']}; "
            f"audit={release_request['audit_event_id']}."
            "\n   Laptop evidence is demo-only; the card remains a non-discoverable draft."
        )
        transcript["steps"].append(
            {
                "step": "govern",
                "name": card_now["name"],
                "count_after": count_after,
                "governance_count_after": governance_count_after,
                "lifecycle_after": card_now["governance"]["lifecycle"],
                "eval_run_id": card_now["governance"]["release_evidence"]["eval_run_id"],
                "audit_event_id": card_now["governance"]["release_evidence"]["audit_event_id"],
            }
        )

        # ---- Step 5: reversibility — onprem fail-fast ----------------------------- #
        _h("5. Reversibility (P-02) — the same command fails fast under onprem")
        print(
            "Switching AGENT_REGISTRY_PROFILE=onprem rebinds the port to the Google\n"
            "Distributed Cloud migration placeholder: every method raises, and the CLI\n"
            "turns that into a clean exit 2 (no traceback). The contract is identical."
        )
        _pause("AGENT_REGISTRY_PROFILE=onprem agent-registry list   (expect exit 2)")
        print()
        os.environ["AGENT_REGISTRY_PROFILE"] = "onprem"
        code = _cli(
            ["list"], db_path=cli_db, echo="AGENT_REGISTRY_PROFILE=onprem agent-registry list"
        )
        os.environ["AGENT_REGISTRY_PROFILE"] = "local"
        print(f"-> exit={code}  (2 = profile cannot satisfy the command, as designed)")
        transcript["steps"].append({"step": "onprem_failfast", "exit": code})

        # Capture the final gallery for the transcript artifact.
        transcript["final_gallery"] = api.get("/v1/governance/agents").json()

    _h("Done — talking points")
    print(
        "- One catalog, three profiles: identical AgentCard contract across local / gcp / "
        "onprem.\n"
        "- New cards are drafts; activation requires an attested model-quality-gate EvalRun and "
        "agent-observability link.\n"
        "- Governance is additive: a plain A2A peer reads six fields; the platform relies on\n"
        "  owner / lifecycle / scopes to kill shadow AI (R4) and enforce least privilege.\n"
        "- Everything above ran offline on the local SQLite catalog — no GCP, no API key."
    )

    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(transcript, fh, indent=2)
        print(f"\nWrote gallery + transcript JSON -> {out_path}")


def main(out_path: str | None) -> None:
    previous_profile = os.environ.get("AGENT_REGISTRY_PROFILE")
    previous_db = os.environ.get("AGENT_REGISTRY_LOCAL_DB")
    try:
        with tempfile.TemporaryDirectory(prefix="hrz3-registry-demo-") as directory:
            _run_demo(out_path, str(Path(directory) / "registry.db"))
    finally:
        if previous_profile is None:
            os.environ.pop("AGENT_REGISTRY_PROFILE", None)
        else:
            os.environ["AGENT_REGISTRY_PROFILE"] = previous_profile
        if previous_db is None:
            os.environ.pop("AGENT_REGISTRY_LOCAL_DB", None)
        else:
            os.environ["AGENT_REGISTRY_LOCAL_DB"] = previous_db
        from agent_registry.api import deps

        deps.get_container.cache_clear()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
