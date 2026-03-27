"""
Tests for MCP Apps protocol compliance.

These tests verify that tool responses and resources comply with the MCP Apps
extension specification as documented at:
- https://modelcontextprotocol.io/docs/extensions/apps
- https://github.com/modelcontextprotocol/ext-apps/blob/main/specification/

Key requirements tested:
1. MIME type matches spec exactly (text/html;profile=mcp-app)
2. Tool responses include structuredContent and TextContent
3. Tools have required _meta.ui fields (resourceUri, csp)
4. Template URIs use ui:// scheme
5. Resources referenced by tools exist and are valid
6. CSP metadata is properly structured
7. HTML content is valid

These tests help catch issues that would cause apps to fail in MCP hosts
(Claude, VS Code, Goose, basic-host) before deployment.
"""

import pytest
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mcp.types as types

# =============================================================================
# SPEC CONSTANTS - Do NOT change these, they come from the MCP Apps specification
# =============================================================================

# From @modelcontextprotocol/ext-apps RESOURCE_MIME_TYPE constant
MCP_APPS_MIME_TYPE = "text/html;profile=mcp-app"

# Required URI scheme for UI resources
UI_SCHEME = "ui://"


# =============================================================================
# TEST HELPERS
# =============================================================================

def get_widgets():
    """Import and return WIDGETS list."""
    from main import WIDGETS
    return WIDGETS


def get_widget_ids():
    """Return list of widget identifiers for parametrized tests."""
    return [w.identifier for w in get_widgets()]


async def call_tool(widget_id: str, arguments: dict = None):
    """Call a tool and return the result."""
    from main import handle_call_tool
    request = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(
            name=widget_id,
            arguments=arguments or {},
        ),
    )
    return await handle_call_tool(request)


async def read_resource(uri: str):
    """Read a resource and return the result."""
    from main import handle_read_resource
    request = types.ReadResourceRequest(
        method="resources/read",
        params=types.ReadResourceRequestParams(uri=uri),
    )
    return await handle_read_resource(request)


# =============================================================================
# MIME TYPE COMPLIANCE
# =============================================================================

class TestMimeTypeCompliance:
    """Verify MIME type matches MCP Apps specification exactly."""

    def test_mime_type_matches_spec(self):
        """MIME_TYPE must be exactly 'text/html;profile=mcp-app'.

        This is the RESOURCE_MIME_TYPE from @modelcontextprotocol/ext-apps.
        Hosts like basic-host reject resources with any other MIME type.
        """
        from main import MIME_TYPE
        assert MIME_TYPE == MCP_APPS_MIME_TYPE, (
            f"MIME_TYPE is '{MIME_TYPE}' but spec requires '{MCP_APPS_MIME_TYPE}'"
        )

    @pytest.mark.asyncio
    async def test_resources_use_correct_mime_type(self):
        """All resources must use the spec MIME type."""
        from main import list_resources
        for resource in await list_resources():
            assert resource.mimeType == MCP_APPS_MIME_TYPE, (
                f"Resource '{resource.name}' uses '{resource.mimeType}', "
                f"must use '{MCP_APPS_MIME_TYPE}'"
            )

    @pytest.mark.asyncio
    async def test_resource_content_uses_correct_mime_type(self):
        """Resource content returned by read must use correct MIME type."""
        for widget in get_widgets():
            result = await read_resource(widget.template_uri)
            assert len(result.root.contents) == 1
            assert result.root.contents[0].mimeType == MCP_APPS_MIME_TYPE


# =============================================================================
# URI SCHEME COMPLIANCE
# =============================================================================

class TestUriSchemeCompliance:
    """Verify URIs follow MCP Apps conventions."""

    def test_template_uris_use_ui_scheme(self):
        """Template URIs must start with 'ui://'."""
        for widget in get_widgets():
            assert widget.template_uri.startswith(UI_SCHEME), (
                f"Widget '{widget.identifier}' URI '{widget.template_uri}' "
                f"must start with '{UI_SCHEME}'"
            )

    def test_template_uris_end_with_html(self):
        """Template URIs should end with .html for HTML resources."""
        for widget in get_widgets():
            assert widget.template_uri.endswith(".html"), (
                f"Widget '{widget.identifier}' URI should end with '.html'"
            )

    def test_template_uris_are_unique(self):
        """Each widget must have a unique template URI."""
        uris = [w.template_uri for w in get_widgets()]
        assert len(uris) == len(set(uris)), "Duplicate template URIs found"

    def test_identifiers_are_unique(self):
        """Each widget must have a unique identifier."""
        ids = [w.identifier for w in get_widgets()]
        assert len(ids) == len(set(ids)), "Duplicate widget identifiers found"


