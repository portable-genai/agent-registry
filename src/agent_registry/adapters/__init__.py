"""Adapter families bound to ports by the container.

* :mod:`agent_registry.adapters.gcp` : AlloyDB / Firestore managed-store adapters.
* :mod:`agent_registry.adapters.local` : SQLite catalog adapter (SDK-free, dev / test default).
* :mod:`agent_registry.adapters.onprem` : fail-fast migration placeholders.
"""

from __future__ import annotations
