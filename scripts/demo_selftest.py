#!/usr/bin/env python3
"""Run the real agent-registry walkthrough unattended and assert its live transcript."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"demo evidence mismatch: {message}")


def validate_evidence(evidence: dict[str, Any]) -> None:
    _require(evidence["profile"] == "local", "profile")
    steps = evidence["steps"]
    _require(
        [step["step"] for step in steps]
        == ["well_known", "register", "discover", "govern", "onprem_failfast"],
        "step order",
    )
    self_card = steps[0]["card"]
    _require(self_card["name"] == "agent-registry", "self-card name")
    _require(
        {skill["id"] for skill in self_card["skills"]} == {"register", "resolve", "discover"},
        "self-card skills",
    )
    expected_registered = {
        "compliance-advisory",
        "guardrail-gateway",
        "kyc-doc-extractor",
        "fx-rate-helper",
    }
    _require(steps[1]["cli_exit"] == 0, "registration CLI exit")
    _require(steps[1]["http_statuses"] == [201, 201, 201], "registration HTTP statuses")
    _require(steps[1]["observed_count"] == 4, "registered gallery count")
    _require(set(steps[1]["observed_names"]) == expected_registered, "registered gallery names")
    _require(
        len(steps[1]["observed_names"]) == len(set(steps[1]["observed_names"])),
        "registered gallery uniqueness",
    )
    expected_final = expected_registered | {"agent-registry"}
    discovered_names = steps[2]["names"]
    _require(set(discovered_names) == {"agent-registry"}, "public discovery before release")
    _require(
        len(discovered_names) == len(set(discovered_names)),
        "discovered gallery uniqueness",
    )
    _require(set(steps[2]["governance_names"]) == expected_final, "governance inventory")
    _require(steps[2]["draft_lookup_status"] == 404, "draft direct resolution")
    _require(steps[2]["draft_a2a_status"] == 404, "draft A2A resolution")
    _require(
        steps[3]
        == {
            "step": "govern",
            "name": "guardrail-gateway",
            "count_after": 1,
            "governance_count_after": 5,
            "lifecycle_after": "draft",
            "eval_run_id": "eval-demo-guardrail-gateway-0.9.0",
            "audit_event_id": "audit-demo-guardrail-gateway-release",
        },
        "observed governance result",
    )
    _require(steps[4]["exit"] == 2, "on-prem fail-fast exit")
    final_gallery = evidence["final_gallery"]
    final_names = [card["name"] for card in final_gallery]
    _require(len(final_names) == len(set(final_names)), "final gallery uniqueness")
    _require(set(final_names) == expected_final, "final gallery names")
    final = {card["name"]: card for card in final_gallery}
    _require(
        final["guardrail-gateway"]["governance"]["lifecycle"] == "draft",
        "demo review must not activate production discovery",
    )
    _require(
        final["guardrail-gateway"]["governance"]["release_evidence"]["assurance"] == "demo-only",
        "demo assurance label",
    )
    _require(
        not final["fx-rate-helper"]["governance"]["owner"]["team"],
        "unowned governance signal",
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="hrz3-demo-") as directory:
        artifact = Path(directory) / "transcript.json"
        env = os.environ.copy()
        env.update(
            DEMO_AUTO="1",
            AGENT_REGISTRY_PROFILE="local",
            PYTHONPATH=str(ROOT / "src"),
        )
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "registry_demo.py"), str(artifact)],
            cwd=ROOT,
            env=env,
            check=True,
        )
        evidence: dict[str, Any] = json.loads(artifact.read_text(encoding="utf-8"))

    validate_evidence(evidence)
    print(
        "PASS agent-registry demo self-test: live registry transcript matches all narrated outcomes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
