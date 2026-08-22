"""AlloyDB-backed registry adapter.

Persists AgentCards in AlloyDB for PostgreSQL — the system of record for the A3 catalog.
The card body is stored as ``JSONB`` keyed on the agent ``name``; ``register`` is an
idempotent ``INSERT ... ON CONFLICT (name) DO UPDATE`` upsert so an agent re-publishing its
card on deploy updates the row in place.

Connections go through the **AlloyDB Python connector** (private IP, IAM auth) wrapped in a
SQLAlchemy engine — the same pattern C1 uses for its freshness ledger. Data residency is
enforced upstream: the AlloyDB cluster lives in the configured region with a regional CMEK key
(see ``infra/terraform``).

Google Cloud SDK imports are lazy (inside ``__init__`` / methods) so this module imports
cleanly under the local profile with no ``google-cloud-alloydb-connector`` / SQLAlchemy
installed.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ...cards import card_from_dict, card_to_dict
from ...config import Settings
from ...models import AgentCard

if TYPE_CHECKING:  # imported only for type-checkers, never at runtime under local
    from sqlalchemy.engine import Engine

_DDL = """
CREATE TABLE IF NOT EXISTS {table} (
    name        TEXT PRIMARY KEY,
    card        JSONB NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

_UPSERT = """
INSERT INTO {table} (name, card, updated_at)
VALUES (:name, CAST(:card AS JSONB), now())
ON CONFLICT (name) DO UPDATE
    SET card = EXCLUDED.card, updated_at = now()
"""

_SELECT_ONE = "SELECT card FROM {table} WHERE name = :name"
_SELECT_ALL = "SELECT card FROM {table} ORDER BY name"


class AlloyDBRegistryAdapter:
    """AlloyDB implementation of :class:`AgentRegistryPort`."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._table = settings.alloydb.table
        self._engine: Any | None = None
        self._connector: Any | None = None
        self._initialized = False

    # ------------------------------------------------------------------ #
    # Lazy engine construction (AlloyDB connector + SQLAlchemy)
    # ------------------------------------------------------------------ #
    def _get_engine(self) -> Engine:
        if self._engine is None:
            # Lazy imports — only when a real call is made.
            import sqlalchemy
            from google.cloud.alloydb.connector import Connector, IPTypes

            adb = self._settings.alloydb
            connector = Connector()
            self._connector = connector

            def _connect() -> Any:
                return connector.connect(
                    adb.instance_uri,
                    "pg8000",
                    db=adb.database,
                    user=adb.user,
                    ip_type=IPTypes(adb.ip_type),
                    enable_iam_auth=True,
                )

            self._engine = sqlalchemy.create_engine(
                "postgresql+pg8000://",
                creator=_connect,
                pool_pre_ping=True,
            )
        if not self._initialized:
            self._ensure_schema()
            self._initialized = True
        return self._engine

    def _ensure_schema(self) -> None:
        import sqlalchemy

        assert self._engine is not None
        with self._engine.begin() as conn:
            conn.execute(sqlalchemy.text(_DDL.format(table=self._table)))

    # ------------------------------------------------------------------ #
    # AgentRegistryPort
    # ------------------------------------------------------------------ #
    def register(self, card: AgentCard) -> None:
        import sqlalchemy

        engine = self._get_engine()
        with engine.begin() as conn:
            conn.execute(
                sqlalchemy.text(_UPSERT.format(table=self._table)),
                {"name": card.name, "card": json.dumps(card_to_dict(card))},
            )

    def get(self, name: str) -> AgentCard | None:
        import sqlalchemy

        engine = self._get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                sqlalchemy.text(_SELECT_ONE.format(table=self._table)),
                {"name": name},
            ).fetchone()
        if row is None:
            return None
        return card_from_dict(self._row_to_dict(row[0]))

    def list(self) -> list[AgentCard]:
        import sqlalchemy

        engine = self._get_engine()
        with engine.connect() as conn:
            rows = conn.execute(sqlalchemy.text(_SELECT_ALL.format(table=self._table))).fetchall()
        return [card_from_dict(self._row_to_dict(r[0])) for r in rows]

    @staticmethod
    def _row_to_dict(value: Any) -> dict[str, Any]:
        # pg8000 returns JSONB as already-decoded dict; be tolerant of str too.
        if isinstance(value, str):
            return json.loads(value)
        return dict(value)
