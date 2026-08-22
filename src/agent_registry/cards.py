"""AgentCard <-> JSON conversion — the single source of truth for the wire shape.

The A2A AgentCard contract (SPEC §6) is::

    { "name", "description", "url", "version", "provider",
      "skills": [{"id","name","description"}] }

A3 carries its governance metadata in an **additive** ``governance`` block so that:

* a plain A2A / MCP peer (and C1's :class:`RemoteRegistryAdapter`) reads only the six
  top-level fields and ignores the rest, and
* the platform can rely on ``governance.owner`` / ``governance.lifecycle`` /
  ``governance.scopes`` / ``governance.protocols`` for entitlement enforcement.

Both directions live here so the HTTP layer, the persistence adapters, and the well-known
endpoint never disagree on the shape. Enums always serialise to their ``.value``.
"""

from __future__ import annotations

from typing import Any

from .models import (
    AgentCard,
    AgentSkill,
    InteropProtocol,
    Lifecycle,
    Ownership,
    ReleaseEvidence,
)


def card_to_dict(card: AgentCard) -> dict[str, Any]:
    """Render a card as the SPEC §6 JSON body plus an additive ``governance`` block."""
    body: dict[str, Any] = {
        "name": card.name,
        "description": card.description,
        "url": card.url,
        "version": card.version,
        "provider": card.provider,
        "skills": [{"id": s.id, "name": s.name, "description": s.description} for s in card.skills],
    }
    body["governance"] = {
        "owner": {
            "team": card.owner.team,
            "contact": card.owner.contact,
            "organization": card.owner.organization,
        },
        "lifecycle": card.lifecycle.value,
        "scopes": list(card.scopes),
        "protocols": [p.value for p in card.protocols],
        "release_evidence": (
            {
                "eval_run_id": card.release_evidence.eval_run_id,
                "eval_status": card.release_evidence.eval_status,
                "eval_attested": card.release_evidence.eval_attested,
                "eval_evidence_ref": card.release_evidence.eval_evidence_ref,
                "audit_event_id": card.release_evidence.audit_event_id,
                "approved_by": card.release_evidence.approved_by,
                "released_at": card.release_evidence.released_at,
                "assurance": card.release_evidence.assurance,
                "schema_version": card.release_evidence.schema_version,
            }
            if card.release_evidence is not None
            else None
        ),
    }
    return body


def card_from_dict(body: dict[str, Any]) -> AgentCard:
    """Parse a SPEC §6 JSON body (with optional ``governance``) into an :class:`AgentCard`.

    Tolerant of cards authored by plain A2A clients that omit the ``governance`` block —
    governance fields then fall back to their safe defaults (active, no scopes).
    """
    skills = tuple(
        AgentSkill(
            id=str(item.get("id", "")),
            name=str(item.get("name", "")),
            description=str(item.get("description", "")),
        )
        for item in (body.get("skills") or ())
    )
    gov = body.get("governance") or {}
    owner_raw = gov.get("owner") or {}
    owner = Ownership(
        team=str(owner_raw.get("team", "")),
        contact=str(owner_raw.get("contact", "")),
        organization=str(owner_raw.get("organization", "")),
    )
    lifecycle = _parse_lifecycle(gov.get("lifecycle"))
    scopes = tuple(str(s) for s in (gov.get("scopes") or ()))
    protocols = _parse_protocols(gov.get("protocols"))
    release_raw = gov.get("release_evidence")
    release_evidence = (
        ReleaseEvidence(
            eval_run_id=str(release_raw.get("eval_run_id", "")),
            eval_status=str(release_raw.get("eval_status", "")),
            eval_attested=release_raw.get("eval_attested") is True,
            eval_evidence_ref=str(release_raw.get("eval_evidence_ref", "")),
            audit_event_id=str(release_raw.get("audit_event_id", "")),
            approved_by=str(release_raw.get("approved_by", "")),
            released_at=str(release_raw.get("released_at", "")),
            assurance=str(release_raw.get("assurance", "not-attested")),
            schema_version=str(release_raw.get("schema_version", "agent-release/v1")),
        )
        if isinstance(release_raw, dict)
        else None
    )
    return AgentCard(
        name=str(body.get("name", "")),
        description=str(body.get("description", "")),
        url=str(body.get("url", "")),
        version=str(body.get("version", "")),
        provider=str(body.get("provider", "agent-registry")),
        skills=skills,
        owner=owner,
        lifecycle=lifecycle,
        scopes=scopes,
        protocols=protocols,
        release_evidence=release_evidence,
    )


def _parse_lifecycle(value: Any) -> Lifecycle:
    if value is None:
        return Lifecycle.DRAFT
    try:
        return Lifecycle(str(value).lower())
    except ValueError:
        return Lifecycle.DRAFT


def _parse_protocols(value: Any) -> tuple[InteropProtocol, ...]:
    if not value:
        return (InteropProtocol.A2A, InteropProtocol.MCP)
    out: list[InteropProtocol] = []
    for item in value:
        try:
            out.append(InteropProtocol(str(item).lower()))
        except ValueError:
            continue
    return tuple(out) or (InteropProtocol.A2A, InteropProtocol.MCP)
