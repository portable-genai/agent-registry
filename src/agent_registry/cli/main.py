"""``agent-registry`` — the catalog CLI for A3 ``agent-registry``.

A thin, dependency-light (stdlib ``argparse``) presentation layer over the catalog. It owns
no business logic: every command builds the wiring from
:class:`~agent_registry.container.Container` for the active ``HRZ_REGISTRY_PROFILE``, calls
the resolved :class:`~agent_registry.ports.registry.AgentRegistryPort`, and prints the
result.

Design constraints honoured here:

* **Import-safe.** Importing this module (the ``[project.scripts]`` entry point, or
  ``--help``) must never pull in FastAPI, uvicorn or the Google Cloud SDKs. The container and
  adapters are imported lazily inside command bodies, so the onprem / test profile (which
  installs no Google Cloud SDK) can still load the CLI and run ``--help``.
* **Profile-aware.** ``HRZ_REGISTRY_PROFILE`` selects the adapter stack. The ``onprem``
  profile binds placeholder adapters that raise ``NotImplementedError`` from every method;
  when a command trips one of those, the CLI fails clearly (exit code 2) with a message that
  names the migration target rather than dumping a traceback.

Exit codes: ``0`` success; ``2`` the active profile cannot satisfy the command (e.g. the
onprem stub, or no adapter wired); ``1`` an unexpected runtime failure.

Primary command for the end-to-end local smoke is ``register`` followed by ``list`` /
``get`` (see README "Run it locally"). Under ``HRZ_REGISTRY_PROFILE=onprem`` any command
that touches the store exits 2 with the migration message.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime top level
    from ..config import Settings
    from ..models import AgentCard

# Exit codes (mirrors C1's _PROFILE_EXIT / _RUNTIME_EXIT contract).
_PROFILE_EXIT = 2
_RUNTIME_EXIT = 1


def _fail(message: str, *, code: int = _RUNTIME_EXIT) -> Any:
    """Print a clean error to stderr and abort with ``code`` (no traceback)."""
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def _settings() -> Settings:
    from ..config import Settings

    return Settings.load()


def _registry(settings: Settings) -> Any:
    from ..container import Container

    return Container(settings).registry


def _run(action: str, profile: str, fn: Any) -> Any:
    """Execute ``fn`` and translate adapter failures into clean CLI exit codes.

    ``NotImplementedError`` (raised by every onprem placeholder adapter) maps to a profile
    error that names the migration target; ``KeyError`` (no binding for the profile) is also
    a profile error; anything else surfaces as a runtime error. This is the single place the
    CLI turns exceptions into exit codes.
    """
    try:
        return fn()
    except NotImplementedError as exc:
        detail = str(exc) or "method not implemented"
        _fail(
            f"'{action}' is not available under profile '{profile}'. "
            f"This profile uses placeholder adapters (on-prem migration target): {detail}",
            code=_PROFILE_EXIT,
        )
    except KeyError as exc:
        _fail(
            f"'{action}' has no adapter wired for profile '{profile}': {exc}",
            code=_PROFILE_EXIT,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary: no tracebacks to operators
        _fail(f"'{action}' failed: {type(exc).__name__}: {exc}", code=_RUNTIME_EXIT)


def _card_from_json(raw: str) -> AgentCard:
    from ..cards import card_from_dict

    try:
        body = json.loads(raw)
    except json.JSONDecodeError as exc:
        _fail(f"invalid JSON for --card: {exc}", code=_RUNTIME_EXIT)
    if not isinstance(body, dict):
        _fail("--card must be a JSON object", code=_RUNTIME_EXIT)
    if not str(body.get("name", "")).strip():
        _fail("--card is missing the required 'name' field", code=_RUNTIME_EXIT)
    return card_from_dict(body)


def _print_card(card: AgentCard) -> None:
    from ..cards import card_to_dict

    print(json.dumps(card_to_dict(card), indent=2, sort_keys=True))


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def _cmd_register(args: argparse.Namespace) -> int:
    settings = _settings()
    card = _card_from_json(args.card)
    from ..models import Lifecycle

    if card.lifecycle is not Lifecycle.DRAFT:
        _fail(
            "new agent cards must be draft; use the HTTP release endpoint with "
            "attested evaluation and audit evidence"
        )

    def _do() -> AgentCard:
        registry = _registry(settings)
        registry.register(card)
        return registry.get(card.name) or card

    stored = _run("register", settings.profile, _do)
    print(f"registered '{stored.name}' (profile={settings.profile})", file=sys.stderr)
    _print_card(stored)
    return 0


def _cmd_get(args: argparse.Namespace) -> int:
    settings = _settings()

    def _do() -> AgentCard | None:
        return _registry(settings).get(args.name)

    card = _run("get", settings.profile, _do)
    if card is None:
        _fail(f"no agent registered with name '{args.name}'", code=_RUNTIME_EXIT)
    _print_card(card)
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    settings = _settings()

    def _do() -> list[AgentCard]:
        return _registry(settings).list()

    cards = _run("list", settings.profile, _do)
    from ..cards import card_to_dict

    print(json.dumps([card_to_dict(c) for c in cards], indent=2, sort_keys=True))
    print(f"{len(cards)} agent(s) (profile={settings.profile})", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-registry",
        description=(
            "A3 Agent Registry & Governance CLI: publish and resolve A2A AgentCards in the "
            "governed catalog. The active adapter stack is chosen by HRZ_REGISTRY_PROFILE "
            "(gcp | local | onprem); 'local' runs the SQLite catalog offline with no Google "
            "Cloud SDKs."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_reg = sub.add_parser("register", help="Publish (upsert) an AgentCard into the catalog.")
    p_reg.add_argument(
        "--card",
        required=True,
        help="The AgentCard as a JSON object (SPEC §6 wire shape, governance optional).",
    )
    p_reg.set_defaults(func=_cmd_register)

    p_get = sub.add_parser("get", help="Resolve a single AgentCard by name.")
    p_get.add_argument("name", help="The agent name (catalog key).")
    p_get.set_defaults(func=_cmd_get)

    p_list = sub.add_parser("list", help="List the full agent gallery.")
    p_list.set_defaults(func=_cmd_list)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
