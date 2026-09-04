"""FastAPI application for A3 ``agent-registry``.

Implements the SPEC §6 A3 HTTP contract exactly so C1's ``RemoteRegistryAdapter`` (and any
A2A / MCP peer) talks to it without translation::

    POST /v1/agents                   { AgentCard }  -> 201 { AgentCard }
    GET  /v1/agents/{name}            -> 200 { AgentCard } | 404
    GET  /v1/agents                   -> 200 [ { AgentCard }, ... ]
    GET  /.well-known/agent-card.json -> 200 { AgentCard }   (the registry's own card)
    GET  /v1/agents/{name}/card       -> 200 { AgentCard } | 404  (A2A passthrough)
    GET  /healthz                     -> 200 { "status": "ok" }

The app owns no business logic beyond catalog CRUD: it delegates persistence to the
:class:`~agent_registry.ports.registry.AgentRegistryPort` resolved by the
:class:`~agent_registry.container.Container`, so it runs identically against AlloyDB,
Firestore, or the SDK-free local SQLite catalog. Responses are emitted through
:func:`agent_registry.cards.card_to_dict` to guarantee the wire shape never drifts.

Design constraint — **import-safe** (mirrors the C1 reference): the module-level ``app`` is
built with route decorators only, and the active-profile adapter is resolved lazily per
request via :mod:`agent_registry.api.deps` (a FastAPI ``Depends`` provider). The registry's
own self-card is seeded in a startup hook, never at import. Importing this module (e.g.
``uvicorn agent_registry.api.app:app`` or OpenAPI/schema tooling) therefore performs no
adapter construction, no filesystem I/O, and no network — even under the ``gcp``
profile, which would otherwise need ``sqlalchemy`` / a live AlloyDB connection.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Response, status
from hex_service_kit import read_env_setting
from hex_service_kit.capabilities import (
    AssuranceLevel,
    Capability,
    CapabilityManifest,
    CapabilityMode,
)
from hex_service_kit.web import add_loopback_exposure_guard

from ..cards import card_from_dict, card_to_dict
from ..config import Settings
from ..container import Container
from ..models import AgentCard, Lifecycle
from ..ports import AgentRegistryPort
from ..release_policy import ReleasePolicyError, approve_release, record_demo_release
from ..release_verifier import (
    LocalDemoReleaseEvidenceVerifier,
    ReleaseEvidenceVerifierPort,
    ReleaseVerificationError,
    RemoteReleaseEvidenceVerifier,
)
from ..schemas import (
    AgentCardModel,
    CapabilityManifestModel,
    HealthResponse,
    ReleaseRequestModel,
)
from ..self_card import build_self_card
from . import deps
from .security import ServiceCaller, caller_is_verified

WELL_KNOWN_PATH = "/.well-known/agent-card.json"

# Lazily-resolved registry: the dependency builds the adapter only at request time (and once
# in the startup hook). ``create_app(settings)`` overrides ``deps.get_registry`` /
# ``deps.get_settings`` to bind a specific profile without touching the process-wide container.
RegistryDep = Annotated[AgentRegistryPort, Depends(deps.get_registry)]
SettingsDep = Annotated[Settings, Depends(deps.get_settings)]
ReleaseVerifierDep = Annotated[ReleaseEvidenceVerifierPort, Depends(deps.get_release_verifier)]


def _seed_self_card(registry: AgentRegistryPort, settings: Settings) -> AgentCard:
    """Register the registry's own card if it is not already present, and return it."""
    self_card = build_self_card(settings)
    if registry.get(self_card.name) is None:
        registry.register(self_card)
    return self_card


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Seed the registry's own self-card on startup (not at import).

    Resolving the adapter here is the first time any I/O happens, and only when the app
    actually starts serving. The dependency overrides applied by :func:`create_app` are
    honoured so a test app seeds its own ephemeral store.
    """
    get_registry = app.dependency_overrides.get(deps.get_registry, deps.get_registry)
    get_settings = app.dependency_overrides.get(deps.get_settings, deps.get_settings)
    _seed_self_card(get_registry(), get_settings())
    yield


app = FastAPI(
    title="A3 Agent Registry & Governance",
    version="0.1.0",
    description=(
        "Governed catalog/gallery of agents for the Horizon platform — identity, "
        "ownership, scoped entitlements, and A2A v1.0 + MCP 2026-07-28 discovery. "
        "GCP region configurable; default asia-southeast1."
    ),
    lifespan=_lifespan,
)


#: The operator's explicit opt-in to exposure. The SAME variable the bind guard in
#: ``__main__.main()`` honours, so there is one way to accept the exposure and not two.
_INSECURE_DEMO_ENV = "AGENT_REGISTRY_ALLOW_INSECURE_DEMO"


def _is_unauthenticated_posture(settings: Settings) -> bool:
    """Is this app unfit to be served to anything but a loopback peer?

    It is, unless BOTH of these hold, and the guard bounds every case where either fails:

    1. a profile was chosen. Absent that, nobody selected an authentication scheme at all; the
       guarded catalog routes already refuse every caller, but ``/healthz``, ``/v1/capabilities``
       and the well-known agent card would still answer a stranger, and a deployment nobody
       configured has no business being reachable;
    2. the scheme bound to that profile VERIFIES its caller (``api/security.caller_is_verified``,
       derived from the same ``SECURE_PROFILES`` the S2S dependency is built from). Under the
       shared-secret path the string is symmetric and anonymous, and under a deliberate ``local``
       the routes are OPEN when no string is configured; ``onprem`` is there too. None of that
       authenticates anybody, so none of it may switch this off.

    A3 has no END USER: its callers are SERVICES. That is the one word that differs from the same
    guard in the user-facing siblings, and it is why the answer here comes from the S2S scheme
    rather than from an identity adapter. A service credential authenticates a calling service and
    no end user, so it can never stand in for end-user authentication; what it CAN establish is
    that this deployment verifies the only callers it has, and under ``gcp`` it does: a
    Google-signed assertion checked against its issuer, expiry and audience, then an allowlist.
    That deployment is fronted by the platform and every data route refuses an unverified caller
    on its own, so the guard stands down for it and the shipped Cloud Run service keeps serving.

    Note what is NOT in this expression: ``AGENT_REGISTRY_S2S_TOKEN``. Whether a credential happens
    to be SET is not evidence that this deployment can authenticate its callers, and it is no
    evidence at all about the routes that carry no credential by design. The credential belongs
    where it already is: in the S2S dependency guarding the catalog, one route at a time.

    Loopback S2S is untouched either way. A sibling service calling this registry over loopback
    (the offline stack, the demo, the local compose) clears the guard on its peer address and then
    meets the S2S dependency exactly as before.
    """
    return not (settings.profile_explicit and caller_is_verified(settings.exposure_profile))


def _bind_exposure_guard(target: FastAPI, settings: Settings) -> None:
    """Register the exposure guard on ``target``, LAST so it is the OUTERMOST middleware.

    Bound to the APP OBJECT, not to ``main()``: the Dockerfile CMD is
    ``exec uvicorn agent_registry.api.app:app --host 0.0.0.0 --port ${PORT:-8083}``, which never
    reaches ``main()``, so a guard living only there is dead in every shipped process. Executed
    before this existed: a peer at 203.0.113.7 carrying no credential read ``/v1/agents``,
    ``/v1/governance/agents`` and the whole ``/v1/capabilities`` manifest.

    Applied to the scoped app ``create_app(settings)`` builds as well, from THAT app's settings,
    so a per-tenant or test app is bounded by its own posture rather than inheriting none.
    """
    add_loopback_exposure_guard(
        target,
        unauthenticated=_is_unauthenticated_posture(settings),
        insecure_demo_env=_INSECURE_DEMO_ENV,
        # The EXPOSURE profile, so a run nobody configured names itself 'unconfigured' in the
        # refusal rather than borrowing the name of a profile an operator never chose.
        posture=settings.exposure_profile,
    )


_bind_exposure_guard(app, deps.get_settings())


# ------------------------------------------------------------------------- #
# Health
# ------------------------------------------------------------------------- #
@app.get("/healthz", response_model=HealthResponse, tags=["meta"])
def healthz(settings: SettingsDep) -> HealthResponse:
    manifest = _capability_manifest(settings)
    return HealthResponse(
        profile=manifest.profile,
        region=manifest.region,
        demo_only=manifest.demo_only,
        production_ready=manifest.production_ready,
    )


@app.get("/v1/capabilities", response_model=CapabilityManifestModel, tags=["meta"])
def capabilities(settings: SettingsDep) -> CapabilityManifestModel:
    return _capability_manifest(settings)


def _capability(
    *,
    name: str,
    available: bool,
    mode: str,
    assurance: str,
    provider: str = "",
    reason: str = "",
    required_for_production: bool = False,
) -> Capability:
    """Build a kit :class:`Capability` from this service, VALIDATING both vocabularies.

    The enum constructors are the point rather than a formality: a mode or an assurance level
    this fleet does not define now raises here, instead of being served as a string that reads
    like it means something. The strings themselves are unchanged on the wire.
    """
    return Capability(
        name=name,
        available=available,
        mode=CapabilityMode(mode),
        assurance=AssuranceLevel(assurance),
        provider=provider,
        reason=reason,
        required_for_production=required_for_production,
    )


def _capability_manifest(settings: Settings) -> CapabilityManifestModel:
    demo_only = settings.profile == "local"
    managed = settings.profile == "gcp"
    refs = {
        "agent-catalog": read_env_setting("AGENT_REGISTRY_CATALOG_ATTESTATION_REF").value,
        "identity-entitlements": read_env_setting("AGENT_REGISTRY_IDENTITY_ATTESTATION_REF").value,
        "release-governance": read_env_setting("AGENT_REGISTRY_RELEASE_ATTESTATION_REF").value,
        "audit-linkage": read_env_setting("AGENT_REGISTRY_AUDIT_ATTESTATION_REF").value,
    }
    local_or_managed = demo_only or managed

    def assurance(name: str) -> str:
        return "attested" if managed and refs[name] else "not-attested"

    release_configured = bool(settings.registry.quality_url and settings.registry.observability_url)
    items = []
    for name, provider, configured in (
        ("agent-catalog", "SQLite" if demo_only else settings.backend, True),
        ("identity-entitlements", "registry governance policy", True),
        ("release-governance", "registry lifecycle policy", release_configured),
    ):
        items.append(
            _capability(
                name=name,
                available=local_or_managed and (demo_only or configured),
                mode="local" if demo_only else ("managed" if managed else "disabled"),
                assurance=(
                    "demo-only"
                    if demo_only
                    else (assurance(name) if managed and configured else "unavailable")
                ),
                provider=provider,
                reason=(
                    "functional SQLite demo; not institution-attested governance evidence"
                    if demo_only
                    else (
                        ""
                        if managed and configured and refs[name]
                        else "runtime configuration or capability-specific attestation is missing"
                    )
                ),
                required_for_production=True,
            )
        )
    items.append(
        _capability(
            name="audit-linkage",
            available=managed and bool(settings.registry.observability_url),
            mode="external" if managed else "disabled",
            assurance=(
                assurance("audit-linkage")
                if managed and settings.registry.observability_url
                else "unavailable"
            ),
            provider="agent-observability",
            reason=(
                "managed audit service intentionally absent from the laptop profile"
                if demo_only
                else (
                    ""
                    if managed and settings.registry.observability_url and refs["audit-linkage"]
                    else "agent-observability URL or audit-linkage attestation is missing"
                )
            ),
            required_for_production=True,
        )
    )
    # production_ready is NOT recomputed here: the kit manifest derives it from the
    # very capabilities just built, so the served flag and the rule behind it cannot
    # disagree. It used to be written out a second time, right above this line.
    return CapabilityManifestModel.from_manifest(
        CapabilityManifest(
            service="agent-registry",
            profile=settings.profile,
            region=settings.region,
            capabilities=tuple(items),
            demo_only=demo_only,
        )
    )


# ------------------------------------------------------------------------- #
# A2A discovery — the registry's own card
# ------------------------------------------------------------------------- #
@app.get(WELL_KNOWN_PATH, tags=["a2a"])
def well_known_card(registry: RegistryDep, settings: SettingsDep) -> dict[str, Any]:
    """Serve the registry's own AgentCard for A2A discovery."""
    self_card = build_self_card(settings)
    card = registry.get(self_card.name) or self_card
    return card_to_dict(card)


