# Scraper MCP

MCP server for web scraping functionality.

## Setup

This project uses `uv` for package management.

```bash
# Install dependencies
uv pip install -e ".[dev]"

# Run the server
python -m scraper_mcp
```

## Development

```bash
# Run tests
pytest

# Type checking
mypy src/

# Linting
ruff check .
ruff format .
```

## Project Structure

```
scraper-mcp/
├── src/
│   └── scraper_mcp/
│       ├── __init__.py
│       └── __main__.py
├── tests/
│   └── __init__.py
├── pyproject.toml
└── README.md
```

## Requirements

- Python 3.12+
- uv package manager

---

_Last updated: October 30, 2025_