# =============================================================================
# TOOL METADATA COMPLIANCE
# =============================================================================

class TestToolMetadataCompliance:
    """Verify tools have required MCP Apps metadata in _meta."""

    def test_tools_have_ui_section(self):
        """Tool metadata must include 'ui' section."""
        from main import get_tool_meta
        for widget in get_widgets():
            meta = get_tool_meta(widget)
            assert "ui" in meta, f"Widget '{widget.identifier}' missing 'ui' in _meta"

    def test_tools_have_resource_uri(self):
        """Tool metadata must include ui.resourceUri linking to the resource."""
        from main import get_tool_meta
        for widget in get_widgets():
            meta = get_tool_meta(widget)
            assert "resourceUri" in meta["ui"], (
                f"Widget '{widget.identifier}' missing 'ui.resourceUri'"
            )
            assert meta["ui"]["resourceUri"] == widget.template_uri, (
                f"Widget '{widget.identifier}' resourceUri mismatch"
            )

    def test_tools_have_csp(self):
        """Tool metadata must include ui.csp for sandbox security."""
        from main import get_tool_meta
        for widget in get_widgets():
            meta = get_tool_meta(widget)
            assert "csp" in meta["ui"], (
                f"Widget '{widget.identifier}' missing 'ui.csp' - "
                "required for loading external resources in sandbox"
            )

    def test_csp_structure_is_valid(self):
        """CSP must have resourceDomains and connectDomains arrays."""
        from main import get_tool_meta
        for widget in get_widgets():
            csp = get_tool_meta(widget)["ui"]["csp"]
            for field in ("resourceDomains", "connectDomains"):
                assert field in csp, f"Widget '{widget.identifier}' CSP missing '{field}'"
                assert isinstance(csp[field], list), f"CSP '{field}' must be a list"

    def test_csp_includes_server_origin(self):
        """CSP resourceDomains must include server origin for asset loading."""
        from main import get_tool_meta, get_base_url
        from urllib.parse import urlparse

        base_url = get_base_url()
        origin = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"

        for widget in get_widgets():
            domains = get_tool_meta(widget)["ui"]["csp"]["resourceDomains"]
            assert origin in domains, (
                f"Widget '{widget.identifier}' CSP must include server origin '{origin}'"
            )

    @pytest.mark.asyncio
    async def test_widget_tools_have_metadata(self):
        """Widget tools returned by list_tools must have _meta with ui section.
        Data-only helper tools (visibility=["app"] only) are excluded from this check."""
        from main import list_tools, WIDGETS_BY_ID
        widget_tools_found = 0
        for tool in await list_tools():
            meta = getattr(tool, '_meta', None) or getattr(tool, 'meta', None)
            if meta is None:
                continue
            # Skip data-only tools — they have _meta.ui.visibility but no resourceUri
            if tool.name not in WIDGETS_BY_ID:
                continue
            widget_tools_found += 1
            assert "ui" in meta, f"Tool '{tool.name}' has _meta but missing _meta.ui"
            assert "resourceUri" in meta["ui"], f"Tool '{tool.name}' missing _meta.ui.resourceUri"
        assert widget_tools_found > 0, "Expected at least one widget tool with _meta.ui"


# =============================================================================
# TOOL RESPONSE FORMAT COMPLIANCE
# =============================================================================

