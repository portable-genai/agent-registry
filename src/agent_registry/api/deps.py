"""FastAPI dependency wiring for A3 ``agent-registry``.

This module builds a single, process-wide :class:`~agent_registry.container.Container`
(the ports-and-adapters registry) and exposes the active
:class:`~agent_registry.ports.registry.AgentRegistryPort` to the API layer. The Container is
created lazily on first access so importing this module — and therefore the FastAPI ``app``
— never touches Google Cloud and performs no adapter I/O: a unit test or the ``onprem``
profile can import the API with no GCP SDK installed, and importing under the ``gcp``
profile does not require ``sqlalchemy`` / the AlloyDB connector or open a live connection.

Each provider is a FastAPI ``Depends`` factory. The underlying adapter is constructed lazily
by the Container on first use (which is request time, never import time), mirroring the C1
reference where ``deps.get_container()`` is the single place that resolves the active profile.
"""

from __future__ import annotations

from functools import lru_cache

from ..config import Settings
from ..container import Container
from ..ports import AgentRegistryPort
from ..release_verifier import (
    LocalDemoReleaseEvidenceVerifier,
    ReleaseEvidenceVerifierPort,
    RemoteReleaseEvidenceVerifier,
)


@lru_cache(maxsize=1)
def get_container() -> Container:
    """Return the process-wide Container, building it on first use.

    Cached for the lifetime of the process so every request shares one set of adapter
    instances (and their cached clients). ``Settings.load()`` reads ``config/settings.yaml``
    with ``${ENV_VAR}`` interpolation and selects the active profile.
    """
    return Container(Settings.load())


def get_settings() -> Settings:
    """Convenience accessor for the active settings (region, profile…)."""
    return get_container().settings


def get_registry() -> AgentRegistryPort:
    """Resolve the active-profile registry adapter (constructed lazily by the Container)."""
    return get_container().registry


@lru_cache(maxsize=1)
def get_release_verifier() -> ReleaseEvidenceVerifierPort:
    """Return the profile-specific, server-side release-evidence verifier."""
    settings = get_settings()
    if settings.profile == "local":
        return LocalDemoReleaseEvidenceVerifier()
    if settings.profile == "gcp":
        return RemoteReleaseEvidenceVerifier(settings)
    raise NotImplementedError(
        f"release evidence verification is not configured for profile {settings.profile!r}"
    )
