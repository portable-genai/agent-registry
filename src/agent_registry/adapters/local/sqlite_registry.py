"""Local registry adapter (AgentRegistryPort): SQLite catalog, SDK-free and seedable.

The ``local`` profile's stand-in for the managed **AlloyDB / Firestore** catalog: a single
-file ``sqlite3`` store keyed on the agent ``name``, with an idempotent ``INSERT ... ON
CONFLICT(name) DO UPDATE`` upsert so an agent re-publishing its card on deploy updates the
row in place. The card body is stored as JSON via :mod:`agent_registry.cards`, so a stored
card round-trips byte-for-byte like the managed adapters write it, which is what lets the
contract tests assert interface parity across the three families.

It is deterministic and **seedable** (``seed(cards)`` / ``add(cards)``), so the same code
backs the offline CLI run and the unit tests. There is no Google emulator for AlloyDB, so
the default path is unconditional SQLite. When the **Firestore emulator** is opted in
(``FIRESTORE_EMULATOR_HOST`` set AND the client lib imports), writes are mirrored to the
emulator for higher-fidelity local dev; the google client is imported lazily, only on that
branch, so the default path imports no google-cloud package.

The emulator branch is a **write mirror**, not a second read source: SQLite remains the
single read source of truth for :meth:`get` / :meth:`list`. To keep the two stores from
silently diverging across a deterministic reset, :meth:`seed` clears the mirrored collection
as well as the SQLite table, so a re-seed leaves no stale rows behind in the emulator.

Default DB path is under a per-package local dir (``~/.agent_registry/local.db``); tests
pass ``:memory:`` for an ephemeral, deterministic store.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from ...cards import card_from_dict, card_to_dict
from ...config import Settings
from ...models import AgentCard
from ._emulator import firestore_emulator_active

# Per-package local catalog directory name (under the user's home dir).
_DEFAULT_DB_DIRNAME = ".agent_registry"
_DEFAULT_DB_FILENAME = "local.db"


def _default_db_path() -> str:
    """Resolve the default catalog path at call time so ``$HOME`` overrides are honoured."""
    return str(Path.home() / _DEFAULT_DB_DIRNAME / _DEFAULT_DB_FILENAME)


class SqliteRegistryAdapter:
    """SQLite-backed implementation of :class:`AgentRegistryPort`."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        db_path = getattr(getattr(settings, "local", None), "db_path", "") or _default_db_path()
        self._db_path = db_path
        self._lock = threading.RLock()
        self._conn = self._connect(db_path)
        self._init_schema()

        # Optional Firestore-emulator mirror (opt-in; lazy google import on this branch only).
        self._fs = None
        self._fs_collection = settings.firestore.collection
        if firestore_emulator_active():
            from google.cloud import firestore  # noqa: PLC0415 - lazy, emulator branch only

            self._fs = firestore.Client(
                project=settings.project_id or "local",
                database=settings.firestore.database,
            )

    # ------------------------------------------------------------------ #
    # Connection / schema
    # ------------------------------------------------------------------ #
    @staticmethod
    def _connect(db_path: str) -> sqlite3.Connection:
        if db_path not in (":memory:", "") and not db_path.startswith("file:"):
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False + an RLock keeps the store usable from the FastAPI thread
        # pool, mirroring the thread-safety the in-memory adapter offered.
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_cards (
                    name        TEXT PRIMARY KEY,
                    card        TEXT NOT NULL,
                    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            self._conn.commit()

    # ------------------------------------------------------------------ #
    # Seeding (deterministic test / CLI seed)
    # ------------------------------------------------------------------ #
    def seed(self, cards: list[AgentCard] | tuple[AgentCard, ...]) -> int:
        """Replace the catalog contents with ``cards`` (deterministic seed).

        When the Firestore-emulator mirror is active, the mirrored collection is cleared too,
        so a re-seed does not leave stale rows behind in the emulator (the SQLite table and
        the mirror reset together).
        """
        with self._lock:
            self._conn.execute("DELETE FROM agent_cards")
            self._conn.commit()
        if self._fs is not None:
            collection = self._fs.collection(self._fs_collection)
            for doc in collection.list_documents():
                doc.delete()
        return self.add(list(cards))

    def add(self, cards: list[AgentCard]) -> int:
        """Upsert each card in ``cards`` without clearing existing rows."""
        for card in cards:
            self.register(card)
        return len(cards)

    # ------------------------------------------------------------------ #
    # AgentRegistryPort
    # ------------------------------------------------------------------ #
    def register(self, card: AgentCard) -> None:
        """Insert or update a card, keyed on ``card.name`` (idempotent upsert)."""
        payload = json.dumps(card_to_dict(card))
        with self._lock:
            self._conn.execute(
                "INSERT INTO agent_cards (name, card, updated_at) "
                "VALUES (?, ?, datetime('now')) "
                "ON CONFLICT(name) DO UPDATE SET card = excluded.card, "
                "updated_at = datetime('now')",
                (card.name, payload),
            )
            self._conn.commit()
        if self._fs is not None:
            self._fs.collection(self._fs_collection).document(card.name).set(card_to_dict(card))

    def get(self, name: str) -> AgentCard | None:
        """Resolve a single card by name; ``None`` if not registered."""
        with self._lock:
            row = self._conn.execute(
                "SELECT card FROM agent_cards WHERE name = ?", (name,)
            ).fetchone()
        if row is None:
            return None
        return card_from_dict(json.loads(row["card"]))

    def list(self) -> list[AgentCard]:
        """Return every registered card (the full gallery), ordered by name."""
        with self._lock:
            rows = self._conn.execute("SELECT card FROM agent_cards ORDER BY name").fetchall()
        return [card_from_dict(json.loads(r["card"])) for r in rows]
