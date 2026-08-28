"""A3's discovery catalog is served over MCP, is read-only, and is packaged from itself.

A3 is the third interop surface. The two exemplars serve their own domain capabilities; this
serves the DIRECTORY that tells a peer those capabilities exist, which is the surface every
other agent reads before deciding who to talk to.

The guards are about the seam rather than the transport. What goes wrong here is not that MCP
breaks; it is that the served surface drifts from the declared one, or that the surface quietly
grows a write. `bind` refuses the first in both directions. The second has a test of its own,
because it is a decision rather than a mistake and it must stay one.

The MCP SDK is in an optional extra and the offline gate does not install it, so everything
below uses `bind`, which is pure.
"""

from __future__ import annotations

import json
import pathlib

import jsonschema
import pytest
from hex_service_kit.mcpserve import ToolDispatchError, bind
from hex_service_kit.plugin import load_schema

from agent_registry.container import Container
from agent_registry.mcp import server as mcp_server
from agent_registry.ports.registry import AgentRegistryPort
from agent_registry.tool_catalog import ToolCatalog


@pytest.fixture
def catalog() -> ToolCatalog:
    return ToolCatalog()


def test_every_declared_tool_has_a_handler_and_no_handler_is_undeclared(
    catalog: ToolCatalog,
) -> None:
    bound = bind(catalog, mcp_server.build_handlers(Container()))

    assert set(bound) == {spec.name for spec in catalog.list_tools()}


def test_a_declared_tool_with_no_handler_refuses_to_start(catalog: ToolCatalog) -> None:
    handlers = mcp_server.build_handlers(Container())
    del handlers["get_agent"]

    with pytest.raises(ToolDispatchError, match="no handler"):
        bind(catalog, handlers)


def test_a_handler_for_an_undeclared_tool_refuses_to_start(catalog: ToolCatalog) -> None:
    handlers = mcp_server.build_handlers(Container())
    handlers["register_agent"] = lambda **_: None

    with pytest.raises(ToolDispatchError, match="does not declare"):
        bind(catalog, handlers)


def test_the_catalog_serves_no_write_tool(catalog: ToolCatalog) -> None:
    """Registration is not something a caller asks for, and this is the decision, not an omission.

    `register` is on `AgentRegistryPort` and is deliberately absent from the catalog. A write
    tool here would let any peer that can reach the registry publish a card claiming any name,
    endpoint and skill set, on the surface every other agent trusts to decide who to talk to.

    Asserted against the PORT rather than against a hand-written list of forbidden names, so a
    write method added to the port later is caught here rather than quietly served.
    """
    port_writes = {
        name
        for name in dir(AgentRegistryPort)
        if not name.startswith("_") and name not in {"get", "list"}
    }
    served = {spec.name for spec in catalog.list_tools()}

    assert port_writes, "the port has no write methods, so this guard is asserting nothing"
    for write in port_writes:
        assert not any(write in name for name in served), (
            f"{write!r} reached the served catalog; a write tool here has to be a deliberate "
            "decision, so this test has to be deleted deliberately"
        )


def test_the_handler_roster_matches_the_catalog_exactly(catalog: ToolCatalog) -> None:
    assert set(mcp_server.HANDLER_NAMES) == {spec.name for spec in catalog.list_tools()}


# --------------------------------------------------------------------------- #
# Packaging
# --------------------------------------------------------------------------- #
def _render(tmp_path: pathlib.Path) -> pathlib.Path:
    import sys

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
    import render_plugin

    render_plugin.main(["--dest", str(tmp_path / "plugin")])
    return tmp_path / "plugin"


def test_the_manifest_validates_against_the_vendored_specification_schema(
    tmp_path: pathlib.Path,
) -> None:
    """`jsonschema` is a hard dev dependency so this can never quietly skip into green."""
    manifest = json.loads((_render(tmp_path) / "plugin.json").read_text())

    jsonschema.validate(manifest, load_schema("plugin"))


def test_the_manifest_advertises_exactly_the_declared_tools(
    tmp_path: pathlib.Path, catalog: ToolCatalog
) -> None:
    manifest = json.loads((_render(tmp_path) / "plugin.json").read_text())
    declared = {spec.name.replace("_", "-") for spec in catalog.list_tools()}

    assert set(manifest["keywords"]) == declared