class TestToolResponseCompliance:
    """Verify tool responses follow MCP Apps format requirements."""

    @pytest.mark.asyncio
    async def test_tools_return_structured_content(self):
        """Tools must return structuredContent for the UI to consume."""
        for widget in get_widgets():
            result = await call_tool(widget.identifier)
            assert result.root.structuredContent is not None, (
                f"Tool '{widget.identifier}' must return structuredContent"
            )

    @pytest.mark.asyncio
    async def test_tools_return_text_content(self):
        """Tools must return content with TextContent for model narration."""
        for widget in get_widgets():
            result = await call_tool(widget.identifier)
            assert result.root.content, f"Tool '{widget.identifier}' must return content"
            assert len(result.root.content) > 0
            assert result.root.content[0].type == "text"

    @pytest.mark.asyncio
    async def test_structured_content_is_serializable(self):
        """structuredContent must be JSON-serializable."""
        for widget in get_widgets():
            result = await call_tool(widget.identifier)
            try:
                json.dumps(result.root.structuredContent)
            except (TypeError, ValueError) as e:
                pytest.fail(f"Tool '{widget.identifier}' structuredContent not serializable: {e}")

    @pytest.mark.asyncio
    async def test_tool_results_have_invocation_meta(self):
        """Tool results should include _meta for UI rendering."""
        for widget in get_widgets():
            result = await call_tool(widget.identifier)
            # Python SDK exposes _meta as either _meta or meta depending on version
            meta = getattr(result.root, '_meta', None) or getattr(result.root, 'meta', None)
            assert meta is not None, (
                f"Tool '{widget.identifier}' result missing _meta"
            )


# =============================================================================
# TOOL-RESOURCE LINKAGE COMPLIANCE
# =============================================================================

class TestToolResourceLinkage:
    """Verify tools are properly linked to existing resources."""

    @pytest.mark.asyncio
    async def test_tool_resource_uri_exists(self):
        """Resource referenced by tool's ui.resourceUri must exist."""
        from main import WIDGETS_BY_URI
        for widget in get_widgets():
            assert widget.template_uri in WIDGETS_BY_URI, (
                f"Widget '{widget.identifier}' references non-existent resource "
                f"'{widget.template_uri}'"
            )

    @pytest.mark.asyncio
    async def test_tool_resource_is_readable(self):
        """Resource referenced by tool must be readable."""
        for widget in get_widgets():
            result = await read_resource(widget.template_uri)
            assert result.root.contents, (
                f"Resource '{widget.template_uri}' returned no content"
            )


# =============================================================================
# HTML CONTENT COMPLIANCE
# =============================================================================

class TestHtmlContentCompliance:
    """Verify HTML content meets requirements."""

    def test_html_is_non_empty(self):
        """Widget HTML must be non-empty."""
        from main import load_widget_html
        for widget in get_widgets():
            html = load_widget_html(widget.component_name)
            assert html and html.strip(), (
                f"Widget '{widget.identifier}' has empty HTML. Run 'pnpm run build'."
            )

    def test_html_has_doctype(self):
        """Widget HTML should have DOCTYPE declaration."""
        from main import load_widget_html
        for widget in get_widgets():
            html_lower = load_widget_html(widget.component_name).lower().strip()
            assert html_lower.startswith("<!doctype html"), (
                f"Widget '{widget.identifier}' HTML should start with <!DOCTYPE html>"
            )

    def test_html_has_script_tag(self):
        """Widget HTML must include script tag for the widget code."""
        from main import load_widget_html
        for widget in get_widgets():
            html = load_widget_html(widget.component_name)
            assert "<script" in html.lower(), (
                f"Widget '{widget.identifier}' HTML missing script tag"
            )


# =============================================================================
# TOOL ANNOTATIONS COMPLIANCE
# =============================================================================

class TestToolAnnotations:
    """Verify tools have proper safety annotations.

    These tests validate annotation structure and consistency, not specific values.
    Tools can have any valid annotation values based on their behavior.
    """

    @pytest.mark.asyncio
    async def test_tools_have_annotations(self):
        """All tools should have annotations defined."""
        from main import list_tools
        for tool in await list_tools():
            assert tool.annotations is not None, (
                f"Tool '{tool.name}' should have annotations"
            )

    @pytest.mark.asyncio
    async def test_annotations_have_valid_hints(self):
        """Tool annotations should have boolean hint values."""
        from main import list_tools
        for tool in await list_tools():
            if tool.annotations:
                # readOnlyHint should be boolean if present
                if hasattr(tool.annotations, 'readOnlyHint') and tool.annotations.readOnlyHint is not None:
                    assert isinstance(tool.annotations.readOnlyHint, bool), (
                        f"Tool '{tool.name}' readOnlyHint must be boolean"
                    )
                # destructiveHint should be boolean if present
                if hasattr(tool.annotations, 'destructiveHint') and tool.annotations.destructiveHint is not None:
                    assert isinstance(tool.annotations.destructiveHint, bool), (
                        f"Tool '{tool.name}' destructiveHint must be boolean"
                    )

    @pytest.mark.asyncio
    async def test_destructive_tools_not_read_only(self):
        """Destructive tools should not claim to be read-only (logical consistency)."""
        from main import list_tools
        for tool in await list_tools():
            if tool.annotations:
                is_destructive = getattr(tool.annotations, 'destructiveHint', False)
                is_read_only = getattr(tool.annotations, 'readOnlyHint', False)
                # A tool cannot be both destructive AND read-only
                if is_destructive:
                    assert not is_read_only, (
                        f"Tool '{tool.name}' cannot be both destructive and read-only"
                    )


