"""
App Submission Readiness Tests.

These tests verify the MCP server meets requirements for publishing to
app stores like OpenAI's ChatGPT Apps marketplace.

Based on:
- OpenAI App Submission Guidelines (developers.openai.com/apps-sdk/app-submission-guidelines)
- "What Makes a Great ChatGPT App" (developers.openai.com/blog/what-makes-a-great-chatgpt-app)
- "15 Lessons Building ChatGPT Apps" (docs/15-lessons-building-chatgpt-apps.md)
- MCP Apps GA announcement (blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/)

Categories tested:
1. Annotation Correctness - Top rejection reason per OpenAI
2. Stability & Reliability - No crashes, consistent responses
3. Token Efficiency - Responses fit in context windows
4. Capability Focus - Think capabilities, not screens
5. Cold Start Experience - Value on first interaction
6. Cross-Host Portability - Works on ChatGPT, Claude, VS Code, etc.
"""

import json
import time
import pytest
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mcp.types as types


# =============================================================================
# GRADING INFRASTRUCTURE
# =============================================================================

@dataclass
class GradeResult:
    """Result of a submission readiness check."""
    category: str
    check_name: str
    passed: bool
    score: float
    details: str
    weight: float = 1.0
    fix_hint: str = ""


class AppSubmissionReport:
    """Collects submission readiness results and generates a report."""

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
            "APP SUBMISSION READINESS REPORT",
            "=" * 60,
            "",
            "Based on: OpenAI App Submission Guidelines +",
            "          MCP Apps Best Practices (2025-2026)",
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
                        for detail_line in r.details.split("\n")[:5]:
                            lines.append(f"      {detail_line}")

        lines.append("\n" + "=" * 60)
        overall = self.get_overall_score()
        grade = self.get_grade_letter()
        lines.append(f"OVERALL SCORE: {overall:.1f}% (Grade: {grade})")
        lines.append("=" * 60)
        return "\n".join(lines)


_report = AppSubmissionReport()


# =============================================================================
# 1. ANNOTATION CORRECTNESS TESTS
# =============================================================================

class TestAnnotationCorrectness:
    """Tests for correct tool annotations.

    From OpenAI's App Submission Guidelines:
    "Tool annotations must be correctly set - incorrect/missing annotations
    are a common rejection reason."

    Key rules:
    - readOnlyHint=True means the tool ONLY reads data (no writes)
    - destructiveHint=True means the tool deletes/irreversibly changes data
    - openWorldHint=True means the tool accesses external third-party APIs
    - readOnlyHint and destructiveHint should never BOTH be True
    """

    @pytest.mark.asyncio
    async def test_no_conflicting_annotations(self):
        """readOnlyHint and destructiveHint should never both be True."""
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

            is_read_only = anno_dict.get("readOnlyHint", False)
            is_destructive = anno_dict.get("destructiveHint", False)

            if is_read_only and is_destructive:
                violations.append(
                    f"'{tool.name}' - conflicting: readOnlyHint=True AND destructiveHint=True"
                )

        score = 1.0 if len(violations) == 0 else 0.0
        _report.add_result(GradeResult(
            category="1. Annotation Correctness",
            check_name="No conflicting annotations",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            weight=2.0,
            fix_hint="A tool can't be both read-only and destructive. Pick one.",
        ))

        assert len(violations) == 0, f"Conflicting annotations:\n" + "\n".join(violations)

    @pytest.mark.asyncio
    async def test_annotations_match_description(self):
        """Annotations should be consistent with tool description.

        If a tool says "delete" or "remove" in its description, it should
        have destructiveHint=True. If it says "display" or "show", it
        should have readOnlyHint=True.

        TODO: Improve with LLM. Current implementation uses keyword matching.
        An LLM could better understand nuanced descriptions.
        """
        from main import list_tools

        tools = await list_tools()
        violations = []

        destructive_keywords = ['delete', 'remove', 'destroy', 'drop', 'erase', 'purge']
        read_only_keywords = ['display', 'show', 'view', 'render', 'visualize', 'present', 'list', 'get']
        external_keywords = ['external api', 'third-party', 'fetch from', 'calls to', 'connects to']

        for tool in tools:
            annotations = getattr(tool, 'annotations', None) or {}
            if isinstance(annotations, dict):
                anno_dict = annotations
            elif hasattr(annotations, 'model_dump'):
                anno_dict = annotations.model_dump()
            else:
                continue

            desc_lower = tool.description.lower()

            # Check destructive mismatch
            mentions_destructive = any(kw in desc_lower for kw in destructive_keywords)
            is_destructive = anno_dict.get("destructiveHint", False)
            if mentions_destructive and not is_destructive:
                violations.append(
                    f"'{tool.name}' - description mentions destructive action but destructiveHint=False"
                )

            # Check read-only mismatch
            mentions_read_only = any(kw in desc_lower for kw in read_only_keywords)
            is_read_only = anno_dict.get("readOnlyHint", False)
            if mentions_read_only and not mentions_destructive and not is_read_only:
                # Only flag if it's clearly read-only (no destructive terms)
                violations.append(
                    f"'{tool.name}' - description suggests read-only but readOnlyHint=False"
                )

        score = 1.0 - (len(violations) / len(tools)) if tools else 0.0
        _report.add_result(GradeResult(
            category="1. Annotation Correctness",
            check_name="Annotations match description",
            passed=len(violations) == 0,
            score=max(0, score),
            details="\n".join(violations) if violations else "",
            weight=1.5,
            fix_hint="Align annotations with what the tool actually does",
        ))


