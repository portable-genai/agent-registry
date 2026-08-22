"""Pure governed-release policy for the agent registry."""

from __future__ import annotations

from dataclasses import replace

from .models import AgentCard, Lifecycle, ReleaseEvidence


class ReleasePolicyError(ValueError):
    """A card or its assurance evidence is not eligible for production discovery."""


def approve_release(
    card: AgentCard,
    *,
    evidence: ReleaseEvidence,
) -> AgentCard:
    """Return an ACTIVE card only when governance and assurance evidence are complete."""
    missing: list[str] = []
    required = {
        "owner.team": card.owner.team,
        "owner.contact": card.owner.contact,
        "url": card.url,
        "version": card.version,
        "eval_run_id": evidence.eval_run_id,
        "eval_evidence_ref": evidence.eval_evidence_ref,
        "audit_event_id": evidence.audit_event_id,
        "approved_by": evidence.approved_by,
    }
    missing.extend(name for name, value in required.items() if not value.strip())
    if not card.scopes:
        missing.append("scopes")
    if card.lifecycle is not Lifecycle.DRAFT:
        missing.append("lifecycle=draft")
    if evidence.eval_status.strip().lower() != "passed":
        missing.append("eval_status=passed")
    if not evidence.eval_attested:
        missing.append("eval_attested=true")
    if evidence.assurance != "attested":
        missing.append("assurance=attested")
    if missing:
        raise ReleasePolicyError("agent release blocked; missing or invalid: " + ", ".join(missing))

    return replace(card, lifecycle=Lifecycle.ACTIVE, release_evidence=evidence)


def record_demo_release(card: AgentCard, *, evidence: ReleaseEvidence) -> AgentCard:
    """Attach visibly demo-only evidence without making the card discoverable."""
    if evidence.assurance != "demo-only" or evidence.eval_attested:
        raise ReleasePolicyError("demo release evidence must be demo-only and unattested")
    if card.lifecycle is not Lifecycle.DRAFT:
        raise ReleasePolicyError("demo release review applies only to draft cards")
    return replace(card, release_evidence=evidence)