# =============================================================================
# WIDGET IDENTIFIER CONVENTIONS
# =============================================================================

class TestWidgetIdentifierConventions:
    """Verify widget identifiers follow MCP naming conventions."""

    def test_identifiers_are_valid_tool_names(self):
        """Identifiers must be lowercase letters, numbers, and underscores."""
        import re
        for widget in get_widgets():
            assert re.match(r'^[a-z][a-z0-9_]*$', widget.identifier), (
                f"Widget identifier '{widget.identifier}' must be lowercase "
                "with underscores, starting with a letter"
            )

    def test_invocation_messages_are_non_empty(self):
        """Invocation messages must be non-empty for UX."""
        for widget in get_widgets():
            assert widget.invoking and widget.invoking.strip(), (
                f"Widget '{widget.identifier}' has empty 'invoking' message"
            )
            assert widget.invoked and widget.invoked.strip(), (
                f"Widget '{widget.identifier}' has empty 'invoked' message"
            )


# =============================================================================
# TOOL VISIBILITY COMPLIANCE
# =============================================================================

class TestToolVisibilityCompliance:
    """Verify tools have proper visibility configuration per MCP Apps spec.

    The spec defines visibility as: ["model", "app"] (default), ["model"], or ["app"]
    - "model": Tool visible to and callable by the agent
    - "app": Tool callable by the app from the same server connection only
    """

    @pytest.mark.asyncio
    async def test_tools_visibility_format(self):
        """If visibility is specified, it must be a list of valid values."""
        from main import get_tool_meta
        valid_values = {"model", "app"}

        for widget in get_widgets():
            meta = get_tool_meta(widget)
            ui_meta = meta.get("ui", {})
            visibility = ui_meta.get("visibility")

            if visibility is not None:
                assert isinstance(visibility, list), (
                    f"Widget '{widget.identifier}' visibility must be a list"
                )
                for v in visibility:
                    assert v in valid_values, (
                        f"Widget '{widget.identifier}' has invalid visibility value '{v}'. "
                        f"Valid values: {valid_values}"
                    )

    @pytest.mark.asyncio
    async def test_listed_tools_visibility(self):
        """Tools in list_tools should have valid visibility if specified."""
        from main import list_tools
        valid_values = {"model", "app"}

        for tool in await list_tools():
            meta = getattr(tool, '_meta', None) or getattr(tool, 'meta', None)
            if meta and "ui" in meta:
                visibility = meta["ui"].get("visibility")
                if visibility is not None:
                    assert isinstance(visibility, list), (
                        f"Tool '{tool.name}' visibility must be a list"
                    )
                    for v in visibility:
                        assert v in valid_values, (
                            f"Tool '{tool.name}' has invalid visibility value '{v}'"
                        )


# =============================================================================
# EXTENDED CSP COMPLIANCE
# =============================================================================

