from __future__ import annotations

import importlib.util
import sys
from argparse import Namespace
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parents[1] / "scripts" / "rename_fork.py"
_SPEC = importlib.util.spec_from_file_location("rename_fork", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def _args() -> Namespace:
    return Namespace(
        package="bank_agent_catalog",
        cli="bank-agent-catalog",
        env_prefix="BANK_CATALOG",
        resource="bank-agent-catalog",
        dist="",
    )


def test_rename_rewrites_package_cli_env_and_resource() -> None:
    rewritten, count = _MODULE._rewrite_text(
        (
            f"{_MODULE._OLD_PACKAGE} {_MODULE._OLD_ENV_PREFIX}PROFILE "
            f'{_MODULE._OLD_CLI} name = "{_MODULE._OLD_DIST}" {_MODULE._OLD_RESOURCE}'
        ),
        _MODULE._replacements(_args()),
    )
    assert count == 5
    assert rewritten == (
        "bank_agent_catalog BANK_CATALOG_PROFILE bank-agent-catalog "
        'name = "bank-agent-catalog" bank-agent-catalog'
    )


def test_apply_preflights_destination_collision_before_any_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "src" / _MODULE._OLD_PACKAGE
    destination = tmp_path / "src" / "bank_agent_catalog"
    source.mkdir(parents=True)
    destination.mkdir(parents=True)
    config = tmp_path / "settings.py"
    config.write_text(f'PROFILE = "{_MODULE._OLD_ENV_PREFIX}PROFILE"\n')
    monkeypatch.setattr(_MODULE, "_ROOT", tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rename_fork.py",
            "--package",
            "bank_agent_catalog",
            "--cli",
            "bank-agent-catalog",
            "--env-prefix",
            "BANK_CATALOG",
            "--resource",
            "bank-agent-catalog",
            "--yes",
        ],
    )
    with pytest.raises(RuntimeError, match="destination package already exists"):
        _MODULE.main()
    assert config.read_text() == f'PROFILE = "{_MODULE._OLD_ENV_PREFIX}PROFILE"\n'


def test_cli_and_resource_names_cannot_diverge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "src" / _MODULE._OLD_PACKAGE
    source.mkdir(parents=True)
    monkeypatch.setattr(_MODULE, "_ROOT", tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rename_fork.py",
            "--package",
            "bank_agent_catalog",
            "--cli",
            "bank-agent-cli",
            "--env-prefix",
            "BANK_CATALOG",
            "--resource",
            "bank-agent-service",
            "--yes",
        ],
    )
    with pytest.raises(SystemExit, match="2"):
        _MODULE.main()
    assert source.exists()


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--env-prefix", "BANK CATALOG"),
        ("--dist", "bad dist!"),
    ],
)
def test_invalid_output_names_fail_before_writes(
    flag: str,
    value: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "src" / _MODULE._OLD_PACKAGE
    source.mkdir(parents=True)
    config = tmp_path / "settings.py"
    original = f'PROFILE = "{_MODULE._OLD_ENV_PREFIX}PROFILE"\n'
    config.write_text(original)
    monkeypatch.setattr(_MODULE, "_ROOT", tmp_path)
    arguments = [
        "rename_fork.py",
        "--package",
        "bank_agent_catalog",
        "--cli",
        "bank-agent-catalog",
        "--env-prefix",
        "BANK_CATALOG",
        "--resource",
        "bank-agent-catalog",
        "--yes",
    ]
    if flag == "--env-prefix":
        arguments[arguments.index("--env-prefix") + 1] = value
    else:
        arguments.extend([flag, value])
    monkeypatch.setattr(sys, "argv", arguments)

    with pytest.raises(SystemExit, match="2"):
        _MODULE.main()
    assert config.read_text() == original
    assert source.exists()
    assert not (tmp_path / "src" / "bank_agent_catalog").exists()


def test_a_distribution_name_differing_from_the_resource_leaves_the_resource_alone() -> None:
    """They are the same token, so only the anchored form can tell them apart.

    Unanchored, the distribution replacement consumes every occurrence and the resource name
    silently becomes the distribution name. This proves that is absent, rather than believed.
    """
    args = Namespace(
        package="bank_agent_catalog",
        cli="bank-agent-catalog",
        env_prefix="BANK_CATALOG",
        resource="bank-agent-catalog",
        dist="bank-catalog-dist",
    )
    rewritten, _ = _MODULE._rewrite_text(
        f'{_MODULE._OLD_RESOURCE} name = "{_MODULE._OLD_DIST}"',
        _MODULE._replacements(args),
    )

    assert rewritten == 'bank-agent-catalog name = "bank-catalog-dist"'