# ------------------------------------------------------------------------- #
# Catalog CRUD (SPEC §6)
# ------------------------------------------------------------------------- #
@app.post(
    "/v1/agents",
    status_code=status.HTTP_201_CREATED,
    response_model=AgentCardModel,
    tags=["agents"],
    dependencies=[ServiceCaller],
)
def register_agent(
    body: AgentCardModel,
    response: Response,
    registry: RegistryDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    """Publish a draft AgentCard; production activation uses the release endpoint."""
    card = card_from_dict(body.model_dump(mode="json"))
    if card.name == settings.registry.name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="the registry self-card is reserved and cannot be mutated through the API",
        )
    if card.lifecycle is not Lifecycle.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="new agent cards must be draft; use POST /v1/agents/{name}/release",
        )
    registry.register(card)
    stored = registry.get(card.name) or card
    response.headers["Location"] = f"/v1/agents/{card.name}"
    return card_to_dict(stored)


@app.post(
    "/v1/agents/{name}/release",
    response_model=AgentCardModel,
    tags=["agents"],
    dependencies=[ServiceCaller],
)
def release_agent(
    name: str,
    body: ReleaseRequestModel,
    registry: RegistryDep,
    verifier: ReleaseVerifierDep,
) -> dict[str, Any]:
    """Activate a draft only with an attested model-quality-gate run and agent-observability
    linkage.
    """
    card = registry.get(name)
    if card is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no agent registered with name '{name}'",
        )
    try:
        evidence = verifier.verify(
            card,
            eval_run_id=body.eval_run_id,
            audit_event_id=body.audit_event_id,
        )
        released = (
            record_demo_release(card, evidence=evidence)
            if evidence.assurance == "demo-only"
            else approve_release(card, evidence=evidence)
        )
    except (ReleasePolicyError, ReleaseVerificationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    registry.register(released)
    return card_to_dict(released)


@app.get(
    "/v1/agents",
    response_model=list[AgentCardModel],
    tags=["agents"],
    dependencies=[ServiceCaller],
)
def list_agents(registry: RegistryDep) -> list[dict[str, Any]]:
    """List only release-approved cards for production discovery."""
    return [card_to_dict(card) for card in registry.list() if card.discoverable]


@app.get(
    "/v1/agents/{name}",
    response_model=AgentCardModel,
    tags=["agents"],
    dependencies=[ServiceCaller],
)
def get_agent(name: str, registry: RegistryDep) -> dict[str, Any]:
    """Resolve a single agent card by name; 404 if it is not registered."""
    card = registry.get(name)
    if card is None or not card.discoverable:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no agent registered with name '{name}'",
        )
    return card_to_dict(card)


