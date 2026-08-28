#!/usr/bin/env python3
"""Render A3's Agent Plugins 1.0.0 directory from what this repo already declares.

Identity comes from the registry's own self card, keywords from the governed tool catalog, and
``skills/`` from ``.agents/skills``. Nothing is hand-authored, so the manifest cannot advertise a
capability the registry does not have.

Run it with ``make plugin``; the output is build output and is not committed.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from hex_service_kit.plugin import (
    Author,
    PluginSpec,
    StdioServer,
    keywords_from_skill_ids,
    render,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_DEST = REPO_ROOT / "dist" / "plugin"


def build_spec() -> PluginSpec:
    """Assemble the spec from this repo's own declarations, never from literals."""
    from agent_registry.config import Settings
    from agent_registry.self_card import build_self_card
    from agent_registry.tool_catalog import ToolCatalog

    card = build_self_card(Settings.load())

    return PluginSpec(
        name="agent-registry",
        version=str(getattr(card, "version", "") or "0.0.1"),
        description=str(getattr(card, "description", "") or ""),
        license="Apache-2.0",
        repository="https://github.com/portable-genai/agent-registry",
        keywords=keywords_from_skill_ids([s.name for s in ToolCatalog().list_tools()]),
        author=Author(name="portable-genai"),
        servers={
            "agent-registry": StdioServer(
                command="python",
                args=("-m", "agent_registry.mcp"),
                cwd="${PLUGIN_ROOT}",
            )
        },
        skills_source=REPO_ROOT / ".agents" / "skills",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=pathlib.Path, default=DEFAULT_DEST)
    args = parser.parse_args(argv)
    report = render(build_spec(), args.dest)
    print(f"rendered {report.root}: {len(report.skills)} skills, {len(report.servers)} server(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
