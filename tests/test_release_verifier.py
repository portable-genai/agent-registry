from __future__ import annotations

import httpx
import pytest

from agent_registry.cards import card_from_dict
from agent_registry.config import RegistrySettings, Settings
from agent_registry.release_verifier import (
    ReleaseVerificationError,
    RemoteReleaseEvidenceVerifier,
)


def _verifier() -> RemoteReleaseEvidenceVerifier:
    return RemoteReleaseEvidenceVerifier(
        Settings(
            profile="gcp",
            registry=RegistrySettings(
                quality_url="https://quality.example.test",
                observability_url="https://observability.example.test",
                release_policy_version="release-policy/v7",
                release_dataset_id="release-golden",
                release_dataset_version="v7",
                release_dataset_digest="sha256:approved",
                release_evaluator="gemini-eval-managed",
                release_threshold_policy_digest="sha256:thresholds",
                release_artifact_prefixes=("gs://eval-artifacts/",),
                release_redteam_categories=("prompt_injection",),
            ),
        )
    )


def _card():
    return card_from_dict(
        {
            "name": "compliance-advisory",
            "description": "Fictional agent",
            "url": "https://agent.example.test",
            "version": "1.2.3",
            "provider": "test",
            "skills": [],
            "governance": {
                "owner": {"team": "risk", "contact": "risk@example.test"},
                "lifecycle": "draft",
                "scopes": ["agent:invoke"],
            },
        }
    )


def _eval_body(**changes: object) -> dict[str, object]:
    body: dict[str, object] = {
        "schema_version": "mrm-evidence/v1",
        "run_id": "eval-123",
        "target": {
            "model": "compliance-advisory",
            "prompt_version": "1.2.3",
            "dataset_id": "release-golden",
            "system": "registry",
        },
        "eval_report": {
            "run_id": "eval-123",
            "attested": True,
            "dataset_version": "v7",
            "dataset_digest": "sha256:approved",
            "evaluator": "gemini-eval-managed",
            "artifact_refs": ["gs://eval-artifacts/eval-123.json"],
        },
        "redteam_report": {"results": [{"case": {"category": "prompt_injection"}, "passed": True}]},
        "threshold_policy_digest": "sha256:thresholds",
        "requires_human_review": False,
        "passed": True,
    }
    body.update(changes)
    return body


def _audit_body(**changes: object) -> dict[str, object]:
    body: dict[str, object] = {
        "event_id": "audit-123",
        "action": "release-approved",
        "decision": "allowed",
        "actor": "model-risk@example.test",
        "timestamp": "2026-07-30T00:00:00Z",
        "metadata": {
            "agent_name": "compliance-advisory",
            "agent_version": "1.2.3",
            "eval_run_id": "eval-123",
            "approval_policy_version": "release-policy/v7",
        },
    }
    body.update(changes)
    return body


@pytest.fixture(autouse=True)
def _service_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        RemoteReleaseEvidenceVerifier,
        "_headers",
        lambda self, audience: {"Authorization": f"Bearer id-token-for:{audience}"},
    )


def test_remote_verifier_reads_hrz4_and_hrz5_with_service_identity(monkeypatch) -> None:
    requests: list[tuple[str, dict[str, object]]] = []

    def get(url: str, **kwargs: object) -> httpx.Response:
        requests.append((url, kwargs))
        body = _eval_body() if "mrm-evidence" in url else _audit_body()
        return httpx.Response(200, json=body)

    monkeypatch.setattr(httpx, "get", get)
    evidence = _verifier().verify(_card(), eval_run_id="eval-123", audit_event_id="audit-123")
    assert evidence.assurance == "attested"
    assert evidence.approved_by == "model-risk@example.test"
    assert [url for url, _ in requests] == [
        "https://quality.example.test/v1/mrm-evidence/eval-123",
        "https://observability.example.test/v1/audit/audit-123",
    ]
    assert all(
        kwargs["headers"] == {"Authorization": f"Bearer id-token-for:{url.split('/v1/')[0]}"}
        for url, kwargs in requests
    )


@pytest.mark.parametrize(
    ("eval_changes", "audit_changes"),
    [
        ({"run_id": "other-eval"}, {}),
        ({"passed": False}, {}),
        ({"eval_report": {"run_id": "eval-123", "attested": False}}, {}),
        ({"target": {"model": "other", "prompt_version": "1.2.3"}}, {}),
        (
            {
                "target": {
                    "model": "compliance-advisory",
                    "prompt_version": "1.2.3",
                    "dataset_id": "toy",
                }
            },
            {},
        ),
        ({"threshold_policy_digest": "sha256:weaker"}, {}),
        ({"requires_human_review": True}, {}),
        ({"requires_human_review": None}, {}),
        ({"requires_human_review": "false"}, {}),
        (
            {
                "eval_report": {
                    "run_id": "eval-123",
                    "attested": True,
                    "dataset_version": "v6",
                    "dataset_digest": "sha256:approved",
                    "evaluator": "gemini-eval-managed",
                    "artifact_refs": ["gs://eval-artifacts/eval-123.json"],
                }
            },
            {},
        ),
        ({}, {"event_id": "other-audit"}),
        ({}, {"action": "ask"}),
        ({}, {"decision": "escalated"}),
        ({}, {"actor": ""}),
        ({}, {"metadata": {"agent_name": "other"}}),
    ],
)
def test_remote_verifier_rejects_mismatched_or_unattested_evidence(
    monkeypatch, eval_changes: dict[str, object], audit_changes: dict[str, object]
) -> None:
    def get(url: str, **kwargs: object) -> httpx.Response:
        del kwargs
        body = _eval_body(**eval_changes) if "mrm-evidence" in url else _audit_body(**audit_changes)
        return httpx.Response(200, json=body)

    monkeypatch.setattr(httpx, "get", get)
    with pytest.raises(ReleaseVerificationError):
        _verifier().verify(_card(), eval_run_id="eval-123", audit_event_id="audit-123")
