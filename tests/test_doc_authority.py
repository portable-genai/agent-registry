"""G1/G2: the documentation authority order is declared, and it stays true.

A declared order is only worth something if something fails when it is dropped or when a
document goes stale. These tests are that something:

* the order is declared in AGENTS.md and restated in the SPEC preamble, in the same sequence;
* every document named in the order exists;
* no authority document describes a shipped capability as forthcoming or not yet built;
* the compliance mapping cites files that exist, and the regulator crosswalk says who owns it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
AUTHORITY_ORDER = ("SPEC.md", "ARCHITECTURE.md", "COMPLIANCE.md", "README.md")
STALENESS_MARKERS = ("forthcoming", "not yet built", "not yet implemented", "coming soon")


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_every_document_in_the_declared_order_exists() -> None:
    for name in AUTHORITY_ORDER:
        assert (ROOT / name).is_file(), f"{name} is named in the authority order but missing"
    assert (ROOT / "AGENTS.md").is_file()


def test_agents_md_declares_the_order_in_sequence() -> None:
    text = _read("AGENTS.md")
    assert "## Documentation authority order" in text
    positions = [text.index(f"[`{name}`]({name})") for name in AUTHORITY_ORDER]
    assert positions == sorted(positions), "AGENTS.md must list the order highest authority first"


def test_spec_preamble_restates_the_same_order() -> None:
    preamble = _read("SPEC.md").split("---", 1)[0]
    assert "Documentation authority" in preamble
    positions = [preamble.index(name) for name in AUTHORITY_ORDER]
    assert positions == sorted(positions)


@pytest.mark.parametrize("name", AUTHORITY_ORDER)
def test_authority_documents_carry_no_forward_looking_markers(name: str) -> None:
    text = _read(name).lower()
    for marker in STALENESS_MARKERS:
        assert marker not in text, f"{name} still describes something as '{marker}'"


def test_compliance_mapping_cites_files_that_exist() -> None:
    text = _read("COMPLIANCE.md")
    pattern = r"`((?:src/|infra/|eval/|scripts/|tests/|config/|docs/)[\w./*-]+)`"
    cited = set(re.findall(pattern, text))
    assert cited, "expected the mapping table to cite repository paths"
    missing = sorted(
        path
        for path in cited
        if "*" not in path
        and not (ROOT / path.split("::")[0]).exists()
        and not (ROOT / path.rstrip("/")).exists()
    )
    assert not missing, f"COMPLIANCE.md cites paths that do not exist: {missing}"


def test_regulator_crosswalk_is_present_and_adopter_owned() -> None:
    text = _read("COMPLIANCE.md")
    assert "Regulator crosswalk (ADOPTER-OWNED)" in text
    crosswalk = text.split("Regulator crosswalk (ADOPTER-OWNED)", 1)[1]
    assert "owned by the ADOPTING institution" in crosswalk
    assert "MAS" in crosswalk
    # The crosswalk must not overstate: live enforcement evidence is not claimed.
    assert "does not assert compliance" in crosswalk
