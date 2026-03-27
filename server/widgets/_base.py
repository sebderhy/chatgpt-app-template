"""Shared infrastructure for widget modules."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

from pydantic import ValidationError


@dataclass(frozen=True)
class Widget:
    """Configuration for a widget that can be rendered in MCP Apps hosts."""
    identifier: str
    title: str
    description: str
    template_uri: str
    invoking: str
    invoked: str
    component_name: str
    # Tool annotations (SEP-1865 stable spec, 2026-01-26)
    read_only: bool = True
    destructive: bool = False
    open_world: bool = False
    # UI preferences
    prefers_border: bool = True


ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"
# MCP Apps MIME type for UI resources
# The profile parameter signals this is an MCP App resource
MIME_TYPE = "text/html;profile=mcp-app"

_DEFAULT_BASE_URL = "http://localhost:8000/assets"

# Cache for loaded HTML with resolved URLs (keyed by component name)
_html_cache: Dict[str, str] = {}
_html_mtimes: Dict[str, float] = {}


def _clear_html_cache() -> None:
    """Clear the HTML cache. Used by tests."""
    _html_cache.clear()
    _html_mtimes.clear()


def get_base_url() -> str:
    """Get the base URL for assets from environment or use default."""
    return os.environ.get("BASE_URL", _DEFAULT_BASE_URL).rstrip("/")


def _resolve_html_path(component_name: str) -> Path:
    """Find the HTML file for a component, raising if not found."""
    html_path = ASSETS_DIR / f"{component_name}.html"
    if html_path.exists():
        return html_path

    fallback_candidates = sorted(ASSETS_DIR.glob(f"{component_name}-*.html"))
    if fallback_candidates:
        return fallback_candidates[-1]

    raise FileNotFoundError(
        f'Widget HTML for "{component_name}" not found in {ASSETS_DIR}. '
        "Run `pnpm run build` from the repo root to generate the assets."
    )


def load_widget_html(component_name: str) -> str:
    """Load the built widget HTML from the assets directory.

    Converts relative paths (./) to absolute URLs using BASE_URL env var.
    This is needed because widget HTML is injected into iframes via srcdoc,
    where relative paths don't resolve correctly.

    Results are cached per component name. The cache is automatically
    invalidated when the file's modification time changes, so rebuilding
    widgets takes effect without restarting the server.
    """
    html_path = _resolve_html_path(component_name)
    current_mtime = html_path.stat().st_mtime

    if component_name in _html_cache and _html_mtimes.get(component_name) == current_mtime:
        return _html_cache[component_name]

    html = html_path.read_text(encoding="utf8")

    # Convert relative paths to absolute URLs for srcdoc iframe compatibility
    # HTML files use "./" prefix which works for static serving but not srcdoc
    base_url = get_base_url()
    html = html.replace('src="./', f'src="{base_url}/')
    html = html.replace('href="./', f'href="{base_url}/')

    _html_cache[component_name] = html
    _html_mtimes[component_name] = current_mtime
    return html


# Add cache_clear method for test compatibility (mimics lru_cache interface)
load_widget_html.cache_clear = _clear_html_cache  # type: ignore[attr-defined]


# External CDN domains used by the template widgets
# Add any external domains your widgets need for images, fonts, or API calls
EXTERNAL_RESOURCE_DOMAINS: List[str] = [
    "https://cdn.openai.com",           # Fonts from @openai/apps-sdk-ui
    "https://images.unsplash.com",      # Sample images in demo widgets
    "https://persistent.oaistatic.com", # Sample images in demo widgets
    "https://cesium.com",               # CesiumJS CDN for map widget
    "https://tile.openstreetmap.org",   # OpenStreetMap tiles for map widget
]

# Domains that need fetch/XHR access (connect-src).
# CesiumJS loads assets (JSON, textures, workers) and OSM tiles via fetch.
EXTERNAL_CONNECT_DOMAINS: List[str] = [
    "https://cesium.com",               # CesiumJS assets (JSON, textures, workers)
    "https://tile.openstreetmap.org",   # OpenStreetMap tile images loaded via XHR
]


def get_csp_domains() -> Dict[str, List[str]]:
    """Return CSP domains based on the current BASE_URL.

    This allows the MCP App sandbox to load external assets (JS, CSS, images)
    from our server and from external CDNs.

    SEP-1865 stable spec (2026-01-26) defines four CSP domain lists:
    - resourceDomains: scripts, styles, images, fonts
    - connectDomains: fetch/XHR requests
    - frameDomains: nested iframes (e.g., embedded maps, videos)
    - baseUriDomains: allowed base URIs for relative URL resolution
    """
    base_url = get_base_url()
    # Extract origin from base URL (e.g., "http://localhost:8000" from "http://localhost:8000/assets")
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    # Combine server origin with external CDN domains
    resource_domains = [origin] + EXTERNAL_RESOURCE_DOMAINS
    connect_domains = [origin] + EXTERNAL_CONNECT_DOMAINS

    return {
        "resourceDomains": resource_domains,  # For scripts, styles, images, fonts
        "connectDomains": connect_domains,    # For fetch/XHR requests
        "frameDomains": [],                   # Nested iframes (add domains if needed)
        "baseUriDomains": [origin],           # Base URI for relative URL resolution
    }


def get_tool_meta(widget: Widget) -> Dict[str, Any]:
    """Return MCP Apps metadata for a tool.

    The key field is `ui.resourceUri` which links the tool to its UI resource.
    The `csp` field specifies Content Security Policy domains for the sandbox.
    The `visibility` field controls who can call the tool (model, app, or both).
    The `prefersBorder` field hints to hosts about visual boundary preference.
    This follows the MCP Apps protocol specification (SEP-1865 stable, 2026-01-26).
    """
    return {
        "ui": {
            "resourceUri": widget.template_uri,
            "visibility": ["model", "app"],
            "csp": get_csp_domains(),
            "prefersBorder": widget.prefers_border,
        },
    }


def get_data_only_tool_meta() -> Dict[str, Any]:
    """Return MCP Apps metadata for data-only tools (called by widgets, not LLM).

    Data-only tools have visibility=["app"] so MCP hosts hide them from the
    model's tool list. They are only callable via widget callTool invocations.
    """
    return {
        "ui": {
            "visibility": ["app"],
        },
    }


def get_invocation_meta(widget: Widget) -> Dict[str, Any]:
    """Return metadata for tool invocation results.

    Per SEP-1865, content-item _meta.ui takes precedence over listing-level
    metadata. We include full CSP and visibility here for completeness.
    """
    return {
        "ui": {
            "resourceUri": widget.template_uri,
            "visibility": ["model", "app"],
            "csp": get_csp_domains(),
            "prefersBorder": widget.prefers_border,
        },
    }


def get_tool_schema(input_model: type | None) -> Dict[str, Any]:
    """Generate JSON Schema from the Pydantic model for a widget."""
    if not input_model:
        return {"type": "object", "properties": {}, "additionalProperties": False}

    # Generate schema from Pydantic model
    pydantic_schema = input_model.model_json_schema()

    # Convert to MCP-compatible format (remove $defs and other extras)
    properties = {}
    for field_name, field_info in pydantic_schema.get("properties", {}).items():
        prop = {"type": field_info.get("type", "string")}
        if "description" in field_info:
            prop["description"] = field_info["description"]
        if "default" in field_info:
            prop["default"] = field_info["default"]
        properties[field_name] = prop

    return {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }


def format_validation_error(e: ValidationError, input_class: type) -> str:
    """Format Pydantic validation errors into actionable messages."""
    errors = e.errors()
    field_errors = []
    for err in errors:
        field = ".".join(str(x) for x in err["loc"]) if err["loc"] else "input"
        msg = err["msg"]
        field_errors.append(f"  - {field}: {msg}")

    # Get valid field names from the model
    valid_fields = list(input_class.model_fields.keys())

    error_msg = f"Validation error. Issues:\n"
    error_msg += "\n".join(field_errors)
    error_msg += f"\n\nValid fields: {', '.join(valid_fields)}"
    return error_msg
