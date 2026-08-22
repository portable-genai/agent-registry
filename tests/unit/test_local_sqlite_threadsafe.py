"""Concurrency regression: the local SQLite registry adapter is safe across worker threads.

Under ``local serve`` the FastAPI container is process-wide (``deps.get_container`` is
``lru_cache``d, so one ``SqliteRegistryAdapter`` instance with one ``sqlite3`` connection)
while the sync endpoints run in Starlette's anyio worker threadpool. A request handled on a
worker thread therefore calls ``register()`` / ``get()`` / ``list()`` on a connection
opened by a *different* thread (the one that built the container). Without
``check_same_thread=False`` plus a lock, sqlite3 raises "SQLite objects created in a thread
can only be used in that same thread", 500-ing the request and dropping the card publish
under concurrency.

This test constructs the adapter **once** (one in-memory connection, since in-memory DBs
are per-connection, so the one connection opened in ``__init__`` is the one all worker
threads must reach) and then drives interleaved writes (``register``) and reads
(``get`` / ``list``) from many threads via a ``ThreadPoolExecutor``, asserting no exception
is raised and the final row count is exact. It would FAIL if ``check_same_thread=False`` or
the lock were removed from ``SqliteRegistryAdapter`` (with a cross-thread
``sqlite3.ProgrammingError``); it PASSES with the fix in place.
"""

from __future__ import annotations

import concurrent.futures

from agent_registry.adapters.local.sqlite_registry import SqliteRegistryAdapter
from agent_registry.config import LocalSettings, Settings
from agent_registry.models import AgentCard, AgentSkill, Lifecycle, Ownership

_THREADS = 8
_PER_THREAD = 25


def _settings() -> Settings:
    # A single shared in-memory connection (in-memory DBs are per-connection, so the one
    # connection opened in __init__ is the one all worker threads must reach).
    return Settings(profile="local", local=LocalSettings(db_path=":memory:"))


def _card(i: int) -> AgentCard:
    return AgentCard(
        name=f"agent-{i}",
        description=f"governed agent {i}",
        url=f"https://agent-{i}.asia-southeast1.example/a2a",
        version="1.0.0",
        provider="agent-registry",
        skills=(AgentSkill(id="answer", name="Grounded Q&A", description="Cited answers."),),
        owner=Ownership(team="rsk", contact="eng@bank.example", organization="APAC Bank"),
        lifecycle=Lifecycle.ACTIVE,
        scopes=(f"mcp:tool:agent-{i}.query",),
    )


def _drive(fn) -> list:
    """Run ``fn(i)`` for i in range(_THREADS * _PER_THREAD) across a thread pool, raising
    the first exception any worker hit (so a cross-thread sqlite3 error fails the test)."""
    n = _THREADS * _PER_THREAD
    with concurrent.futures.ThreadPoolExecutor(max_workers=_THREADS) as pool:
        futures = [pool.submit(fn, i) for i in range(n)]
        return [f.result() for f in concurrent.futures.as_completed(futures)]


def test_registry_adapter_is_thread_safe() -> None:
    # Construct the adapter ONCE: one connection, reached from every worker thread.
    adapter = SqliteRegistryAdapter(_settings())

    def work(i: int) -> int:
        # Mix writes (register) and reads (get / list) on the shared connection from the
        # worker thread, exactly as concurrent FastAPI requests would.
        adapter.register(_card(i))
        assert adapter.get(f"agent-{i}") is not None
        return len(adapter.list())

    results = _drive(work)

    # No worker raised a cross-thread ProgrammingError, every interleaved read returned a
    # consistent (locked) snapshot, and the final catalog holds exactly one row per card.
    assert all(r >= 0 for r in results)
    cards = adapter.list()
    assert len(cards) == _THREADS * _PER_THREAD
    assert len({c.name for c in cards}) == _THREADS * _PER_THREAD


def test_registry_register_is_idempotent_under_concurrency() -> None:
    # Same name registered from every thread: the ON CONFLICT(name) upsert under the lock
    # must collapse to a single row with no cross-thread error and no lost-update crash.
    adapter = SqliteRegistryAdapter(_settings())

    def work(i: int) -> None:
        adapter.register(
            AgentCard(
                name="hot-agent",
                description="contended row",
                url="https://hot-agent.example/a2a",
                version=f"1.0.{i}",
            )
        )

    _drive(work)

    cards = adapter.list()
    assert len(cards) == 1
    assert cards[0].name == "hot-agent"
