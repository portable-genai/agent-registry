"""Registry port — persistence expressed as an interface.

Mirrors the C1 ``AgentRegistryPort`` (``register`` / ``get`` / ``list``) so the in-process
contract is identical on both ends of the wire. Three interchangeable adapter families
implement this Protocol:

* ``adapters/gcp/*``    : AlloyDB / Firestore managed-store adapters (real, lazy SDK calls).
* ``adapters/local/*``  : SQLite catalog adapter (SDK-free, the dev / test default).
* ``adapters/onprem/*`` : fail-fast Google Distributed Cloud migration placeholders.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..models import AgentCard


@runtime_checkable
class AgentRegistryPort(Protocol):
    """The catalog persistence contract.

    ``register`` is an idempotent upsert keyed on :attr:`AgentCard.name`, so re-registering
    a card with a new ``version`` updates it in place: agents publish their card on every
    deploy. Implementations must be safe to call from the SDK-free local SQLite catalog
    (offline) and from a managed AlloyDB / Firestore store identically.
    """

    def register(self, card: AgentCard) -> None:
        """Insert or update a card, keyed on ``card.name``."""
        ...

    def get(self, name: str) -> AgentCard | None:
        """Resolve a single card by name; ``None`` if not registered."""
        ...

    def list(self) -> list[AgentCard]:
        """Return every registered card (the full gallery)."""
        ...
