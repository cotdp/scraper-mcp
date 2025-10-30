# Contributing to Scraper MCP

Thank you for your interest in contributing to Scraper MCP! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Development Workflow](#development-workflow)
- [Code Standards](#code-standards)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [Areas for Contribution](#areas-for-contribution)

## Code of Conduct

We are committed to providing a welcoming and inclusive environment. Please be respectful and constructive in all interactions.

## Getting Started

### Prerequisites

- Python 3.12 or higher
- [uv](https://github.com/astral-sh/uv) package manager
- Docker and Docker Compose (for testing deployment)
- Git

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone git@github.com:YOUR_USERNAME/scraper-mcp.git
   cd scraper-mcp
   ```

3. Add the upstream repository:
   ```bash
   git remote add upstream git@github.com:carrotly-ai/scraper-mcp.git
   ```

## Development Setup

### Install Dependencies

```bash
# Install the package with development dependencies
uv pip install -e ".[dev]"
```

### Run the Server Locally

```bash
# Run with default settings (stdio transport)
python -m scraper_mcp

# Run with HTTP transport
python -m scraper_mcp streamable-http 0.0.0.0 8000
```

### Access the Dashboard

Open `http://localhost:8000/` in your browser to access the monitoring dashboard, playground, and configuration interface.

## Development Workflow

### Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bug-fix
```

### Make Your Changes

1. Write your code following the [Code Standards](#code-standards)
2. Add or update tests as needed
3. Update documentation (README, docstrings, comments)
4. Run tests and linting locally

### Keep Your Branch Updated

```bash
git fetch upstream
git rebase upstream/main
```

## Code Standards

### Python Style

We use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting:

```bash
# Check for linting issues
ruff check .

# Auto-fix linting issues
ruff check . --fix

# Format code
ruff format .
```

### Type Hints

We use type hints throughout the codebase. Run type checking with:

```bash
mypy src/
```

All public functions and methods should have complete type annotations.

### Code Organization

- **Provider Pattern**: New scraping backends should implement the `ScraperProvider` interface
- **Utilities**: HTML processing utilities go in `src/scraper_mcp/utils.py`
- **Models**: Use Pydantic v2 models for all data structures
- **Async/Await**: Use async patterns consistently throughout

### Documentation

- Add docstrings to all public functions, classes, and methods
- Update README.md for user-facing changes
- Update CLAUDE.md for development guidance changes
- Include inline comments for complex logic

### Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

```
feat: add support for JavaScript rendering
fix: resolve timeout issue with slow sites
docs: update proxy configuration examples
refactor: simplify retry logic
test: add tests for batch operations
chore: update dependencies
```

Keep commits focused and atomic. Each commit should represent a single logical change.

## Testing

### Run Tests

```bash
# Run all tests with coverage
pytest

# Run specific test file
pytest tests/test_server.py

# Run specific test class
pytest tests/test_server.py::TestScrapeUrlTool

# Run with verbose output
pytest -v

# Run without coverage report
pytest --no-cov
```

### Writing Tests

- Use `pytest` with `pytest-asyncio` for async tests
- Use `pytest-mock` for mocking
- Place test fixtures in `tests/conftest.py`
- Aim for >90% code coverage
- Test both success and error cases
- Test edge cases and boundary conditions

### Test Structure

```python
import pytest
from unittest.mock import Mock, patch

@pytest.mark.asyncio
async def test_feature_name(provider: RequestsProvider) -> None:
    """Test description."""
    # Arrange
    mock_response = Mock()
    mock_response.status_code = 200

    # Act
    with patch.object(provider.session, "get", return_value=mock_response):
        result = await provider.scrape("https://example.com")

    # Assert
    assert result.status_code == 200
```

## Submitting Changes

### Before Submitting

1. **Run all checks**:
   ```bash
   # Format code
   ruff format .

   # Fix linting issues
   ruff check . --fix

   # Type check
   mypy src/

   # Run tests
   pytest
   ```

2. **Update documentation** if needed
3. **Add tests** for new features or bug fixes
4. **Rebase on latest main**:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

### Create a Pull Request

1. Push your branch to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```

2. Go to the [repository on GitHub](https://github.com/carrotly-ai/scraper-mcp)
3. Click "New Pull Request"
4. Select your fork and branch
5. Fill out the PR template:
   - **Title**: Brief description (50 chars max)
   - **Description**:
     - What does this PR do?
     - Why is this change needed?
     - How was it tested?
     - Any breaking changes?
   - **Link related issues**: Use "Closes #123" or "Fixes #123"

### PR Review Process

- Maintainers will review your PR
- Address feedback and push updates
- Once approved, maintainers will merge your PR
- Your contribution will be credited in the release notes

## Areas for Contribution

We welcome contributions in these areas:

### High Priority

- **New Scraping Providers**: Implement `ScraperProvider` for Playwright, Selenium, or Scrapy
- **Performance Optimizations**: Improve caching, concurrency, or memory usage
- **Documentation**: Improve examples, tutorials, or API documentation
- **Test Coverage**: Add tests for edge cases or untested code paths

### Feature Ideas

- **Authentication Support**: Add support for authenticated requests (OAuth, cookies, headers)
- **Screenshot Capture**: Add tools for capturing page screenshots
- **Rate Limiting**: Implement per-domain rate limiting
- **Request Pooling**: Connection pooling for improved performance
- **Webhook Support**: Trigger scrapes via webhooks
- **Scheduled Scraping**: Cron-like scheduling for periodic scrapes
- **Export Formats**: Add JSON, XML, or CSV export options
- **Browser Fingerprinting**: Advanced anti-detection techniques
- **Sitemap Support**: Parse and scrape from XML sitemaps
- **Mobile User Agents**: Better mobile scraping support

### Bug Fixes

- Check the [Issues](https://github.com/carrotly-ai/scraper-mcp/issues) page for open bugs
- Look for issues labeled `good first issue` or `help wanted`

### Documentation

- Improve README examples
- Add tutorials or guides
- Document common use cases
- Translate documentation (if applicable)

## Questions?

- Open an [Issue](https://github.com/carrotly-ai/scraper-mcp/issues) for questions
- Check existing issues and discussions first
- Be specific and provide context

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to Scraper MCP! 🎉
