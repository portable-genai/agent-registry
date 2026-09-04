from __future__ import annotations

import copy
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPT = Path(__file__).parents[1] / "scripts" / "demo_selftest.py"
_SPEC = importlib.util.spec_from_file_location("demo_selftest", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def _card(name: str, *, lifecycle: str = "active", owner: str = "team") -> dict[str, Any]:
    card = {
        "name": name,
        "governance": {"lifecycle": lifecycle, "owner": {"team": owner}},
    }
    if name == "guardrail-gateway":
        card["governance"]["release_evidence"] = {"assurance": "demo-only"}
    return card


def _valid_evidence() -> dict[str, Any]:
    registered = [
        "compliance-advisory",
        "fx-rate-helper",
        "guardrail-gateway",
        "kyc-doc-extractor",
    ]
    final_names = ["agent-registry", *registered]
    return {
        "profile": "local",
        "steps": [
            {
                "step": "well_known",
                "card": {
                    "name": "agent-registry",
                    "skills": [{"id": item} for item in ("register", "resolve", "discover")],
                },
            },
            {
                "step": "register",
                "cli_exit": 0,
                "http_statuses": [201, 201, 201],
                "observed_count": 4,
                "observed_names": registered,
            },
            {
                "step": "discover",
                "names": ["agent-registry"],
                "governance_names": final_names,
                "draft_lookup_status": 404,
                "draft_a2a_status": 404,
            },
            {
                "step": "govern",
                "name": "guardrail-gateway",
                "count_after": 1,
                "governance_count_after": 5,
                "lifecycle_after": "draft",
                "eval_run_id": "eval-demo-guardrail-gateway-0.9.0",
                "audit_event_id": "audit-demo-guardrail-gateway-release",
            },
            {"step": "onprem_failfast", "exit": 2},
        ],
        "final_gallery": [
            _card("agent-registry"),
            _card("compliance-advisory"),
            _card("fx-rate-helper", owner=""),
            _card("guardrail-gateway", lifecycle="draft"),
            _card("kyc-doc-extractor"),
        ],
    }


def test_valid_evidence_passes() -> None:
    _MODULE.validate_evidence(_valid_evidence())


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_final_name",
        "duplicate_discovery_name",
        "stale_lifecycle",
        "wrong_post_upsert_count",
    ],
)
def test_false_green_evidence_is_rejected(mutation: str) -> None:
    evidence = copy.deepcopy(_valid_evidence())
    if mutation == "duplicate_final_name":
        evidence["final_gallery"][-1]["name"] = "guardrail-gateway"
    elif mutation == "duplicate_discovery_name":
        evidence["steps"][2]["names"].append("guardrail-gateway")
    elif mutation == "stale_lifecycle":
        evidence["steps"][3]["lifecycle_after"] = "active"
    else:
        evidence["steps"][3]["count_after"] = 6

    with pytest.raises(RuntimeError, match="demo evidence mismatch"):
        _MODULE.validate_evidence(evidence)


def test_concurrent_demo_selftests_are_isolated() -> None:
    root = Path(__file__).parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    command = [sys.executable, str(root / "scripts" / "demo_selftest.py")]
    processes = [
        subprocess.Popen(
            command,
            cwd=root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        for _ in range(2)
    ]

    for process in processes:
        output, _ = process.communicate(timeout=30)
        assert process.returncode == 0, output
        assert "lifecycle is now 'draft'" in output
        assert "EvalRun=eval-demo-guardrail-gateway-0.9.0" in output
        assert "PASS agent-registry demo self-test" in output
