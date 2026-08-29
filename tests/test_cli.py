"""CLI tests: the ``agent-registry`` command runs offline under ``local`` and fails fast
under ``onprem``.

These exercise the same exit-code contract the end-to-end smoke relies on: ``local`` returns
a real artifact (exit 0), and ``onprem`` exits 2 with the migration message. The profile is
selected via ``AGENT_REGISTRY_PROFILE`` exactly as in production.
"""

from __future__ import annotations

import json

import pytest

from agent_registry.cli import main as cli

_CARD = json.dumps(
    {
        "name": "smoke-agent",
        "description": "A clearly-fictional smoke-test agent.",
        "url": "https://smoke.example/a2a",
        "version": "1.0.0",
        "provider": "test",
        "skills": [{"id": "ping", "name": "Ping", "description": "ping"}],
    }
)


def test_local_register_then_get(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("AGENT_REGISTRY_PROFILE", "local")
    db = tmp_path / "cli.db"
    monkeypatch.setenv("AGENT_REGISTRY_LOCAL_DB", str(db))

    assert cli.main(["register", "--card", _CARD]) == 0
    out = capsys.readouterr().out
    assert json.loads(out)["name"] == "smoke-agent"

    assert cli.main(["get", "smoke-agent"]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["name"] == "smoke-agent"
    assert body["version"] == "1.0.0"


def test_local_list_returns_array(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("AGENT_REGISTRY_PROFILE", "local")
    monkeypatch.setenv("AGENT_REGISTRY_LOCAL_DB", str(tmp_path / "cli.db"))

    cli.main(["register", "--card", _CARD])
    capsys.readouterr()
    assert cli.main(["list"]) == 0
    body = json.loads(capsys.readouterr().out)
    assert isinstance(body, list)
    assert {c["name"] for c in body} == {"smoke-agent"}


def test_onprem_register_exits_2(monkeypatch, capsys) -> None:
    monkeypatch.setenv("AGENT_REGISTRY_PROFILE", "onprem")
    with pytest.raises(SystemExit) as exc:
        cli.main(["register", "--card", _CARD])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "on-prem migration target" in err


def test_onprem_list_exits_2(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_REGISTRY_PROFILE", "onprem")
    with pytest.raises(SystemExit) as exc:
        cli.main(["list"])
    assert exc.value.code == 2


def test_invalid_card_json_exits_1(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_REGISTRY_PROFILE", "local")
    with pytest.raises(SystemExit) as exc:
        cli.main(["register", "--card", "{not json"])
    assert exc.value.code == 1
