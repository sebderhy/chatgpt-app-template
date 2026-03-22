"""
MCP Apps Protocol Compliance Tests (SEP-1865).

These tests verify that the MCP server conforms to the MCP Apps protocol
specification (SEP-1865, stable version 2026-01-26).

Unlike the "best practices" and "guidelines" tests which are aspirational
grading, these tests enforce HARD compliance requirements. A tool that
fails these tests will not work correctly in MCP Apps hosts (ChatGPT,
Claude, VS Code, Goose, etc.).

Categories tested:
1. Resource Registration - ui:// scheme, MIME type, CSP domains
2. Tool-UI Linkage - _meta.ui.resourceUri, nested structure
3. Tool Visibility - visibility array for model/app routing
4. Tool Annotations - readOnlyHint, destructiveHint, openWorldHint
5. CSP Completeness - All four domain lists present
6. Text Fallback - content[] provided alongside structuredContent
7. Invocation Metadata - _meta in tool results

References:
- docs/mcp-apps-specs.mdx (SEP-1865 stable, 2026-01-26)
- docs/mcp-apps-docs.md (MCP Apps overview)
- https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/
"""

import json
import pytest
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Set
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mcp.types as types


# =============================================================================
# GRADING INFRASTRUCTURE
# =============================================================================

@dataclass
class GradeResult:
    """Result of a compliance check."""
    category: str
    check_name: str
    passed: bool
    score: float  # 0.0 to 1.0
    details: str
    weight: float = 1.0
    fix_hint: str = ""


class ProtocolComplianceReport:
    """Collects compliance results and generates a report."""

    def __init__(self):
        self.results: List[GradeResult] = []

    def add_result(self, result: GradeResult):
        self.results.append(result)

    def get_category_score(self, category: str) -> float:
        category_results = [r for r in self.results if r.category == category]
        if not category_results:
            return 0.0
        total_weight = sum(r.weight for r in category_results)
        weighted_sum = sum(r.score * r.weight for r in category_results)
        return (weighted_sum / total_weight) * 100 if total_weight > 0 else 0.0

    def get_overall_score(self) -> float:
        if not self.results:
            return 0.0
        total_weight = sum(r.weight for r in self.results)
        weighted_sum = sum(r.score * r.weight for r in self.results)
        return (weighted_sum / total_weight) * 100 if total_weight > 0 else 0.0

    def get_grade_letter(self) -> str:
        score = self.get_overall_score()
        if score >= 90: return "A"
        elif score >= 80: return "B"
        elif score >= 70: return "C"
        elif score >= 60: return "D"
        else: return "F"

    def generate_report(self) -> str:
        lines = [
            "=" * 60,
            "MCP APPS PROTOCOL COMPLIANCE REPORT",
            "=" * 60,
            "",
            "Spec: SEP-1865 (stable, 2026-01-26)",
            "",
        ]

        categories: Dict[str, List[GradeResult]] = {}
        for r in self.results:
            categories.setdefault(r.category, []).append(r)

        for category, results in sorted(categories.items()):
            score = self.get_category_score(category)
            lines.append(f"\n{category}: {score:.1f}%")
            lines.append("-" * 40)
            for r in results:
                status = "\u2713" if r.passed else "\u2717"
                lines.append(f"  {status} {r.check_name}: {r.score*100:.0f}%")
                if not r.passed:
                    if r.fix_hint:
                        lines.append(f"      FIX: {r.fix_hint}")
                    if r.details:
                        for detail_line in r.details.split("\n"):
                            lines.append(f"      {detail_line}")

        lines.append("\n" + "=" * 60)
        overall = self.get_overall_score()
        grade = self.get_grade_letter()
        lines.append(f"OVERALL SCORE: {overall:.1f}% (Grade: {grade})")
        lines.append("=" * 60)
        return "\n".join(lines)


_report = ProtocolComplianceReport()


# =============================================================================
# 1. RESOURCE REGISTRATION TESTS
# =============================================================================

