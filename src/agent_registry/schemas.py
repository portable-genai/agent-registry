"""Pydantic request/response schemas — the wire contract.

These mirror SPEC §6 for **A3 ``agent-registry``** field-for-field::

    POST /v1/agents                  { AgentCard }                    -> 201 { AgentCard }
    GET  /v1/agents/{name}           -> { AgentCard }  (404 if absent)
    GET  /v1/agents                  -> [ { AgentCard }, ... ]
    GET  /.well-known/agent-card.json-> the registry's own card
    GET  /v1/agents/{name}/card      -> { AgentCard }  (A2A passthrough)
    GET  /healthz                    -> { "status": "ok" }

``AgentCard`` JSON = ``{ "name", "description", "url", "version", "provider",
"skills": [{"id","name","description"}] }`` (A2A discovery contract). A3 adds an optional
``governance`` block; a plain A2A client may omit it on POST and ignore it on GET.

The canonical AgentCard <-> JSON mapping lives in :mod:`agent_registry.cards`; these schemas
only describe / validate the envelope so FastAPI generates a faithful OpenAPI document.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .cards import card_to_dict
from .models import AgentCard

# --------------------------------------------------------------------------- #
# Shared sub-objects
# --------------------------------------------------------------------------- #


class SkillModel(BaseModel):
    id: str
    name: str
    description: str = ""


class OwnerModel(BaseModel):
    team: str = ""
    contact: str = ""
    organization: str = ""


class ReleaseEvidenceModel(BaseModel):
    eval_run_id: str = Field(min_length=1)
    eval_status: Literal["passed", "failed"]
    eval_attested: bool
    eval_evidence_ref: str = Field(min_length=1)
    audit_event_id: str = Field(min_length=1)
    approved_by: str = Field(min_length=1)
    released_at: str = Field(min_length=1)
    assurance: Literal["attested", "demo-only", "not-attested"] = "not-attested"
    schema_version: Literal["agent-release/v1"] = "agent-release/v1"


def _default_protocols() -> list[Literal["a2a", "mcp"]]:
    return ["a2a", "mcp"]


class GovernanceModel(BaseModel):
    """Additive A3 governance metadata. Optional for plain A2A clients."""

    owner: OwnerModel = Field(default_factory=OwnerModel)
    lifecycle: Literal["draft", "active", "deprecated", "retired"] = "draft"
    scopes: list[str] = Field(default_factory=list)
    protocols: list[Literal["a2a", "mcp"]] = Field(default_factory=_default_protocols)
    release_evidence: ReleaseEvidenceModel | None = None


# --------------------------------------------------------------------------- #
# Request / response card envelope
# --------------------------------------------------------------------------- #


class AgentCardModel(BaseModel):
    """The AgentCard envelope used for both ``POST /v1/agents`` bodies and responses.

    ``extra="ignore"`` keeps the registry forward-compatible with richer A2A cards: unknown
    top-level keys are accepted on input and simply not persisted. The six SPEC fields are
    required for a well-formed card; ``governance`` is optional.
    """

    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1)
    description: str = ""
    url: str = ""
    version: str = ""
    provider: str = "agent-registry"
    skills: list[SkillModel] = Field(default_factory=list)
    governance: GovernanceModel = Field(default_factory=GovernanceModel)

    @classmethod
    def from_card(cls, card: AgentCard) -> AgentCardModel:
        """Build the response model from a domain card via the canonical JSON mapping."""
        return cls.model_validate(card_to_dict(card))


class ReleaseRequestModel(BaseModel):
    """Immutable IDs that the server resolves against trusted Hrz4/Hrz5 evidence."""

    eval_run_id: str = Field(min_length=1)
    audit_event_id: str = Field(min_length=1)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    profile: str = "local"
    region: str = "us-central1"
    demo_only: bool = True
    production_ready: bool = False


class CapabilityModel(BaseModel):
    name: str
    available: bool
    mode: str
    assurance: str
    provider: str = ""
    reason: str = ""
    required_for_production: bool = False


class CapabilityManifestModel(BaseModel):
    service: str
    profile: str
    region: str
    capabilities: list[CapabilityModel]
    schema_version: str = "capability-manifest/v1"
    portable_core: bool = True
    demo_only: bool = False
    production_ready: bool = False
