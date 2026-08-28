"""Serve A3's read-only discovery catalog over MCP 2026-07-28."""

from .server import HANDLER_NAMES, build_handlers, build_server

__all__ = ["HANDLER_NAMES", "build_handlers", "build_server"]