class TestResourceRegistration:
    """Tests that UI resources are correctly registered per SEP-1865.

    MCP Apps resources MUST:
    - Use the ui:// URI scheme
    - Have MIME type text/html;profile=mcp-app
    - Include _meta.ui with CSP configuration
    """

    @pytest.mark.asyncio
    async def test_resources_use_ui_scheme(self):
        """All UI resources MUST use the ui:// URI scheme."""
        from main import list_resources

        resources = await list_resources()
        violations = []

        for resource in resources:
            uri = str(resource.uri)
            if not uri.startswith("ui://"):
                violations.append(f"'{resource.name}' - URI '{uri}' does not use ui:// scheme")

        score = 1.0 - (len(violations) / len(resources)) if resources else 0.0
        _report.add_result(GradeResult(
            category="1. Resource Registration",
            check_name="ui:// URI scheme",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else f"All {len(resources)} resources use ui:// scheme",
            weight=2.0,
            fix_hint="Set template_uri='ui://widget/my-widget.html' in Widget definition",
        ))

        assert len(violations) == 0, f"URI scheme violations:\n" + "\n".join(violations)

    @pytest.mark.asyncio
    async def test_resources_have_correct_mime_type(self):
        """All UI resources MUST have MIME type text/html;profile=mcp-app."""
        from main import list_resources

        resources = await list_resources()
        expected_mime = "text/html;profile=mcp-app"
        violations = []

        for resource in resources:
            if resource.mimeType != expected_mime:
                violations.append(
                    f"'{resource.name}' - MIME '{resource.mimeType}' should be '{expected_mime}'"
                )

        score = 1.0 - (len(violations) / len(resources)) if resources else 0.0
        _report.add_result(GradeResult(
            category="1. Resource Registration",
            check_name="MCP App MIME type",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            weight=2.0,
            fix_hint="Set MIME_TYPE = 'text/html;profile=mcp-app' in _base.py",
        ))

        assert len(violations) == 0, f"MIME type violations:\n" + "\n".join(violations)

    @pytest.mark.asyncio
    async def test_resources_have_meta_ui(self):
        """Resources MUST have _meta.ui with CSP configuration."""
        from main import list_resources

        resources = await list_resources()
        violations = []

        for resource in resources:
            meta = getattr(resource, '_meta', None) or getattr(resource, 'meta', None)
            if not meta:
                violations.append(f"'{resource.name}' - missing _meta")
                continue

            ui_meta = meta.get("ui") if isinstance(meta, dict) else None
            if not ui_meta:
                violations.append(f"'{resource.name}' - missing _meta.ui")
                continue

            if "csp" not in ui_meta:
                violations.append(f"'{resource.name}' - missing _meta.ui.csp")

        score = 1.0 - (len(violations) / len(resources)) if resources else 0.0
        _report.add_result(GradeResult(
            category="1. Resource Registration",
            check_name="Resource _meta.ui present",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            weight=1.5,
            fix_hint="Return _meta={'ui': {'csp': get_csp_domains(), ...}} in list_resources",
        ))

        assert len(violations) == 0, f"Resource meta violations:\n" + "\n".join(violations)


# =============================================================================
# 2. TOOL-UI LINKAGE TESTS
# =============================================================================