class TestExtendedCspCompliance:
    """Verify CSP configuration follows the full MCP Apps spec.

    The spec defines these CSP fields:
    - connectDomains: Origins for network requests (fetch/XHR/WebSocket)
    - resourceDomains: Origins for static resources (scripts, images, styles, fonts)
    - frameDomains: Origins for nested iframes (optional)
    - baseUriDomains: Allowed base URIs (optional)
    """

    def test_csp_domains_are_valid_origins(self):
        """CSP domains must be valid HTTP(S) origins."""
        from main import get_tool_meta
        from urllib.parse import urlparse

        for widget in get_widgets():
            csp = get_tool_meta(widget)["ui"]["csp"]

            for field in ("resourceDomains", "connectDomains"):
                for domain in csp.get(field, []):
                    parsed = urlparse(domain)
                    assert parsed.scheme in ("http", "https"), (
                        f"Widget '{widget.identifier}' CSP {field} has invalid scheme in '{domain}'. "
                        "Must be http:// or https://"
                    )
                    assert parsed.netloc, (
                        f"Widget '{widget.identifier}' CSP {field} missing host in '{domain}'"
                    )

    def test_csp_optional_fields_format(self):
        """If frameDomains or baseUriDomains are specified, they must be valid."""
        from main import get_tool_meta
        from urllib.parse import urlparse

        for widget in get_widgets():
            csp = get_tool_meta(widget)["ui"]["csp"]

            for field in ("frameDomains", "baseUriDomains"):
                if field in csp:
                    assert isinstance(csp[field], list), (
                        f"Widget '{widget.identifier}' CSP {field} must be a list"
                    )
                    for domain in csp[field]:
                        parsed = urlparse(domain)
                        assert parsed.scheme in ("http", "https"), (
                            f"Widget '{widget.identifier}' CSP {field} has invalid scheme in '{domain}'"
                        )


# =============================================================================
# PERMISSIONS COMPLIANCE
# =============================================================================

class TestPermissionsCompliance:
    """Verify permissions structure follows MCP Apps spec.

    The spec defines these permission types:
    - camera: Request camera access
    - microphone: Request microphone access
    - geolocation: Request geolocation access
    - clipboardWrite: Request clipboard write access
    """

    def test_permissions_structure_if_present(self):
        """If permissions are declared, they must follow the spec structure."""
        from main import get_tool_meta
        valid_permissions = {"camera", "microphone", "geolocation", "clipboardWrite"}

        for widget in get_widgets():
            meta = get_tool_meta(widget)
            ui_meta = meta.get("ui", {})
            permissions = ui_meta.get("permissions")

            if permissions is not None:
                assert isinstance(permissions, dict), (
                    f"Widget '{widget.identifier}' permissions must be a dict"
                )
                for perm_name, perm_value in permissions.items():
                    assert perm_name in valid_permissions, (
                        f"Widget '{widget.identifier}' has unknown permission '{perm_name}'. "
                        f"Valid: {valid_permissions}"
                    )
                    # Per spec, permission values are empty objects {}
                    assert isinstance(perm_value, dict), (
                        f"Widget '{widget.identifier}' permission '{perm_name}' must be an empty dict"
                    )

    @pytest.mark.asyncio
    async def test_resource_permissions_structure(self):
        """Resource metadata permissions must follow spec structure if present."""
        valid_permissions = {"camera", "microphone", "geolocation", "clipboardWrite"}

        for widget in get_widgets():
            result = await read_resource(widget.template_uri)
            content = result.root.contents[0]

            # Check for _meta.ui.permissions
            meta = getattr(content, '_meta', None) or getattr(content, 'meta', None)
            if meta and "ui" in meta and "permissions" in meta["ui"]:
                permissions = meta["ui"]["permissions"]
                assert isinstance(permissions, dict)
                for perm_name in permissions:
                    assert perm_name in valid_permissions


# =============================================================================
# RESOURCE READ RESPONSE COMPLIANCE
# =============================================================================