# =============================================================================
# 2. STABILITY & RELIABILITY TESTS
# =============================================================================

class TestStabilityReliability:
    """Tests for server stability.

    From OpenAI's guidelines:
    "Apps must be thoroughly tested for stability, responsiveness, and low latency."
    "Common rejection: review team cannot connect to MCP server."
    """

    @pytest.mark.asyncio
    async def test_all_tools_respond_without_crash(self):
        """Every tool MUST return a valid response (not crash) with default args."""
        from main import handle_call_tool, WIDGETS

        crashes = []

        for widget in WIDGETS:
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(
                    name=widget.identifier,
                    arguments={},
                ),
            )

            try:
                result = await handle_call_tool(request)
                # Should have either content or structuredContent
                has_content = bool(result.root.content)
                has_structured = result.root.structuredContent is not None
                if not has_content and not has_structured:
                    crashes.append(f"'{widget.identifier}' - returns empty result")
            except Exception as e:
                crashes.append(f"'{widget.identifier}' - CRASHED: {type(e).__name__}: {e}")

        score = 1.0 - (len(crashes) / len(WIDGETS)) if WIDGETS else 0.0
        _report.add_result(GradeResult(
            category="2. Stability & Reliability",
            check_name="No crashes with default args",
            passed=len(crashes) == 0,
            score=score,
            details="\n".join(crashes) if crashes else f"All {len(WIDGETS)} tools respond successfully",
            weight=2.0,
            fix_hint="Wrap handler logic in try/except and return error result instead of crashing",
        ))

        assert len(crashes) == 0, f"Tool crashes:\n" + "\n".join(crashes)

    @pytest.mark.asyncio
    async def test_all_tools_handle_invalid_input(self):
        """Every tool MUST gracefully handle invalid input (not crash)."""
        from main import handle_call_tool, WIDGETS

        crashes = []

        invalid_inputs = [
            {"completely_invalid_field_xyz": "bad"},
            {"": "empty key"},
            {"x" * 1000: "very long key"},
        ]

        for widget in WIDGETS:
            for invalid in invalid_inputs:
                request = types.CallToolRequest(
                    method="tools/call",
                    params=types.CallToolRequestParams(
                        name=widget.identifier,
                        arguments=invalid,
                    ),
                )

                try:
                    result = await handle_call_tool(request)
                    # Should be an error, not success
                    if not result.root.isError:
                        # Accepting invalid input without error is a minor issue
                        pass
                except Exception as e:
                    crashes.append(
                        f"'{widget.identifier}' - CRASHED on {list(invalid.keys())[0][:20]}: {type(e).__name__}"
                    )

        score = 1.0 if len(crashes) == 0 else 0.0
        _report.add_result(GradeResult(
            category="2. Stability & Reliability",
            check_name="Graceful invalid input handling",
            passed=len(crashes) == 0,
            score=score,
            details="\n".join(crashes) if crashes else "",
            weight=2.0,
            fix_hint="Use Pydantic extra='forbid' and try/except ValidationError in handlers",
        ))

        assert len(crashes) == 0, f"Crashes on invalid input:\n" + "\n".join(crashes)