class TestToolUILinkage:
    """Tests that tools are correctly linked to UI resources.

    Per SEP-1865, tools MUST use the nested _meta.ui structure:
    - _meta.ui.resourceUri (NOT the deprecated _meta["ui/resourceUri"])
    - _meta.ui.csp for Content Security Policy
    """

    @pytest.mark.asyncio
    async def test_tools_have_nested_meta_ui(self):
        """Widget tools MUST use nested _meta.ui.resourceUri (not flat format)."""
        from main import list_tools, WIDGETS_BY_ID

        tools = await list_tools()
        violations = []
        widget_tools = 0

        for tool in tools:
            # Skip data-only tools — they have _meta.ui.visibility but no resourceUri
            if tool.name not in WIDGETS_BY_ID:
                continue

            meta = getattr(tool, '_meta', None) or getattr(tool, 'meta', None)
            if not meta or not isinstance(meta, dict):
                continue

            # Check for deprecated flat format
            if "ui/resourceUri" in meta:
                violations.append(
                    f"'{tool.name}' - uses deprecated flat _meta['ui/resourceUri'], use _meta.ui.resourceUri"
                )
                widget_tools += 1
                continue

            ui_meta = meta.get("ui")
            if ui_meta and isinstance(ui_meta, dict):
                widget_tools += 1
                if "resourceUri" not in ui_meta:
                    violations.append(f"'{tool.name}' - _meta.ui missing 'resourceUri'")

        score = 1.0 - (len(violations) / widget_tools) if widget_tools else 0.0
        _report.add_result(GradeResult(
            category="2. Tool-UI Linkage",
            check_name="Nested _meta.ui structure",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else f"All {widget_tools} tools use _meta.ui.resourceUri",
            weight=2.0,
            fix_hint="Use _meta={'ui': {'resourceUri': 'ui://...', 'csp': {...}}} (nested, not flat)",
        ))

        assert len(violations) == 0, f"Meta structure violations:\n" + "\n".join(violations)

    @pytest.mark.asyncio
    async def test_tool_resource_uris_are_registered(self):
        """Every tool's _meta.ui.resourceUri MUST match a registered resource."""
        from main import list_tools, list_resources

        tools = await list_tools()
        resources = await list_resources()

        registered_uris = {str(r.uri) for r in resources}
        violations = []

        for tool in tools:
            meta = getattr(tool, '_meta', None) or getattr(tool, 'meta', None)
            if not meta or not isinstance(meta, dict):
                continue
            ui_meta = meta.get("ui", {})
            resource_uri = ui_meta.get("resourceUri")
            if resource_uri and resource_uri not in registered_uris:
                violations.append(
                    f"'{tool.name}' - resourceUri '{resource_uri}' not in registered resources"
                )

        score = 1.0 if len(violations) == 0 else 0.0
        _report.add_result(GradeResult(
            category="2. Tool-UI Linkage",
            check_name="ResourceURIs match resources",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            weight=1.5,
            fix_hint="Ensure each tool's template_uri matches a Widget registered in the server",
        ))

        assert len(violations) == 0, f"Unregistered resource URIs:\n" + "\n".join(violations)


# =============================================================================
# 3. TOOL VISIBILITY TESTS
# =============================================================================