@app.get(
    "/v1/agents/{name}/card",
    response_model=AgentCardModel,
    tags=["a2a"],
    dependencies=[ServiceCaller],
)
def get_agent_card_passthrough(name: str, registry: RegistryDep) -> dict[str, Any]:
    """A2A passthrough — the agent's own card, the body it serves at its well-known path."""
    card = registry.get(name)
    if card is None or not card.discoverable:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no agent registered with name '{name}'",
        )
    return card_to_dict(card)


@app.get(
    "/v1/governance/agents",
    response_model=list[AgentCardModel],
    tags=["governance"],
    dependencies=[ServiceCaller],
)
def list_governance_agents(registry: RegistryDep) -> list[dict[str, Any]]:
    """List every lifecycle state for registry governance and release review."""
    return [card_to_dict(card) for card in registry.list()]


@app.get(
    "/v1/governance/agents/{name}",
    response_model=AgentCardModel,
    tags=["governance"],
    dependencies=[ServiceCaller],
)
def get_governance_agent(name: str, registry: RegistryDep) -> dict[str, Any]:
    """Resolve drafts and retired cards for governance workflows."""
    card = registry.get(name)
    if card is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no agent registered with name '{name}'",
        )
    return card_to_dict(card)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Return a FastAPI app bound to the adapter family for the given (or active) profile.

    With no ``settings`` this returns the module-level ``app`` (the active
    ``AGENT_REGISTRY_PROFILE``, resolved lazily through :mod:`agent_registry.api.deps`). Passing
    ``settings`` builds a fresh app with dependency overrides so tests bind an ephemeral
    in-memory catalog without touching the process-wide container. The bound adapter is still
    resolved lazily: the Container's ``registry`` cached-property is only realised on first
    request (and once in the startup hook), so building the app performs no I/O.
    """
    if settings is None:
        return app

    container = Container(settings)
    scoped = FastAPI(
        title=app.title,
        version=app.version,
        description=app.description,
        lifespan=_lifespan,
    )
    # Re-register the routes so FastAPI binds their dependency-override provider to this
    # scoped app. Copying ``app.router.routes`` by reference leaks the module-level
    # container into tests/tenants and can point at a stale local database.
    scoped.include_router(app.router)
    scoped.dependency_overrides[deps.get_registry] = lambda: container.registry
    scoped.dependency_overrides[deps.get_settings] = lambda: container.settings
    scoped.dependency_overrides[deps.get_release_verifier] = lambda: (
        LocalDemoReleaseEvidenceVerifier()
        if container.settings.profile == "local"
        else RemoteReleaseEvidenceVerifier(container.settings)
    )
    # Registered after the routes, so it is the OUTERMOST middleware on the scoped app too.
    _bind_exposure_guard(scoped, container.settings)
    return scoped