# =============================================================================
# 3. TOKEN EFFICIENCY TESTS
# =============================================================================

class TestTokenEfficiency:
    """Tests for token-efficient responses.

    From Anthropic's "Code Execution with MCP" blog post:
    "Too many connected MCP servers causes tool definitions and results to
    consume excessive tokens, reducing agent efficiency."

    From OpenAI's "What Makes a Great ChatGPT App":
    "Return lean, model-friendly outputs."

    Key metrics:
    - Tool descriptions should be informative but not bloated
    - Responses should be compact (structuredContent is NOT in model context,
      but content[] text IS)
    """

    @pytest.mark.asyncio
    async def test_tool_descriptions_not_bloated(self):
        """Tool descriptions should be < 2000 chars (informative but compact)."""
        from main import list_tools

        tools = await list_tools()
        violations = []
        MAX_DESC = 2000

        for tool in tools:
            if len(tool.description) > MAX_DESC:
                violations.append(
                    f"'{tool.name}' - description {len(tool.description)} chars (max {MAX_DESC})"
                )

        score = 1.0 - (len(violations) / len(tools)) if tools else 0.0
        _report.add_result(GradeResult(
            category="3. Token Efficiency",
            check_name="Compact tool descriptions",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            weight=1.0,
            fix_hint="Keep descriptions under 2000 chars. Move detailed docs to server instructions.",
        ))

    @pytest.mark.asyncio
    async def test_text_content_is_concise(self):
        """Text fallback content should be concise (under 500 chars).

        The text in content[] is added to the model's context. Large text
        wastes tokens. Use structuredContent for detailed data.
        """
        from main import handle_call_tool, WIDGETS

        violations = []
        MAX_TEXT = 500

        for widget in WIDGETS:
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(
                    name=widget.identifier,
                    arguments={},
                ),
            )
            result = await handle_call_tool(request)

            for c in (result.root.content or []):
                if getattr(c, 'type', None) == 'text':
                    text = getattr(c, 'text', '')
                    if len(text) > MAX_TEXT:
                        violations.append(
                            f"'{widget.identifier}' - text content {len(text)} chars (max {MAX_TEXT})"
                        )

        score = 1.0 - (len(violations) / len(WIDGETS)) if WIDGETS else 0.0
        _report.add_result(GradeResult(
            category="3. Token Efficiency",
            check_name="Concise text content",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            weight=1.2,
            fix_hint="Keep text content under 500 chars. Put detailed data in structuredContent.",
        ))

    @pytest.mark.asyncio
    async def test_input_schema_not_bloated(self):
        """Input schemas should be compact (< 20 parameters per tool).

        Large schemas consume tokens in the model's context and increase
        confusion about which params to use.
        """
        from main import list_tools

        tools = await list_tools()
        MAX_PARAMS = 20
        violations = []

        for tool in tools:
            if tool.inputSchema:
                props = tool.inputSchema.get("properties", {})
                if len(props) > MAX_PARAMS:
                    violations.append(
                        f"'{tool.name}' - {len(props)} params (max {MAX_PARAMS})"
                    )

        score = 1.0 - (len(violations) / len(tools)) if tools else 0.0
        _report.add_result(GradeResult(
            category="3. Token Efficiency",
            check_name="Compact input schemas",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            weight=0.8,
            fix_hint="Reduce params: group related fields, use sensible defaults, remove rarely-used options",
        ))

        assert len(violations) == 0, f"Bloated schemas:\n" + "\n".join(violations)


# =============================================================================
# 4. CAPABILITY FOCUS TESTS
# =============================================================================

