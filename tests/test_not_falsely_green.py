"""Prove every eval metric can go RED: a degraded registry state must score below threshold.

A3 has no model to promote, so its metrics are catalog-correctness invariants rather than judge
scores. That changes nothing about falsification: a metric pinned at 1.00 that has never been
observed failing is indistinguishable from no check at all, and these four sit at 1.00 by
design. Each scorer is imported from ``eval/run_eval.py`` and fed the same observation twice,
once as the registry produced it and once carrying exactly the defect the metric exists to
catch.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from agent_eval_kit import assert_can_go_red
from eval.run_eval import (
    THRESHOLDS,
    _adapter,
    _golden_cards,
    score_governance_preserved,
    score_resolve_accuracy,
    score_roundtrip_fidelity,
    score_upsert_idempotency,
)

from agent_registry.models import AgentCard, Lifecycle


@pytest.fixture(scope="module")
def cards() -> list[AgentCard]:
    golden = _golden_cards()
    assert golden, "the proof needs a non-empty golden set"
    return golden


@pytest.fixture(scope="module")
def stored(cards: list[AgentCard]) -> list[AgentCard | None]:
    """The golden cards read back out of a clean store: the green observation."""
    registry = _adapter()
    for card in cards:
        registry.register(card)
    return [registry.get(card.name) for card in cards]


def test_upsert_idempotency_can_go_red(cards: list[AgentCard]) -> None:
    names = [c.name for c in cards]
    assert_can_go_red(
        lambda listed: score_upsert_idempotency(listed, len(cards)),
        green=names,
        red=[*names, names[0]],  # re-registering duplicated instead of updating in place
        threshold=THRESHOLDS["upsert_idempotency"],
        metric="upsert_idempotency",
    )


def test_roundtrip_fidelity_can_go_red(
    cards: list[AgentCard], stored: list[AgentCard | None]
) -> None:
    mangled = [replace(c, description="rewritten by the store") if c else None for c in stored]
    assert_can_go_red(
        lambda got: score_roundtrip_fidelity(got, cards),
        green=stored,
        red=mangled,  # the card came back out different from the one that went in
        threshold=THRESHOLDS["roundtrip_fidelity"],
        metric="roundtrip_fidelity",
    )


def test_resolve_accuracy_can_go_red(
    cards: list[AgentCard], stored: list[AgentCard | None]
) -> None:
    """The red case is a registry that answers for an agent nobody registered."""
    assert_can_go_red(
        lambda unknown: score_resolve_accuracy(stored, cards, unknown),
        green=None,
        red=cards[0],  # get("no-such-agent") resolved to a card
        threshold=THRESHOLDS["resolve_accuracy"],
        metric="resolve_accuracy",
    )


def test_governance_preserved_can_go_red(
    cards: list[AgentCard], stored: list[AgentCard | None]
) -> None:
    demoted = [replace(c, lifecycle=Lifecycle.DEPRECATED, scopes=()) if c else None for c in stored]
    assert_can_go_red(
        lambda got: score_governance_preserved(got, cards),
        green=stored,
        red=demoted,  # owner, lifecycle and scopes did not survive the store
        threshold=THRESHOLDS["governance_preserved"],
        metric="governance_preserved",
    )
