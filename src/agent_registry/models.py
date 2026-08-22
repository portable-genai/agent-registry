"""Domain models for the Agent Registry.

These frozen dataclasses are the in-process contract the ports speak. The field names
mirror the C1 Compliance Assistant domain (``AgentCard`` / ``AgentSkill``) so the JSON that
crosses the wire (see :mod:`agent_registry.schemas`) is byte-for-byte the A2A AgentCard
contract from SPEC §6:

    AgentCard JSON = { "name", "description", "url", "version", "provider",
                       "skills": [{"id","name","description"}] }

A3 layers **governance** onto that interop contract. The five SPEC-required fields above are
always present and authoritative for A2A discovery; the governance fields (``owner``,
``lifecycle``, ``scopes``) are additive metadata the catalog uses to kill shadow AI (rule
**R4**) and enforce least-privilege entitlements. They round-trip through the optional
``governance`` block of the JSON so a vanilla A2A client can ignore them while the platform
can rely on them. Enums serialise to ``.value``.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class Lifecycle(enum.Enum):
    """Governance lifecycle state of a registered agent.

    Only ``ACTIVE`` agents are discoverable for production routing; ``DEPRECATED`` cards
    stay resolvable so in-flight peers degrade gracefully; ``RETIRED`` cards are tombstoned.
    """

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class InteropProtocol(enum.Enum):
    """Interop protocols an agent speaks, surfaced for discovery."""

    A2A = "a2a"
    MCP = "mcp"


@dataclass(frozen=True, slots=True)
class AgentSkill:
    """One advertised capability on an AgentCard (A2A skill)."""

    id: str
    name: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class Ownership:
    """Who is accountable for an agent — the anti-shadow-AI anchor (rule R4)."""

    team: str = ""
    contact: str = ""
    organization: str = ""


@dataclass(frozen=True, slots=True)
class ReleaseEvidence:
    """Evidence required to transition a draft card into production discovery."""

    eval_run_id: str
    eval_status: str
    eval_attested: bool
    eval_evidence_ref: str
    audit_event_id: str
    approved_by: str
    released_at: str
    assurance: str = "attested"
    schema_version: str = "agent-release/v1"


@dataclass(frozen=True, slots=True)
class AgentCard:
    """A2A-style agent card (SPEC §6) plus A3 governance metadata.

    The first six fields are the A2A discovery contract and are what a plain A2A/MCP peer
    sees. ``owner``, ``lifecycle`` and ``scopes`` are A3 governance additions carried in the
    JSON ``governance`` block; they default to safe values so the model is valid for an
    externally-authored card that only sets the A2A fields.
    """

    name: str
    description: str
    url: str
    version: str
    provider: str = "agent-registry"
    skills: tuple[AgentSkill, ...] = ()
    # ---- A3 governance (additive; serialised under "governance") -----------------
    owner: Ownership = field(default_factory=Ownership)
    lifecycle: Lifecycle = Lifecycle.DRAFT
    # Least-privilege scopes / entitlements the agent is allowed to exercise, e.g.
    # "mcp:tool:agent_search.query" or "a2a:invoke:agent-guardrail-gateway".
    scopes: tuple[str, ...] = ()
    # Interop protocols the agent speaks (defaults to A2A + MCP).
    protocols: tuple[InteropProtocol, ...] = (InteropProtocol.A2A, InteropProtocol.MCP)
    release_evidence: ReleaseEvidence | None = None

    @property
    def discoverable(self) -> bool:
        """Whether this card should appear in production discovery results."""
        if self.provider == "agent-registry":
            return self.lifecycle in (Lifecycle.ACTIVE, Lifecycle.DEPRECATED)
        return (
            self.lifecycle in (Lifecycle.ACTIVE, Lifecycle.DEPRECATED)
            and self.release_evidence is not None
        )
