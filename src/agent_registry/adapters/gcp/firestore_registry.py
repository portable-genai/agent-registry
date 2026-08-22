"""Firestore-backed registry adapter.

A serverless alternative to AlloyDB for teams that prefer a document store. Each AgentCard
is one document keyed on the agent ``name`` in a Firestore collection; ``register`` uses
``set`` (full upsert). The Firestore database lives in the configured region with Google-managed
or CMEK encryption (see ``infra/terraform``).

Google Cloud SDK imports are lazy (inside ``__init__`` / methods) so this module imports
cleanly under the local profile with no ``google-cloud-firestore`` installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...cards import card_from_dict, card_to_dict
from ...config import Settings
from ...models import AgentCard

if TYPE_CHECKING:  # imported only for type-checkers, never at runtime under local
    from google.cloud import firestore


class FirestoreRegistryAdapter:
    """Firestore implementation of :class:`AgentRegistryPort`."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._collection_name = settings.firestore.collection
        self._client: Any | None = None

    def _get_client(self) -> firestore.Client:
        if self._client is None:
            # Lazy import — only when a real call is made.
            from google.cloud import firestore

            self._client = firestore.Client(
                project=self._settings.project_id,
                database=self._settings.firestore.database,
            )
        return self._client

    def _collection(self) -> Any:
        return self._get_client().collection(self._collection_name)

    # ------------------------------------------------------------------ #
    # AgentRegistryPort
    # ------------------------------------------------------------------ #
    def register(self, card: AgentCard) -> None:
        self._collection().document(card.name).set(card_to_dict(card))

    def get(self, name: str) -> AgentCard | None:
        snapshot = self._collection().document(name).get()
        if not snapshot.exists:
            return None
        return card_from_dict(dict(snapshot.to_dict() or {}))

    def list(self) -> list[AgentCard]:
        return [
            card_from_dict(dict(doc.to_dict() or {}))
            for doc in self._collection().order_by("name").stream()
        ]