class TestToolVisibility:
    """Tests for tool visibility control (SEP-1865).

    The visibility array controls who can see and call a tool:
    - ["model", "app"] (default): Both model and widgets can call it
    - ["model"]: Only the model can call it (hidden from widget callTool)
    - ["app"]: Only widgets can call it (hidden from model tool list)

    Data-only helper tools (no UI) SHOULD have visibility=["app"] so the
    model doesn't try to call them directly.
    """

    @pytest.mark.asyncio
    async def test_widget_tools_have_visibility(self):
        """Widget tools SHOULD declare visibility in _meta.ui."""
        from main import list_tools

        tools = await list_tools()
        violations = []
        widget_tools = 0

        for tool in tools:
            meta = getattr(tool, '_meta', None) or getattr(tool, 'meta', None)
            if not meta or not isinstance(meta, dict):
                continue
            ui_meta = meta.get("ui", {})
            if "resourceUri" in ui_meta:
                widget_tools += 1
                if "visibility" not in ui_meta:
                    violations.append(f"'{tool.name}' - missing _meta.ui.visibility")

        score = 1.0 - (len(violations) / widget_tools) if widget_tools else 0.0
        _report.add_result(GradeResult(
            category="3. Tool Visibility",
            check_name="Widget tools declare visibility",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else f"All {widget_tools} widget tools have visibility",
            weight=1.5,
            fix_hint="Add 'visibility': ['model', 'app'] to _meta.ui in get_tool_meta()",
        ))

        assert len(violations) == 0, f"Missing visibility:\n" + "\n".join(violations)

    @pytest.mark.asyncio
    async def test_data_only_tools_have_app_visibility(self):
        """Data-only tools (no UI) SHOULD have visibility=['app'].

        This prevents the model from calling helper tools directly, which
        would fail because they don't produce visual output.
        """
        from main import list_tools, WIDGETS_BY_ID

        tools = await list_tools()
        violations = []
        data_tools = 0

        for tool in tools:
            # Skip widget tools
            if tool.name in WIDGETS_BY_ID:
                continue

            data_tools += 1
            meta = getattr(tool, '_meta', None) or getattr(tool, 'meta', None)

            if not meta or not isinstance(meta, dict):
                violations.append(f"'{tool.name}' - data-only tool missing _meta with visibility")
                continue

            ui_meta = meta.get("ui", {})
            visibility = ui_meta.get("visibility", [])
            if "model" in visibility:
                violations.append(
                    f"'{tool.name}' - data-only tool should have visibility=['app'], not {visibility}"
                )

        if data_tools == 0:
            score = 1.0
        else:
            score = 1.0 - (len(violations) / data_tools)

        _report.add_result(GradeResult(
            category="3. Tool Visibility",
            check_name="Data-only tools hidden from model",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else f"All {data_tools} data-only tools have visibility=['app']" if data_tools else "No data-only tools",
            weight=1.2,
            fix_hint="Add _meta={'ui': {'visibility': ['app']}} to data-only tool definitions",
        ))

    @pytest.mark.asyncio
    async def test_visibility_values_are_valid(self):
        """Visibility arrays must contain only 'model' and/or 'app'."""
        from main import list_tools

        tools = await list_tools()
        valid_values = {"model", "app"}
        violations = []
        checked = 0

        for tool in tools:
            meta = getattr(tool, '_meta', None) or getattr(tool, 'meta', None)
            if not meta or not isinstance(meta, dict):
                continue
            ui_meta = meta.get("ui", {})
            visibility = ui_meta.get("visibility")
            if visibility is not None:
                checked += 1
                if not isinstance(visibility, list):
                    violations.append(f"'{tool.name}' - visibility must be a list, got {type(visibility).__name__}")
                elif not all(v in valid_values for v in visibility):
                    invalid = [v for v in visibility if v not in valid_values]
                    violations.append(f"'{tool.name}' - invalid visibility values: {invalid}")

        score = 1.0 - (len(violations) / checked) if checked else 1.0
        _report.add_result(GradeResult(
            category="3. Tool Visibility",
            check_name="Valid visibility values",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            weight=1.0,
            fix_hint="Use only ['model'], ['app'], or ['model', 'app'] for visibility",
        ))

        assert len(violations) == 0, f"Invalid visibility values:\n" + "\n".join(violations)


# =============================================================================
# 4. TOOL ANNOTATIONS TESTS
# =============================================================================

