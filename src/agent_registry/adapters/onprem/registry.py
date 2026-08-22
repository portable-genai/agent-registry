"""On-prem placeholder for ``AgentRegistryPort``: the Google Distributed Cloud target.

A reversibility (P-02) migration placeholder: in the managed profile this port binds to the
AlloyDB / Firestore catalog adapter; switching ``profile`` to ``onprem`` rebinds it here.
The adapter constructs cleanly with **no external dependencies** and structurally satisfies
the same Protocol as the managed and local adapters, so the contract tests prove interface
parity. Porting the registry to an on-premise catalog is *only* a matter of filling these
bodies in: the domain is unchanged.
"""

from __future__ import annotations

from ...config import Settings
from ...models import AgentCard

_MESSAGE = (
    "On-prem AgentRegistryPort adapter is a migration placeholder; implement against your "
    "on-premise platform. Core domain logic is unchanged."
)


class OnPremRegistryAdapter:
    """Placeholder registry adapter for the on-prem (Google Distributed Cloud) profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def register(self, card: AgentCard) -> None:
        raise NotImplementedError(_MESSAGE)

    def get(self, name: str) -> AgentCard | None:
        raise NotImplementedError(_MESSAGE)

    def list(self) -> list[AgentCard]:
        raise NotImplementedError(_MESSAGE)
