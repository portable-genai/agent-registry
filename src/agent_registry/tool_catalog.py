"""A3's governed MCP tool catalog: agent discovery, and nothing that writes.

The other sixteen trees declare this in `adapters/gcp/mcp_tool_catalog.py` because their
catalogs describe capabilities their managed stack fronts. A3 is a control plane and its
catalog describes the registry itself, so it lives in the package root beside `cards.py`
rather than under a cloud adapter: it is profile-independent and there is no managed service
behind it to be an adapter for.

**Read-only, deliberately, and this is the same decision the ledger already records.**
`register` exists on the port and is NOT declared here. Registering an agent is something a
service does as it deploys, from a reviewed pipeline with an identity, not something a caller
asks for over a tool call. A write tool here would let any peer that can reach the registry
publish a card claiming any name, endpoint and skill set, which is the discovery surface every
other agent trusts to decide who to talk to. If a write tool is ever added, the test that
forbids it has to be deleted deliberately.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: MCP protocol revision this catalog conforms to. Membership in the modern era is what the
#: kit checks at connection time; this is the revision the catalog is written against.
MCP_PROTOCOL_VERSION = "2026-07-28"


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """One governed tool: a name, what it does, and the schema its arguments must satisfy."""

    name: str
    description: str
    input_schema: dict[str, Any]


def _build_catalog() -> dict[str, ToolSpec]:
    """Declare the read-only discovery tools, with explicit least-privilege schemas."""
    return {
        "list_agents": ToolSpec(
            name="list_agents",
            description=(
                "List the agent cards this registry holds, so a peer can discover which agents "
                "exist and what each one offers before initiating a task."
            ),
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        "get_agent": ToolSpec(
            name="get_agent",
            description=(
                "Fetch one agent card by name, including its skills, endpoint, lifecycle and "
                "release evidence."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "minLength": 1,
                        "description": "The registered agent name.",
                    }
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        ),
    }


class ToolCatalog:
    """Declarative MCP 2026-07-28 catalog of A3's read-only discovery tools."""

    def __init__(self) -> None:
        self._catalog = _build_catalog()

    def list_tools(self) -> list[ToolSpec]:
        return list(self._catalog.values())

    def get_tool(self, name: str) -> ToolSpec | None:
        return self._catalog.get(name)
