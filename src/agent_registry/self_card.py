"""A3's own AgentCard, served at ``/.well-known/agent-card.json``.

Per the A2A discovery contract, an agent publishes its capabilities as an AgentCard at the
well-known path; peers fetch that card to learn the agent's skills, endpoint URL and version
before initiating a task. The registry is itself an A2A agent — it advertises catalog
skills (register / resolve / discover) so orchestrators can find *the place to find agents*.

The registry seeds this card into the catalog on startup so a standalone deployment is
immediately self-describing and ``GET /v1/agents`` is never empty.
"""

from __future__ import annotations

from .config import Settings
from .models import AgentCard, AgentSkill, InteropProtocol, Lifecycle, Ownership

_REGISTRY_SKILLS: tuple[AgentSkill, ...] = (
    AgentSkill(
        id="register",
        name="Register agent",
        description="Publish or upsert an AgentCard into the governed catalog (POST /v1/agents).",
    ),
    AgentSkill(
        id="resolve",
        name="Resolve agent card",
        description="Resolve a single agent's A2A card by name (GET /v1/agents/{name}).",
    ),
    AgentSkill(
        id="discover",
        name="Discover agents",
        description="List the agent gallery for humans and orchestrators (GET /v1/agents).",
    ),
)


def build_self_card(settings: Settings) -> AgentCard:
    """Construct the registry's own AgentCard from settings."""
    return AgentCard(
        name=settings.registry.name,
        description=(
            "A3 Agent Registry & Governance — the governed catalog/gallery of agents for "
            "the Horizon platform: identity, ownership, scoped entitlements, and A2A/MCP "
            "discovery. Registering here is what kills shadow AI (rule R4)."
        ),
        url=f"{settings.registry.public_url.rstrip('/')}/a2a",
        version=settings.registry.version,
        provider="agent-registry",
        skills=_REGISTRY_SKILLS,
        owner=Ownership(
            team="platform-governance",
            contact="platform-governance@horizon.example",
            organization="Horizon Agent Platform",
        ),
        lifecycle=Lifecycle.ACTIVE,
        scopes=("registry:read", "registry:write"),
        protocols=(InteropProtocol.A2A, InteropProtocol.MCP),
    )