class TestToolAnnotations:
    """Tests for tool annotations (required for MCP Apps hosts).

    Per the MCP spec and OpenAI App Submission Guidelines, every tool MUST
    declare these annotations:
    - readOnlyHint: Does this tool only read data?
    - destructiveHint: Does this tool delete or irreversibly modify data?
    - openWorldHint: Does this tool access external/third-party services?

    Incorrect annotations are a TOP REJECTION REASON for ChatGPT Apps.
    """

    @pytest.mark.asyncio
    async def test_all_tools_have_annotations(self):
        """Every tool MUST have readOnlyHint, destructiveHint, and openWorldHint."""
        from main import list_tools

        tools = await list_tools()
        required_annotations = {"readOnlyHint", "destructiveHint", "openWorldHint"}
        violations = []

        for tool in tools:
            annotations = getattr(tool, 'annotations', None) or {}
            if isinstance(annotations, dict):
                missing = required_annotations - set(annotations.keys())
            else:
                # Pydantic model annotations
                anno_dict = annotations.model_dump() if hasattr(annotations, 'model_dump') else {}
                present = {k for k, v in anno_dict.items() if v is not None}
                missing = required_annotations - present

            if missing:
                violations.append(f"'{tool.name}' - missing annotations: {missing}")

        score = 1.0 - (len(violations) / len(tools)) if tools else 0.0
        _report.add_result(GradeResult(
            category="4. Tool Annotations",
            check_name="Required annotations present",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else f"All {len(tools)} tools have annotations",
            weight=2.0,
            fix_hint="Add annotations={'readOnlyHint': True, 'destructiveHint': False, 'openWorldHint': False} to Tool()",
        ))

        assert len(violations) == 0, f"Missing annotations:\n" + "\n".join(violations)

    @pytest.mark.asyncio
    async def test_annotations_are_boolean(self):
        """Annotation values MUST be boolean (not strings or None)."""
        from main import list_tools

        tools = await list_tools()
        violations = []

        for tool in tools:
            annotations = getattr(tool, 'annotations', None) or {}
            if isinstance(annotations, dict):
                anno_dict = annotations
            elif hasattr(annotations, 'model_dump'):
                anno_dict = annotations.model_dump()
            else:
                continue

            for key in ["readOnlyHint", "destructiveHint", "openWorldHint"]:
                val = anno_dict.get(key)
                if val is not None and not isinstance(val, bool):
                    violations.append(f"'{tool.name}.{key}' - value {val!r} is not boolean")

        score = 1.0 if len(violations) == 0 else 0.0
        _report.add_result(GradeResult(
            category="4. Tool Annotations",
            check_name="Annotations are boolean",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            weight=1.0,
            fix_hint="Use True/False, not strings: 'readOnlyHint': True",
        ))

        assert len(violations) == 0, f"Non-boolean annotations:\n" + "\n".join(violations)

    @pytest.mark.asyncio
    async def test_show_tools_are_read_only(self):
        """Display tools (show_*) SHOULD be marked readOnlyHint=True.

        Show/display tools don't modify state, so they should be read-only.
        This helps hosts like ChatGPT auto-approve the tool call.
        """
        from main import list_tools

        tools = await list_tools()
        violations = []
        show_tools = 0

        for tool in tools:
            if tool.name.startswith("show_"):
                show_tools += 1
                annotations = getattr(tool, 'annotations', None) or {}
                if isinstance(annotations, dict):
                    anno_dict = annotations
                elif hasattr(annotations, 'model_dump'):
                    anno_dict = annotations.model_dump()
                else:
                    anno_dict = {}

                if not anno_dict.get("readOnlyHint", False):
                    violations.append(f"'{tool.name}' - show_ tool should have readOnlyHint=True")
                if anno_dict.get("destructiveHint", False):
                    violations.append(f"'{tool.name}' - show_ tool should NOT have destructiveHint=True")

        score = 1.0 - (len(violations) / show_tools) if show_tools else 1.0
        _report.add_result(GradeResult(
            category="4. Tool Annotations",
            check_name="Show tools are read-only",
            passed=len(violations) == 0,
            score=max(0, score),
            details="\n".join(violations) if violations else f"All {show_tools} show_ tools marked read-only",
            weight=1.5,
            fix_hint="Set read_only=True in Widget() or annotations={'readOnlyHint': True} in Tool()",
        ))

        assert len(violations) == 0, f"Annotation mismatch:\n" + "\n".join(violations)


# =============================================================================
# 5. CSP COMPLETENESS TESTS
# =============================================================================

class TestCSPCompleteness:
    """Tests for Content Security Policy configuration.

    SEP-1865 stable spec defines four CSP domain lists:
    - resourceDomains: For scripts, styles, images, fonts
    - connectDomains: For fetch/XHR requests
    - frameDomains: For nested iframes
    - baseUriDomains: For base URI resolution

    All four SHOULD be present (empty lists are fine for unused categories).
    """

    @pytest.mark.asyncio
    async def test_csp_has_all_domain_lists(self):
        """CSP configuration SHOULD include all four domain lists."""
        from main import list_tools

        tools = await list_tools()
        required_lists = {"resourceDomains", "connectDomains", "frameDomains", "baseUriDomains"}
        violations = []
        checked = 0

        for tool in tools:
            meta = getattr(tool, '_meta', None) or getattr(tool, 'meta', None)
            if not meta or not isinstance(meta, dict):
                continue
            ui_meta = meta.get("ui", {})
            csp = ui_meta.get("csp")
            if not csp:
                continue

            checked += 1
            if isinstance(csp, dict):
                missing = required_lists - set(csp.keys())
                if missing:
                    violations.append(f"'{tool.name}' - CSP missing: {missing}")

        score = 1.0 - (len(violations) / checked) if checked else 0.0
        _report.add_result(GradeResult(
            category="5. CSP Completeness",
            check_name="All four CSP domain lists",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else f"All {checked} tools have complete CSP",
            weight=1.5,
            fix_hint="Add frameDomains: [] and baseUriDomains: [origin] to get_csp_domains()",
        ))

        assert len(violations) == 0, f"Incomplete CSP:\n" + "\n".join(violations)

    @pytest.mark.asyncio
    async def test_csp_resource_domains_include_server(self):
        """CSP resourceDomains MUST include the server's own origin."""
        from main import list_tools
        from widgets._base import get_base_url

        tools = await list_tools()
        base_url = get_base_url()
        parsed = urlparse(base_url)
        server_origin = f"{parsed.scheme}://{parsed.netloc}"

        violations = []
        checked = 0

        for tool in tools:
            meta = getattr(tool, '_meta', None) or getattr(tool, 'meta', None)
            if not meta or not isinstance(meta, dict):
                continue
            ui_meta = meta.get("ui", {})
            csp = ui_meta.get("csp", {})
            resource_domains = csp.get("resourceDomains", [])
            if resource_domains:
                checked += 1
                if server_origin not in resource_domains:
                    violations.append(
                        f"'{tool.name}' - resourceDomains missing server origin '{server_origin}'"
                    )

        score = 1.0 - (len(violations) / checked) if checked else 0.0
        _report.add_result(GradeResult(
            category="5. CSP Completeness",
            check_name="Server origin in resourceDomains",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            weight=1.0,
            fix_hint="Include server origin in resourceDomains for self-hosted assets",
        ))

        assert len(violations) == 0, f"Missing server origin:\n" + "\n".join(violations)


