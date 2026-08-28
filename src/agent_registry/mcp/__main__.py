"""Serve A3's read-only discovery catalog over MCP 2026-07-28 on stdio."""

from __future__ import annotations

import sys

from hex_service_kit.mcpserve import run_stdio

from .server import build_server


def main() -> int:
    run_stdio(build_server())
    return 0


if __name__ == "__main__":
    sys.exit(main())
