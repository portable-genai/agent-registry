"""Managed-store adapters for the ``gcp`` profile.

Two interchangeable backends, both satisfying
:class:`~agent_registry.ports.registry.AgentRegistryPort`:

* :class:`~agent_registry.adapters.gcp.alloydb_registry.AlloyDBRegistryAdapter` — AlloyDB for
  PostgreSQL via the AlloyDB Python connector + SQLAlchemy (the default catalog store).
* :class:`~agent_registry.adapters.gcp.firestore_registry.FirestoreRegistryAdapter` — Firestore
  in Native mode, for teams that prefer a serverless document store.

All Google Cloud SDK imports inside these modules are **lazy** (inside ``__init__`` /
methods) so the package imports cleanly under the ``local`` profile with no
``google-cloud-*`` packages installed.
"""

from __future__ import annotations

__all__ = ["AlloyDBRegistryAdapter", "FirestoreRegistryAdapter"]


def __getattr__(name: str) -> object:  # pragma: no cover - thin lazy re-export
    # Lazy re-export so ``from ...gcp import AlloyDBRegistryAdapter`` does not pull SQLAlchemy
    # / the AlloyDB connector at import time under the local profile.
    if name == "AlloyDBRegistryAdapter":
        from .alloydb_registry import AlloyDBRegistryAdapter

        return AlloyDBRegistryAdapter
    if name == "FirestoreRegistryAdapter":
        from .firestore_registry import FirestoreRegistryAdapter

        return FirestoreRegistryAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