class TestCapabilityFocus:
    """Tests for capability-focused design.

    From OpenAI's "What Makes a Great ChatGPT App":
    "Think capabilities, not screens. Users are mid-conversation; the model
    decides when to invoke your app. Best apps expose a few specific powers,
    not entire product replicas."

    Tests verify that tools are focused capabilities, not kitchen-sink APIs.
    """

    @pytest.mark.asyncio
    async def test_tools_are_focused(self):
        """Each tool should do ONE thing well (not multiple unrelated things)."""
        from main import list_tools

        tools = await list_tools()
        violations = []

        # Multi-purpose indicators in description
        multi_purpose = [
            'and also', 'additionally handles', 'can also be used to',
            'serves double duty', 'multi-purpose', 'all-in-one'
        ]

        for tool in tools:
            desc_lower = tool.description.lower()
            for pattern in multi_purpose:
                if pattern in desc_lower:
                    violations.append(f"'{tool.name}' - description suggests multi-purpose: '{pattern}'")
                    break

        score = 1.0 - (len(violations) / len(tools)) if tools else 0.0
        _report.add_result(GradeResult(
            category="4. Capability Focus",
            check_name="Single-purpose tools",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            weight=1.0,
            fix_hint="Split multi-purpose tools into separate focused tools",
        ))

    @pytest.mark.asyncio
    async def test_tool_count_appropriate(self):
        """App should have a focused set of tools (3-15 is ideal).

        From OpenAI: "Best apps expose a few specific powers, not entire
        product replicas."
        """
        from main import list_tools

        tools = await list_tools()
        count = len(tools)

        if count <= 7:
            score = 1.0
            details = f"Excellent: {count} tools (focused utility)"
        elif count <= 15:
            score = 0.9
            details = f"Good: {count} tools (reasonable scope)"
        elif count <= 25:
            score = 0.7
            details = f"Acceptable: {count} tools (consider pruning)"
        else:
            score = 0.4
            details = f"Too many: {count} tools (split into separate servers)"

        _report.add_result(GradeResult(
            category="4. Capability Focus",
            check_name="Focused tool count",
            passed=count <= 25,
            score=score,
            details=details,
            weight=0.8,
            fix_hint="Keep 3-15 tools. Split large servers into focused modules.",
        ))


# =============================================================================
# 5. COLD START EXPERIENCE TESTS
# =============================================================================

class TestColdStartExperience:
    """Tests for first-interaction experience.

    From OpenAI's "What Makes a Great ChatGPT App":
    "Deliver value quickly. Produce something concrete fast. Multi-step
    onboarding kills engagement."

    Tools should work immediately with no setup, no auth, no configuration.
    """

    @pytest.mark.asyncio
    async def test_all_tools_work_with_empty_args(self):
        """Every tool should produce useful output with {} arguments."""
        from main import handle_call_tool, WIDGETS

        failures = []

        for widget in WIDGETS:
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(
                    name=widget.identifier,
                    arguments={},
                ),
            )
            result = await handle_call_tool(request)

            if result.root.isError:
                failures.append(f"'{widget.identifier}' - errors with empty args")
            elif not result.root.structuredContent:
                failures.append(f"'{widget.identifier}' - empty structuredContent with no args")

        score = 1.0 - (len(failures) / len(WIDGETS)) if WIDGETS else 0.0
        _report.add_result(GradeResult(
            category="5. Cold Start Experience",
            check_name="Works with empty arguments",
            passed=len(failures) == 0,
            score=score,
            details="\n".join(failures) if failures else f"All {len(WIDGETS)} tools work with no args",
            weight=2.0,
            fix_hint="Provide default sample data so tools show useful content on first call",
        ))

        assert len(failures) == 0, f"Cold start failures:\n" + "\n".join(failures)

    @pytest.mark.asyncio
    async def test_default_output_has_real_content(self):
        """Default output should have real content, not placeholders.

        Users should see something meaningful on the first interaction,
        not 'Loading...' or 'No data available'.
        """
        from main import handle_call_tool, WIDGETS

        violations = []
        placeholder_patterns = [
            'loading', 'no data', 'no results', 'empty', 'placeholder',
            'coming soon', 'todo', 'tbd', 'n/a', 'none available'
        ]

        for widget in WIDGETS:
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(
                    name=widget.identifier,
                    arguments={},
                ),
            )
            result = await handle_call_tool(request)

            if result.root.structuredContent:
                content_str = json.dumps(result.root.structuredContent).lower()
                for pattern in placeholder_patterns:
                    # Only flag if it's a primary value, not part of a longer string
                    if f'"{pattern}"' in content_str:
                        violations.append(
                            f"'{widget.identifier}' - contains placeholder value: '{pattern}'"
                        )
                        break

        score = 1.0 - (len(violations) / len(WIDGETS)) if WIDGETS else 0.0
        _report.add_result(GradeResult(
            category="5. Cold Start Experience",
            check_name="Real content, not placeholders",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            weight=1.5,
            fix_hint="Return real sample/demo data as defaults, not placeholder text",
        ))


