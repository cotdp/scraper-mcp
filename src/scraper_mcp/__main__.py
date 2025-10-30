"""Main entry point for the scraper MCP server."""

from __future__ import annotations

import sys

from scraper_mcp.server import run_server


def main() -> None:
    """Main entry point."""
    # Parse command line arguments
    transport = "streamable-http"
    host = "0.0.0.0"
    port = 8000

    if len(sys.argv) > 1:
        transport = sys.argv[1]
    if len(sys.argv) > 2:
        host = sys.argv[2]
    if len(sys.argv) > 3:
        port = int(sys.argv[3])

    print(f"Starting Scraper MCP server on {host}:{port} with {transport} transport...")
    run_server(transport=transport, host=host, port=port)


if __name__ == "__main__":
    main()
