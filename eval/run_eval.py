#!/usr/bin/env python3
"""Offline evaluation gate for A3 ``agent-registry`` — the promotion gate.

CI runs this on every change and the build fails if the catalog's behaviour falls below the
agreed thresholds for a governed agent registry. It needs **no Google Cloud credentials and
no Google Cloud SDK**: it drives the ``local`` SQLite adapter (the same code the offline CLI
runs) against an in-memory store and computes deterministic metrics over a small golden set.

Metrics (a registry has no LLM, so these are catalog-correctness invariants, not judge
scores):

    upsert_idempotency  >= 1.00   re-registering a name updates in place, never duplicates
    roundtrip_fidelity  >= 1.00   a stored card round-trips through cards.* byte-for-byte
    resolve_accuracy    >= 1.00   get(name) returns the registered card; unknown -> None
    governance_preserved>= 1.00   owner / lifecycle / scopes / protocols survive the store

Exit code is ``0`` iff at least one card was scored, at least one metric was computed, and
every computed metric meets its threshold. An evaluation that measured nothing fails closed:
``all(())`` is vacuously true and is not evidence of anything.

Usage::

    python eval/run_eval.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from agent_registry.adapters.local.sqlite_registry import SqliteRegistryAdapter
from agent_registry.cards import card_from_dict, card_to_dict
from agent_registry.config import LocalSettings, Settings
from agent_registry.models import AgentCard

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = _REPO_ROOT / "eval" / "datasets" / "golden_cards.jsonl"

THRESHOLDS: dict[str, float] = {
    "upsert_idempotency": 1.00,
    "roundtrip_fidelity": 1.00,
    "resolve_accuracy": 1.00,
    "governance_preserved": 1.00,
}


@dataclass(frozen=True)
class MetricResult:
    metric: str
    score: float
    threshold: float

    @property
    def passed(self) -> bool:
        return self.score >= self.threshold


@dataclass(frozen=True)
class EvalReport:
    """A report over a non-empty golden set and a non-empty metric set.

    ``all(())`` is mathematically true but is not evidence. This gate decides whether the
    registry that verifies every other system's release is itself fit to promote, so it fails
    closed unless at least one card was scored and at least one metric was computed.
    """

    metrics: list[MetricResult] = field(default_factory=list)
    n_examples: int = 0

    @property
    def passed(self) -> bool:
        return self.n_examples > 0 and bool(self.metrics) and all(m.passed for m in self.metrics)


def _golden_cards(dataset: Path = DEFAULT_DATASET) -> list[AgentCard]:
    """The golden set of AgentCards, read from the dataset file.

    A golden set living in code cannot be diffed, exported or reviewed by anyone who does not
    read Python, so it is a data artifact here like every other system's.
    """
    return [
        card_from_dict(json.loads(line))
        for line in dataset.read_text().splitlines()
        if line.strip()
    ]


def _adapter() -> SqliteRegistryAdapter:
    return SqliteRegistryAdapter(Settings(profile="local", local=LocalSettings(db_path=":memory:")))


def score_upsert_idempotency(listed_names: list[str], expected: int) -> float:
    """1.0 only when re-registering updated in place: no duplicates, no losses."""
    return 1.0 if len(listed_names) == len(set(listed_names)) == expected else 0.0


def score_roundtrip_fidelity(stored: list[AgentCard | None], originals: list[AgentCard]) -> float:
    """Fraction of cards whose stored form is byte-for-byte the card that was registered."""
    if not originals:
        return 0.0
    hits = sum(
        1
        for got, card in zip(stored, originals, strict=True)
        if got is not None and card_to_dict(got) == card_to_dict(card)
    )
    return hits / len(originals)


def score_resolve_accuracy(
    stored: list[AgentCard | None], originals: list[AgentCard], unknown: AgentCard | None
) -> float:
    """Every registered name resolves to its own card, and an unknown name resolves to None."""
    if unknown is not None:
        return 0.0  # a registry that answers for an agent it never registered
    if not originals:
        return 0.0
    hits = sum(
        1
        for got, card in zip(stored, originals, strict=True)
        if got is not None and got.name == card.name
    )
    return hits / len(originals)


def score_governance_preserved(stored: list[AgentCard | None], originals: list[AgentCard]) -> float:
    """Fraction of cards whose owner, lifecycle, scopes and protocols survived the store."""
    if not originals:
        return 0.0
    hits = sum(
        1
        for got, card in zip(stored, originals, strict=True)
        if got is not None
        and got.owner == card.owner
        and got.lifecycle is card.lifecycle
        and got.scopes == card.scopes
        and got.protocols == card.protocols
    )
    return hits / len(originals)


def evaluate() -> EvalReport:
    cards = _golden_cards()

    # upsert_idempotency: register all twice (second time bumped version), expect no dupes.
    adapter = _adapter()
    for card in cards:
        adapter.register(card)
    for card in cards:
        adapter.register(replace(card, version=card.version + "-r2"))
    idempotency = score_upsert_idempotency([c.name for c in adapter.list()], len(cards))

    # One clean store, read back once: fidelity, resolution and governance all score off it.
    fresh = _adapter()
    for card in cards:
        fresh.register(card)
    stored = [fresh.get(card.name) for card in cards]

    scores = {
        "upsert_idempotency": idempotency,
        "roundtrip_fidelity": score_roundtrip_fidelity(stored, cards),
        "resolve_accuracy": score_resolve_accuracy(stored, cards, fresh.get("no-such-agent")),
        "governance_preserved": score_governance_preserved(stored, cards),
    }
    return EvalReport(
        metrics=[MetricResult(m, scores[m], THRESHOLDS[m]) for m in sorted(THRESHOLDS)],
        n_examples=len(cards),
    )


def main() -> int:
    report = evaluate()
    print("A3 agent-registry — offline eval gate")
    print(f"  cards scored: {report.n_examples}")
    print("-" * 52)
    for m in report.metrics:
        mark = "PASS" if m.passed else "FAIL"
        print(f"  [{mark}] {m.metric:<22} {m.score:.2f} (>= {m.threshold:.2f})")
    print("-" * 52)
    verdict = "PASS" if report.passed else "FAIL"
    print(f"eval gate: {verdict}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
