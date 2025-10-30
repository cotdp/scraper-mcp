"""Dashboard router for serving the monitoring web interface."""

from pathlib import Path

from starlette.requests import Request
from starlette.responses import HTMLResponse

# Setup template directory
TEMPLATES_DIR = Path(__file__).parent / "templates"


async def dashboard(request: Request) -> HTMLResponse:
    """Serve the monitoring dashboard.

    Returns:
        HTMLResponse with the dashboard UI
    """
    # Read the template file directly since it's already complete HTML
    template_path = TEMPLATES_DIR / "dashboard.html"
    html_content = template_path.read_text()
    return HTMLResponse(content=html_content)