# =============================================================================
# 6. TEXT FALLBACK TESTS
# =============================================================================

class TestTextFallback:
    """Tests for text-only fallback (portability).

    Per SEP-1865 and the "Build for portability" best practice, tools MUST
    provide text content alongside structuredContent. Hosts that don't support
    MCP Apps will only see the text content array.

    This is a TOP REJECTION REASON: if your tool only returns structuredContent
    without text content, it breaks on non-UI hosts.
    """

    @pytest.mark.asyncio
    async def test_tools_have_text_content(self):
        """Tool results MUST include content[] with TextContent for non-UI hosts."""
        from main import handle_call_tool, WIDGETS

        violations = []

        for widget in WIDGETS:
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(
                    name=widget.identifier,
                    arguments={},
                ),
            )
            result = await handle_call_tool(request)

            content = result.root.content
            if not content:
                violations.append(f"'{widget.identifier}' - missing content[] (no text fallback)")
            else:
                has_text = any(
                    getattr(c, 'type', None) == 'text' and getattr(c, 'text', '').strip()
                    for c in content
                )
                if not has_text:
                    violations.append(f"'{widget.identifier}' - content[] has no non-empty TextContent")

        score = 1.0 - (len(violations) / len(WIDGETS)) if WIDGETS else 0.0
        _report.add_result(GradeResult(
            category="6. Text Fallback",
            check_name="Text content for non-UI hosts",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else f"All {len(WIDGETS)} tools provide text fallback",
            weight=2.0,
            fix_hint="Include content=[types.TextContent(type='text', text='Summary...')] in CallToolResult",
        ))

        assert len(violations) == 0, f"Missing text fallback:\n" + "\n".join(violations)

    @pytest.mark.asyncio
    async def test_text_content_is_meaningful(self):
        """Text fallback should be a meaningful summary, not just 'OK' or the tool name."""
        from main import handle_call_tool, WIDGETS

        violations = []
        trivial_responses = {'ok', 'success', 'done', 'ready', 'loaded', ''}

        for widget in WIDGETS:
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(
                    name=widget.identifier,
                    arguments={},
                ),
            )
            result = await handle_call_tool(request)

            content = result.root.content
            if content:
                for c in content:
                    if getattr(c, 'type', None) == 'text':
                        text = getattr(c, 'text', '').strip().lower()
                        if text in trivial_responses:
                            violations.append(
                                f"'{widget.identifier}' - trivial text content: '{text}'"
                            )
                        elif len(text) < 10:
                            violations.append(
                                f"'{widget.identifier}' - text content too short ({len(text)} chars)"
                            )

        score = 1.0 - (len(violations) / len(WIDGETS)) if WIDGETS else 0.0
        _report.add_result(GradeResult(
            category="6. Text Fallback",
            check_name="Meaningful text summary",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            weight=1.0,
            fix_hint="Return a useful summary: 'Carousel with 5 items: Photo Gallery' not just 'OK'",
        ))

        # Soft check - contributes to grade but doesn't fail
        # assert len(violations) == 0