class TestResourceReadCompliance:
    """Verify resources/read responses follow MCP Apps spec format.

    The spec requires resource content to include _meta.ui with:
    - csp: Content Security Policy configuration
    - permissions: Optional sandbox permissions
    - domain: Optional dedicated origin
    - prefersBorder: Optional visual boundary preference
    """

    @pytest.mark.asyncio
    async def test_resource_content_has_ui_meta(self):
        """Resource content should include _meta.ui section."""
        for widget in get_widgets():
            result = await read_resource(widget.template_uri)
            content = result.root.contents[0]

            meta = getattr(content, '_meta', None) or getattr(content, 'meta', None)
            assert meta is not None, (
                f"Resource '{widget.template_uri}' missing _meta in content"
            )
            assert "ui" in meta, (
                f"Resource '{widget.template_uri}' missing _meta.ui in content"
            )

    @pytest.mark.asyncio
    async def test_resource_content_has_csp(self):
        """Resource content _meta.ui should include CSP configuration."""
        for widget in get_widgets():
            result = await read_resource(widget.template_uri)
            content = result.root.contents[0]

            meta = getattr(content, '_meta', None) or getattr(content, 'meta', None)
            assert "csp" in meta.get("ui", {}), (
                f"Resource '{widget.template_uri}' missing _meta.ui.csp"
            )

    @pytest.mark.asyncio
    async def test_resource_content_csp_matches_tool(self):
        """Resource CSP should match the tool's declared CSP."""
        from main import get_tool_meta

        for widget in get_widgets():
            # Get tool CSP
            tool_meta = get_tool_meta(widget)
            tool_csp = tool_meta["ui"]["csp"]

            # Get resource CSP
            result = await read_resource(widget.template_uri)
            content = result.root.contents[0]
            content_meta = getattr(content, '_meta', None) or getattr(content, 'meta', None)
            resource_csp = content_meta.get("ui", {}).get("csp", {})

            # Compare resourceDomains
            assert set(resource_csp.get("resourceDomains", [])) == set(tool_csp.get("resourceDomains", [])), (
                f"Widget '{widget.identifier}' resource CSP resourceDomains doesn't match tool CSP"
            )


# =============================================================================
# INPUT SCHEMA COMPLIANCE
# =============================================================================

class TestInputSchemaCompliance:
    """Verify tool input schemas are properly defined."""

    @pytest.mark.asyncio
    async def test_tools_have_input_schema(self):
        """All tools must have an inputSchema."""
        from main import list_tools

        for tool in await list_tools():
            assert tool.inputSchema is not None, (
                f"Tool '{tool.name}' missing inputSchema"
            )
            assert isinstance(tool.inputSchema, dict), (
                f"Tool '{tool.name}' inputSchema must be a dict"
            )

    @pytest.mark.asyncio
    async def test_input_schema_is_object_type(self):
        """Tool inputSchema should be type: object."""
        from main import list_tools

        for tool in await list_tools():
            schema = tool.inputSchema
            assert schema.get("type") == "object", (
                f"Tool '{tool.name}' inputSchema type should be 'object'"
            )

    @pytest.mark.asyncio
    async def test_input_schema_has_properties(self):
        """Tool inputSchema should have properties defined."""
        from main import list_tools

        for tool in await list_tools():
            schema = tool.inputSchema
            assert "properties" in schema, (
                f"Tool '{tool.name}' inputSchema missing 'properties'"
            )

    @pytest.mark.asyncio
    async def test_input_schema_forbids_additional_properties(self):
        """Tool inputSchema should set additionalProperties: false for safety."""
        from main import list_tools

        for tool in await list_tools():
            schema = tool.inputSchema
            # This is a best practice for MCP tools
            assert schema.get("additionalProperties") is False, (
                f"Tool '{tool.name}' should have additionalProperties: false"
            )


# =============================================================================
# PREFERS BORDER COMPLIANCE
# =============================================================================

class TestPrefersBorderCompliance:
    """Verify prefersBorder field follows MCP Apps spec if present.

    The spec defines prefersBorder as an optional boolean:
    - true: Request visible border + background
    - false: Request no visible border + background
    - omitted: host decides
    """

    def test_prefers_border_is_boolean_if_present(self):
        """If prefersBorder is specified, it must be a boolean."""
        from main import get_tool_meta

        for widget in get_widgets():
            meta = get_tool_meta(widget)
            ui_meta = meta.get("ui", {})

            if "prefersBorder" in ui_meta:
                assert isinstance(ui_meta["prefersBorder"], bool), (
                    f"Widget '{widget.identifier}' prefersBorder must be a boolean"
                )

    @pytest.mark.asyncio
    async def test_resource_prefers_border_is_boolean_if_present(self):
        """Resource _meta.ui.prefersBorder must be boolean if specified."""
        for widget in get_widgets():
            result = await read_resource(widget.template_uri)
            content = result.root.contents[0]

            meta = getattr(content, '_meta', None) or getattr(content, 'meta', None)
            if meta and "ui" in meta and "prefersBorder" in meta["ui"]:
                assert isinstance(meta["ui"]["prefersBorder"], bool), (
                    f"Resource '{widget.template_uri}' prefersBorder must be boolean"
                )