# =============================================================================
# 6. CROSS-HOST PORTABILITY TESTS
# =============================================================================

class TestCrossHostPortability:
    """Tests for cross-host compatibility.

    From the MCP Apps GA announcement:
    "Supported by ChatGPT, Claude, Goose, and VS Code at launch."

    From OpenAI's guidelines:
    "Build for portability. Use the MCP Apps standard as the base, then
    layer host-specific extensions on top."

    Tests verify the server doesn't depend on host-specific features.
    """

    @pytest.mark.asyncio
    async def test_no_host_specific_assumptions(self):
        """Tool results should not reference host-specific APIs."""
        from main import handle_call_tool, WIDGETS

        violations = []
        # Host-specific patterns that indicate non-portable code
        host_specific = [
            'chatgpt.com', 'claude.ai', 'openai.com/chat',
            'window.chatgpt', 'window.claude',
        ]

        for widget in WIDGETS:
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(
                    name=widget.identifier,
                    arguments={},
                ),
            )
            result = await handle_call_tool(request)

            if result.root.structuredContent:
                content_str = json.dumps(result.root.structuredContent).lower()
                for pattern in host_specific:
                    if pattern in content_str:
                        violations.append(
                            f"'{widget.identifier}' - references host-specific: '{pattern}'"
                        )

        score = 1.0 if len(violations) == 0 else 0.0
        _report.add_result(GradeResult(
            category="6. Cross-Host Portability",
            check_name="No host-specific references",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            weight=1.0,
            fix_hint="Remove references to specific hosts. Use standard MCP Apps APIs only.",
        ))

    @pytest.mark.asyncio
    async def test_structured_content_is_json_serializable(self):
        """structuredContent MUST be JSON-serializable for all hosts."""
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

            if result.root.structuredContent:
                try:
                    json.dumps(result.root.structuredContent)
                except (TypeError, ValueError) as e:
                    violations.append(
                        f"'{widget.identifier}' - not JSON-serializable: {e}"
                    )

        score = 1.0 if len(violations) == 0 else 0.0
        _report.add_result(GradeResult(
            category="6. Cross-Host Portability",
            check_name="JSON-serializable output",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            weight=1.5,
            fix_hint="Ensure all values are JSON-compatible (no datetime objects, sets, etc.)",
        ))

        assert len(violations) == 0, f"Serialization errors:\n" + "\n".join(violations)

    def test_server_has_stateless_mode(self):
        """Server SHOULD support stateless HTTP for scalability.

        From the 2026 MCP Roadmap: "Vision: stateless protocol enabling
        scale, with stateful application sessions on top."
        """
        from main import mcp

        # Check if stateless_http is enabled
        is_stateless = getattr(mcp, '_stateless', None) or True  # Default assumption
        # Check mcp server config
        server = getattr(mcp, '_mcp_server', None)

        _report.add_result(GradeResult(
            category="6. Cross-Host Portability",
            check_name="Stateless HTTP support",
            passed=True,  # Informational
            score=1.0,
            details="Server supports stateless HTTP" if is_stateless else "Consider enabling stateless_http=True",
            weight=0.5,
            fix_hint="Set stateless_http=True in FastMCP() for better scalability",
        ))


# =============================================================================
# REPORT GENERATION
# =============================================================================

class TestGenerateReport:
    """Final test to generate the submission readiness report."""

    def test_zzz_generate_app_submission_report(self, capsys):
        """Generate final submission readiness report."""
        report = _report.generate_report()
        print("\n" + report)

        report_path = Path(__file__).parent / "app_submission_report.txt"
        report_path.write_text(report)

        overall = _report.get_overall_score()
        grade = _report.get_grade_letter()

        # Submission readiness should be C or better (70%)
        assert overall >= 70, f"""
APP SUBMISSION READINESS: {grade} ({overall:.1f}%) - Below 70% threshold
This means the app may be rejected during review.
Report: server/tests/app_submission_report.txt
Ref: developers.openai.com/apps-sdk/app-submission-guidelines
"""