# =============================================================================
# 7. INVOCATION METADATA TESTS
# =============================================================================

class TestInvocationMetadata:
    """Tests for tool invocation result metadata.

    Per SEP-1865, tool results SHOULD include _meta.ui with:
    - resourceUri: Links result to the UI resource for rendering
    - csp: CSP domains for the sandbox
    """

    @pytest.mark.asyncio
    async def test_results_have_meta_ui(self):
        """Tool results SHOULD include _meta.ui.resourceUri for rendering."""
        from main import handle_call_tool, WIDGETS

        violations = []

        for widget in WIDGETS:
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(
                    name=widget.identifier,
                    arguments={},
                ),
            )
            result = await handle_call_tool(request)

            meta = getattr(result.root, '_meta', None) or getattr(result.root, 'meta', None)
            if not meta:
                violations.append(f"'{widget.identifier}' - result missing _meta")
                continue

            ui_meta = meta.get("ui") if isinstance(meta, dict) else None
            if not ui_meta:
                violations.append(f"'{widget.identifier}' - result missing _meta.ui")
            elif "resourceUri" not in ui_meta:
                violations.append(f"'{widget.identifier}' - result _meta.ui missing resourceUri")

        score = 1.0 - (len(violations) / len(WIDGETS)) if WIDGETS else 0.0
        _report.add_result(GradeResult(
            category="7. Invocation Metadata",
            check_name="Result _meta.ui.resourceUri",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            weight=1.5,
            fix_hint="Include _meta=get_invocation_meta(widget) in CallToolResult",
        ))

        assert len(violations) == 0, f"Missing result metadata:\n" + "\n".join(violations)


# =============================================================================
# 8. PREFERS BORDER TESTS
# =============================================================================

class TestPrefersBorder:
    """Tests for the prefersBorder UI preference (SEP-1865 stable).

    The prefersBorder field hints to hosts about whether the widget
    should have a visual boundary (border/shadow). This is optional
    but recommended for a polished appearance.
    """

    @pytest.mark.asyncio
    async def test_tools_declare_prefers_border(self):
        """Widget tools SHOULD declare prefersBorder in _meta.ui."""
        from main import list_tools

        tools = await list_tools()
        violations = []
        widget_tools = 0

        for tool in tools:
            meta = getattr(tool, '_meta', None) or getattr(tool, 'meta', None)
            if not meta or not isinstance(meta, dict):
                continue
            ui_meta = meta.get("ui", {})
            if "resourceUri" not in ui_meta:
                continue

            widget_tools += 1
            if "prefersBorder" not in ui_meta:
                violations.append(f"'{tool.name}' - missing _meta.ui.prefersBorder")

        score = 1.0 - (len(violations) / widget_tools) if widget_tools else 0.0
        _report.add_result(GradeResult(
            category="8. UI Preferences",
            check_name="prefersBorder declared",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else f"All {widget_tools} tools declare prefersBorder",
            weight=0.5,
            fix_hint="Add 'prefersBorder': True to _meta.ui in get_tool_meta()",
        ))

        # Soft check
        # assert len(violations) == 0


# =============================================================================
# REPORT GENERATION
# =============================================================================

class TestGenerateReport:
    """Final test to generate the compliance report."""

    def test_zzz_generate_protocol_compliance_report(self, capsys):
        """Generate final compliance report (zzz_ prefix ensures it runs last)."""
        report = _report.generate_report()
        print("\n" + report)

        report_path = Path(__file__).parent / "protocol_compliance_report.txt"
        report_path.write_text(report)

        overall = _report.get_overall_score()
        grade = _report.get_grade_letter()

        # Protocol compliance must be B or better (80%)
        assert overall >= 80, f"""
PROTOCOL COMPLIANCE: {grade} ({overall:.1f}%) - Below 80% threshold
This means the server does not fully comply with SEP-1865.
Report: server/tests/protocol_compliance_report.txt
Spec: docs/mcp-apps-specs.mdx
"""
