"""Main entry point for the scraper MCP server."""

from __future__ import annotations

import argparse

from scraper_mcp.server import run_server


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Scraper MCP Server - Context-optimized web scraping",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m scraper_mcp                           # Default: streamable-http on 127.0.0.1:8000
  python -m scraper_mcp sse                       # Use SSE transport
  python -m scraper_mcp streamable-http 0.0.0.0 9000  # Custom port
  python -m scraper_mcp --enable-prompts          # Enable MCP prompts
  python -m scraper_mcp --enable-resources        # Enable MCP resources
        """,
    )

    parser.add_argument(
        "transport",
        nargs="?",
        default="streamable-http",
        choices=["streamable-http", "sse"],
        help="Transport type (default: streamable-http)",
    )
    parser.add_argument(
        "host",
        nargs="?",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "port",
        nargs="?",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)",
    )
    parser.add_argument(
        "--enable-resources",
        action="store_true",
        help="Enable MCP resources (disabled by default to reduce context overhead)",
    )
    parser.add_argument(
        "--enable-prompts",
        action="store_true",
        help="Enable MCP prompts (disabled by default to reduce context overhead)",
    )

    args = parser.parse_args()

    print(f"Starting Scraper MCP server on {args.host}:{args.port} ({args.transport})...")
    print(f"  - Resources: {'ENABLED' if args.enable_resources else 'disabled'}")
    print(f"  - Prompts: {'ENABLED' if args.enable_prompts else 'disabled'}")

    run_server(
        transport=args.transport,
        host=args.host,
        port=args.port,
        enable_resources=args.enable_resources,
        enable_prompts=args.enable_prompts,
    )


if __name__ == "__main__":
    main()
