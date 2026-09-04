"""Server-side verification of model-quality-gate evaluation and agent-observability evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from urllib.parse import quote, urlparse

import httpx

from .config import Settings
from .models import AgentCard, ReleaseEvidence


class ReleaseVerificationError(RuntimeError):
    """The referenced release evidence could not be independently verified."""


@runtime_checkable
class ReleaseEvidenceVerifierPort(Protocol):
    def verify(
        self,
        card: AgentCard,
        *,
        eval_run_id: str,
        audit_event_id: str,
    ) -> ReleaseEvidence:
        """Resolve immutable evidence and return only server-verified release facts."""
        ...


@dataclass(frozen=True, slots=True)
class LocalDemoReleaseEvidenceVerifier:
    """Approve only the repository's explicit fictional evidence IDs.

    This keeps the laptop walkthrough functional without pretending that arbitrary
    caller-authored strings are production evidence.
    """

    def verify(
        self,
        card: AgentCard,
        *,
        eval_run_id: str,
        audit_event_id: str,
    ) -> ReleaseEvidence:
        expected_eval = f"eval-demo-{card.name}-{card.version}"
        expected_audit = f"audit-demo-{card.name}-release"
        if eval_run_id != expected_eval or audit_event_id != expected_audit:
            raise ReleaseVerificationError("local demo release evidence is unknown or mismatched")
        return ReleaseEvidence(
            eval_run_id=eval_run_id,
            eval_status="passed",
            eval_attested=False,
            eval_evidence_ref=f"local-demo://hrz4/{eval_run_id}",
            audit_event_id=audit_event_id,
            approved_by="fictional-local-model-risk-reviewer",
            released_at="2026-07-30T00:00:00+00:00",
            assurance="demo-only",
        )


class RemoteReleaseEvidenceVerifier:
    """Resolve immutable evidence directly from model-quality-gate and agent-observability."""

    def __init__(self, settings: Settings) -> None:
        self._quality_url = _validate_url(settings.registry.quality_url, "model-quality-gate")
        self._observability_url = _validate_url(
            settings.registry.observability_url, "agent-observability"
        )
        self._policy = settings.registry
        required_policy = {
            "release_policy_version": self._policy.release_policy_version,
            "release_dataset_id": self._policy.release_dataset_id,
            "release_dataset_version": self._policy.release_dataset_version,
            "release_dataset_digest": self._policy.release_dataset_digest,
            "release_evaluator": self._policy.release_evaluator,
            "release_threshold_policy_digest": self._policy.release_threshold_policy_digest,
        }
        missing = [name for name, value in required_policy.items() if not value.strip()]
        if (
            missing
            or not self._policy.release_artifact_prefixes
            or not self._policy.release_redteam_categories
        ):
            raise ReleaseVerificationError(
                "managed release policy is incomplete: "
                + ", ".join((*missing, "artifact/red-team requirements"))
            )

    def verify(
        self,
        card: AgentCard,
        *,
        eval_run_id: str,
        audit_event_id: str,
    ) -> ReleaseEvidence:
        try:
            eval_response = httpx.get(
                f"{self._quality_url}/v1/mrm-evidence/{quote(eval_run_id, safe='')}",
                headers=self._headers(self._quality_url),
                timeout=10.0,
            )
            audit_response = httpx.get(
                f"{self._observability_url}/v1/audit/{quote(audit_event_id, safe='')}",
                headers=self._headers(self._observability_url),
                timeout=10.0,
            )
        except httpx.HTTPError as exc:
            raise ReleaseVerificationError(f"release verifier unavailable: {exc}") from exc
        if eval_response.status_code // 100 != 2 or audit_response.status_code // 100 != 2:
            raise ReleaseVerificationError(
                "model-quality-gate or agent-observability rejected referenced release evidence"
            )
        evaluation = eval_response.json()
        audit = audit_response.json()
        if not isinstance(evaluation, dict) or not isinstance(audit, dict):
            raise ReleaseVerificationError("evidence service returned an invalid envelope")
        target = evaluation.get("target")
        report = evaluation.get("eval_report")
        metadata = audit.get("metadata")
        if (
            not isinstance(target, dict)
            or not isinstance(report, dict)
            or not isinstance(metadata, dict)
        ):
            raise ReleaseVerificationError(
                "release evidence omitted target, report, or audit metadata"
            )
        if evaluation.get("run_id") != eval_run_id or report.get("run_id") != eval_run_id:
            raise ReleaseVerificationError(
                "model-quality-gate returned mismatched evaluation run IDs"
            )
        if target.get("model") != card.name or target.get("prompt_version") != card.version:
            raise ReleaseVerificationError(
                "model-quality-gate evidence targets a different agent release"
            )
        if target.get("dataset_id") != self._policy.release_dataset_id:
            raise ReleaseVerificationError(
                "model-quality-gate evidence used an unapproved release dataset"
            )
        if report.get("dataset_digest") != self._policy.release_dataset_digest:
            raise ReleaseVerificationError(
                "model-quality-gate evidence has the wrong dataset digest"
            )
        if report.get("dataset_version") != self._policy.release_dataset_version:
            raise ReleaseVerificationError(
                "model-quality-gate evidence used an unapproved dataset version"
            )
        if report.get("evaluator") != self._policy.release_evaluator:
            raise ReleaseVerificationError(
                "model-quality-gate evidence used an unapproved evaluator"
            )
        if evaluation.get("threshold_policy_digest") != (
            self._policy.release_threshold_policy_digest
        ):
            raise ReleaseVerificationError(
                "model-quality-gate evidence used an unapproved metric policy"
            )
        artifacts = report.get("artifact_refs")
        if not isinstance(artifacts, list) or any(
            not any(isinstance(ref, str) and ref.startswith(prefix) for ref in artifacts)
            for prefix in self._policy.release_artifact_prefixes
        ):
            raise ReleaseVerificationError(
                "model-quality-gate evidence omitted required managed artifacts"
            )
        redteam = evaluation.get("redteam_report")
        if not isinstance(redteam, dict) or not isinstance(redteam.get("results"), list):
            raise ReleaseVerificationError("model-quality-gate evidence omitted red-team results")
        passed_categories = {
            item.get("case", {}).get("category")
            for item in redteam["results"]
            if isinstance(item, dict)
            and isinstance(item.get("case"), dict)
            and item.get("passed") is True
        }
        if not set(self._policy.release_redteam_categories).issubset(passed_categories):
            raise ReleaseVerificationError(
                "model-quality-gate evidence missed required red-team categories"
            )
        if evaluation.get("requires_human_review") is not False:
            raise ReleaseVerificationError(
                "model-quality-gate still requires unresolved human review"
            )
        if evaluation.get("passed") is not True or report.get("attested") is not True:
            raise ReleaseVerificationError(
                "model-quality-gate did not attest a passing promotion gate"
            )
        if (
            audit.get("event_id") != audit_event_id
            or audit.get("action") != "release-approved"
            or audit.get("decision") != "allowed"
        ):
            raise ReleaseVerificationError(
                "agent-observability event is not the requested release approval"
            )
        expected_metadata = {
            "agent_name": card.name,
            "agent_version": card.version,
            "eval_run_id": eval_run_id,
            "approval_policy_version": self._policy.release_policy_version,
        }
        if any(metadata.get(key) != value for key, value in expected_metadata.items()):
            raise ReleaseVerificationError(
                "agent-observability approval does not bind this agent and evaluation"
            )
        approved_by = audit.get("actor")
        released_at = audit.get("timestamp")
        if not isinstance(approved_by, str) or not approved_by.strip():
            raise ReleaseVerificationError(
                "agent-observability approval has no authenticated actor"
            )
        if not isinstance(released_at, str) or not released_at.strip():
            raise ReleaseVerificationError("agent-observability approval has no timestamp")
        return ReleaseEvidence(
            eval_run_id=eval_run_id,
            eval_status="passed",
            eval_attested=True,
            eval_evidence_ref=(
                f"{self._quality_url}/v1/mrm-evidence/{quote(eval_run_id, safe='')}"
            ),
            audit_event_id=audit_event_id,
            approved_by=approved_by,
            released_at=released_at,
            assurance="attested",
        )

    def _headers(self, audience: str) -> dict[str, str]:
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.id_token import fetch_id_token

            token = fetch_id_token(Request(), audience)
        except Exception as exc:
            raise ReleaseVerificationError(
                f"could not mint a workload-identity token for {audience}: {exc}"
            ) from exc
        return {"Authorization": f"Bearer {token}"}


def _validate_url(value: str, service: str) -> str:
    url = value.rstrip("/")
    parsed = urlparse(url)
    loopback = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if not parsed.netloc or (parsed.scheme != "https" and not loopback):
        raise ReleaseVerificationError(
            f"managed release verification requires an HTTPS {service} URL"
        )
    return url
