"""Local deployment profile adapters: a WORKING, offline laptop registry.

The ``local`` profile is the third deployment option alongside ``gcp`` (managed AlloyDB /
Firestore) and ``onprem`` (fail-fast Google Distributed Cloud migration placeholders).
Unlike ``onprem``, the adapter here is a *real, deterministic* implementation that runs the
whole catalog end to end with **no Google Cloud, no API key, and no running emulators by
default**:

* Registry (AlloyDB / Firestore catalog) -> a single-file ``sqlite3`` store, seedable,
  keyed on the agent ``name`` with an idempotent upsert. The card body rides as JSON, so a
  stored card round-trips through :mod:`agent_registry.cards` exactly like the managed store
  writes it.

The default code path imports **no google-cloud package at module top level**. Optional
higher-fidelity local runs route to Google's official **Firestore emulator** when the
standard ``FIRESTORE_EMULATOR_HOST`` env var is set AND the client lib (from the ``[gcp]``
extra) imports; the google client is imported lazily, only on that branch. See
:mod:`agent_registry.adapters.local._emulator`.
"""
