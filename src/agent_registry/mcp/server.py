"""Serve A3's read-only discovery catalog over MCP 2026-07-28.

A3 is the third interop surface: the two exemplars serve their own domain capabilities, and this
serves the directory that tells a peer those capabilities exist. It is the surface most likely
to expose a catalog/handler mismatch, because its catalog is the one thing every other agent
reads before deciding who to talk to.

`register` is on the port and is deliberately not served. See `tool_catalog` for why, and for
the test that keeps it that way.
"""

from __future__ import annotations

from typing import Any

from hex_service_kit import mcpserve

from ..container import Container
from ..tool_catalog import ToolCatalog

#: The tools this module answers, as data, so a test can hold it against the catalog without
#: starting a server or importing the MCP SDK.
HANDLER_NAMES: tuple[str, ...] = ("list_agents", "get_agent")


def build_handlers(container: Container) -> dict[str, mcpserve.Handler]:
    """Bind each declared tool to the registry port. Both are reads."""

    def list_agents(**_: Any) -> Any:
        return container.registry.list()

    def get_agent(**arguments: Any) -> Any:
        return container.registry.get(str(arguments.get("name", "")))

    return {"list_agents": list_agents, "get_agent": get_agent}


def build_server(container: Container | None = None) -> Any:
    """Build the MCP server for A3's catalog, refusing on any catalog/handler mismatch.

    No audit tools are attached here. A3 is a control plane whose own trail is agent-observability's
    concern,
    and attaching an evidence surface to the directory would put two unrelated things behind one
    endpoint.
    """
    container = container or Container()
    return mcpserve.build_server(
        name="agent-registry",
        version="0.0.1",
        catalog=ToolCatalog(),
        handlers=build_handlers(container),
    )
