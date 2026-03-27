"""
MCP Best Practices Grading Tests.

These tests evaluate the MCP server against best practices from
docs/mcp-server-guidelines-for-ai-agents.md.

Categories tested:
1. Tool Design (naming, count, descriptions)
2. Tool Implementation (structured data, error handling)
3. Server Instructions
4. Input Validation
5. Documentation Quality
6. Anti-Patterns Detection

Each test category contributes to an overall "grade" for the server.
"""

import pytest
import re
import json
import inspect
from typing import List, Tuple, Dict, Any, Set
from dataclasses import dataclass

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel
import mcp.types as types


# =============================================================================
# GRADING INFRASTRUCTURE
# =============================================================================

@dataclass
class GradeResult:
    """Result of a grading check."""
    category: str
    check_name: str
    passed: bool
    score: float  # 0.0 to 1.0
    details: str
    weight: float = 1.0
    fix_hint: str = ""  # Actionable instruction for how to fix


class MCPBestPracticesReport:
    """Collects grading results and generates a report."""

    def __init__(self):
        self.results: List[GradeResult] = []

    def add_result(self, result: GradeResult):
        self.results.append(result)

    def get_category_score(self, category: str) -> float:
        """Get weighted score for a category (0-100%)."""
        category_results = [r for r in self.results if r.category == category]
        if not category_results:
            return 0.0

        total_weight = sum(r.weight for r in category_results)
        weighted_sum = sum(r.score * r.weight for r in category_results)
        return (weighted_sum / total_weight) * 100 if total_weight > 0 else 0.0

    def get_overall_score(self) -> float:
        """Get overall weighted score (0-100%)."""
        if not self.results:
            return 0.0

        total_weight = sum(r.weight for r in self.results)
        weighted_sum = sum(r.score * r.weight for r in self.results)
        return (weighted_sum / total_weight) * 100 if total_weight > 0 else 0.0

    def get_grade_letter(self) -> str:
        """Convert score to letter grade."""
        score = self.get_overall_score()
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"

    def generate_report(self) -> str:
        """Generate a human-readable report."""
        lines = [
            "=" * 60,
            "MCP BEST PRACTICES GRADE REPORT",
            "=" * 60,
            "",
        ]

        # Group by category
        categories: Dict[str, List[GradeResult]] = {}
        for r in self.results:
            if r.category not in categories:
                categories[r.category] = []
            categories[r.category].append(r)

        # Report each category
        for category, results in sorted(categories.items()):
            score = self.get_category_score(category)
            lines.append(f"\n{category}: {score:.1f}%")
            lines.append("-" * 40)

            for r in results:
                status = "✓" if r.passed else "✗"
                lines.append(f"  {status} {r.check_name}: {r.score*100:.0f}%")
                if not r.passed:
                    # Show fix hint first (how to fix)
                    if r.fix_hint:
                        lines.append(f"      FIX: {r.fix_hint}")
                    # Then show details (what's wrong)
                    if r.details:
                        for detail_line in r.details.split("\n"):
                            lines.append(f"      {detail_line}")

        # Overall score
        lines.append("\n" + "=" * 60)
        overall = self.get_overall_score()
        grade = self.get_grade_letter()
        lines.append(f"OVERALL SCORE: {overall:.1f}% (Grade: {grade})")
        lines.append("=" * 60)

        return "\n".join(lines)


# Global report instance for collecting results
_report = MCPBestPracticesReport()


async def _get_widget_tools():
    """Return only widget tools (with _meta.ui.resourceUri) from list_tools.
    Excludes data-only helper tools that have _meta.ui.visibility but no resourceUri."""
    from main import list_tools, WIDGETS_BY_ID
    tools = await list_tools()
    return [t for t in tools if t.name in WIDGETS_BY_ID]


def grade_check(category: str, check_name: str, weight: float = 1.0):
    """Decorator to register a grading check."""
    def decorator(func):
        func._grade_category = category
        func._grade_check_name = check_name
        func._grade_weight = weight
        return func
    return decorator


# =============================================================================
# 1. TOOL DESIGN TESTS
# =============================================================================

class TestToolNaming:
    """Tests for MCP guideline 1.3: Tool Naming Conventions.

    Use verb_noun format, lowercase with underscores.
    """

    @pytest.mark.asyncio
    async def test_tool_names_use_snake_case(self):
        """Tool names should be lowercase with underscores."""
        from main import list_tools

        tools = await list_tools()
        violations = []

        for tool in tools:
            # Check for snake_case (lowercase with underscores)
            if not re.match(r'^[a-z][a-z0-9_]*$', tool.name):
                violations.append(f"'{tool.name}' - should be lowercase with underscores")

        score = 1.0 - (len(violations) / len(tools)) if tools else 0.0
        _report.add_result(GradeResult(
            category="Tool Design",
            check_name="Snake case naming",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            fix_hint="Rename tools to use lowercase_with_underscores format (e.g., 'getUserData' -> 'get_user_data')",
        ))

        assert len(violations) == 0, f"Naming violations:\n" + "\n".join(violations)

    @pytest.mark.asyncio
    async def test_tool_names_use_verb_noun_format(self):
        """Tool names should follow verb_noun pattern (e.g., show_card, get_user)."""
        from main import list_tools

        tools = await list_tools()
        # Common verbs for MCP tools
        verbs = {'show', 'get', 'create', 'update', 'delete', 'search', 'list',
                 'find', 'fetch', 'read', 'write', 'send', 'run', 'execute', 'add',
                 'poll'}

        violations = []
        for tool in tools:
            parts = tool.name.split('_')
            if len(parts) < 2:
                violations.append(f"'{tool.name}' - should have verb_noun format")
            elif parts[0] not in verbs:
                violations.append(f"'{tool.name}' - first word '{parts[0]}' is not a common verb")

        score = 1.0 - (len(violations) / len(tools)) if tools else 0.0
        _report.add_result(GradeResult(
            category="Tool Design",
            check_name="Verb-noun format",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            fix_hint="Rename tools to verb_noun format. Use verbs: get, create, update, delete, search, list, find, show, run",
        ))

        assert len(violations) == 0, f"Format violations:\n" + "\n".join(violations)


class TestToolCount:
    """Tests for MCP guideline 1.2: Tool Count Guidelines.

    Focused utility: 3-7 tools
    Platform integration: 10-20 tools
    Enterprise gateway: 20-50 tools (must use toolset filtering)
    """

    @pytest.mark.asyncio
    async def test_tool_count_is_reasonable(self):
        """Tool count should be appropriate for server type."""
        from main import list_tools

        tools = await list_tools()
        count = len(tools)

        # For a focused utility server, 3-15 is reasonable
        # Allow up to 20 for platform integration without filtering
        if count <= 7:
            score = 1.0
            details = f"Excellent: {count} tools (focused utility range)"
        elif count <= 15:
            score = 0.9
            details = f"Good: {count} tools (small platform range)"
        elif count <= 20:
            score = 0.7
            details = f"Acceptable: {count} tools (consider toolset filtering)"
        else:
            score = 0.5
            details = f"Warning: {count} tools (should implement toolset filtering)"

        passed = count <= 20
        _report.add_result(GradeResult(
            category="Tool Design",
            check_name="Tool count",
            passed=passed,
            score=score,
            details=details,
        ))

        assert count <= 20, f"Too many tools ({count}). Consider toolset filtering for 20+ tools."


# =============================================================================
# 2. TOOL DESCRIPTIONS TESTS
# =============================================================================

class TestToolDescriptions:
    """Tests for MCP guideline 2.1: Always Provide Rich Descriptions.

    Every tool MUST have:
    - A clear description of what it does
    - When to use it (use cases)
    - All argument descriptions with types
    - Return value description with field details
    - At least one example
    """

    @pytest.mark.asyncio
    async def test_descriptions_have_minimum_length(self):
        """Widget tool descriptions should be substantial (not one-liners)."""
        tools = await _get_widget_tools()
        violations = []
        min_length = 100  # Characters

        for tool in tools:
            if len(tool.description) < min_length:
                violations.append(
                    f"'{tool.name}' - description too short ({len(tool.description)} chars, min {min_length})"
                )

        score = 1.0 - (len(violations) / len(tools)) if tools else 0.0
        _report.add_result(GradeResult(
            category="Tool Descriptions",
            check_name="Minimum description length",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            weight=0.8,
            fix_hint="Expand the tool's description in its Widget definition to at least 100 characters",
        ))

        assert len(violations) == 0, f"Short descriptions:\n" + "\n".join(violations)

    @pytest.mark.asyncio
    async def test_descriptions_include_use_cases(self):
        """Widget tool descriptions should include 'Use this tool when' section.

        TODO: Improve with LLM. Current implementation uses keyword matching for
        phrases like 'use this tool when'. An LLM could recognize semantic equivalents
        like 'Perfect for scenarios where...', 'Best used when...', 'Ideal for...'
        that convey use cases without matching these exact patterns.
        """
        tools = await _get_widget_tools()
        violations = []
        patterns = ['use this tool when', 'use this when', 'use when']

        for tool in tools:
            desc_lower = tool.description.lower()
            has_use_case = any(p in desc_lower for p in patterns)
            if not has_use_case:
                violations.append(f"'{tool.name}' - missing 'Use this tool when:' section")

        score = 1.0 - (len(violations) / len(tools)) if tools else 0.0
        _report.add_result(GradeResult(
            category="Tool Descriptions",
            check_name="Use cases documented",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            weight=1.5,
            fix_hint="Add 'Use this tool when:\\n- <scenario 1>\\n- <scenario 2>' section to each tool's description",
        ))

        assert len(violations) == 0, f"Missing use cases:\n" + "\n".join(violations)

    @pytest.mark.asyncio
    async def test_descriptions_include_args_section(self):
        """Widget tool descriptions should document arguments.

        TODO: Improve with LLM. Current implementation matches keywords like 'args:',
        'parameters:'. An LLM could recognize alternative documentation formats like
        'Input fields:', 'Accepts:', 'Takes the following:' that also document args.
        """
        tools = await _get_widget_tools()
        violations = []
        patterns = ['args:', 'arguments:', 'parameters:']

        for tool in tools:
            desc_lower = tool.description.lower()
            has_args = any(p in desc_lower for p in patterns)
            if not has_args:
                violations.append(f"'{tool.name}' - missing 'Args:' section")

        score = 1.0 - (len(violations) / len(tools)) if tools else 0.0
        _report.add_result(GradeResult(
            category="Tool Descriptions",
            check_name="Arguments documented",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            weight=1.0,
            fix_hint="Add 'Args:\\n    param_name: description of parameter' section to each tool's description",
        ))

        assert len(violations) == 0, f"Missing args:\n" + "\n".join(violations)

    @pytest.mark.asyncio
    async def test_descriptions_include_returns_section(self):
        """Widget tool descriptions should document return values.

        TODO: Improve with LLM. Current implementation matches keywords like 'returns:',
        'output:'. An LLM could recognize synonyms like 'Yields:', 'Produces:', 'Result:',
        'Outputs the following:' that also document return values.
        """
        tools = await _get_widget_tools()
        violations = []
        patterns = ['returns:', 'return value:', 'output:']

        for tool in tools:
            desc_lower = tool.description.lower()
            has_returns = any(p in desc_lower for p in patterns)
            if not has_returns:
                violations.append(f"'{tool.name}' - missing 'Returns:' section")

        score = 1.0 - (len(violations) / len(tools)) if tools else 0.0
        _report.add_result(GradeResult(
            category="Tool Descriptions",
            check_name="Return values documented",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            weight=1.0,
            fix_hint="Add 'Returns:\\n    Description of return value with field names' section to each tool's description",
        ))

        assert len(violations) == 0, f"Missing returns:\n" + "\n".join(violations)

    @pytest.mark.asyncio
    async def test_descriptions_include_example(self):
        """Widget tool descriptions should include at least one example.

        TODO: Improve with LLM. Current implementation matches keywords like 'example:',
        'e.g.'. An LLM could recognize examples shown as 'Here's how:', 'Sample usage:',
        'Try:', 'Demo:', or even inline code without explicit markers.
        """
        tools = await _get_widget_tools()
        violations = []
        patterns = ['example:', 'example usage:', 'e.g.', 'for example']

        for tool in tools:
            desc_lower = tool.description.lower()
            has_example = any(p in desc_lower for p in patterns)
            if not has_example:
                violations.append(f"'{tool.name}' - missing example")

        score = 1.0 - (len(violations) / len(tools)) if tools else 0.0
        _report.add_result(GradeResult(
            category="Tool Descriptions",
            check_name="Examples provided",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            weight=1.2,
            fix_hint="Add 'Example:\\n    tool_name(param=\"value\")' section to each tool's description",
        ))

        assert len(violations) == 0, f"Missing examples:\n" + "\n".join(violations)


# =============================================================================
# 3. STRUCTURED DATA TESTS
# =============================================================================

class TestStructuredData:
    """Tests for MCP guideline 2.2: Return Structured Data.

    Always use Pydantic models for outputs. Avoid unstructured string output.
    """

    @pytest.mark.asyncio
    async def test_tools_return_structured_content(self):
        """All tools should return structuredContent (not just text)."""
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

            if result.root.structuredContent is None:
                violations.append(f"'{widget.identifier}' - returns None structuredContent")
            elif not isinstance(result.root.structuredContent, dict):
                violations.append(f"'{widget.identifier}' - structuredContent is not a dict")

        score = 1.0 - (len(violations) / len(WIDGETS)) if WIDGETS else 0.0
        _report.add_result(GradeResult(
            category="Structured Data",
            check_name="Returns structuredContent",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            weight=2.0,
            fix_hint="In the tool handler, return types.ServerResult(types.CallToolResult(structuredContent={...}, ...))",
        ))

        assert len(violations) == 0, f"Missing structured data:\n" + "\n".join(violations)

    @pytest.mark.asyncio
    async def test_structured_content_has_meaningful_keys(self):
        """structuredContent should have descriptive keys (not generic)."""
        from main import handle_call_tool, WIDGETS

        generic_keys = {'data', 'result', 'output', 'response', 'value'}
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
                keys = set(result.root.structuredContent.keys())
                only_generic = keys.issubset(generic_keys)
                if only_generic and keys:
                    violations.append(
                        f"'{widget.identifier}' - uses only generic keys: {keys}"
                    )

        score = 1.0 - (len(violations) / len(WIDGETS)) if WIDGETS else 0.0
        _report.add_result(GradeResult(
            category="Structured Data",
            check_name="Meaningful key names",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            weight=0.8,
            fix_hint="Use descriptive keys like 'items', 'title', 'users' instead of generic 'data' or 'result'",
        ))

        assert len(violations) == 0, f"Generic keys:\n" + "\n".join(violations)


# =============================================================================
# 4. ERROR HANDLING TESTS
# =============================================================================

class TestErrorHandling:
    """Tests for MCP guideline 2.3: Handle Errors Gracefully.

    Return helpful error messages that suggest next steps.
    """

    @pytest.mark.asyncio
    async def test_invalid_input_returns_error_not_crash(self):
        """Tools should return error messages for invalid input, not crash."""
        from main import handle_call_tool, WIDGETS

        violations = []

        for widget in WIDGETS:
            # Try with an invalid extra field
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(
                    name=widget.identifier,
                    arguments={"completely_invalid_field_xyz": "bad_value"},
                ),
            )

            try:
                result = await handle_call_tool(request)
                # Should get an error result, not success
                if not result.root.isError:
                    violations.append(
                        f"'{widget.identifier}' - accepted invalid field without error"
                    )
            except Exception as e:
                violations.append(
                    f"'{widget.identifier}' - crashed instead of returning error: {type(e).__name__}"
                )

        score = 1.0 - (len(violations) / len(WIDGETS)) if WIDGETS else 0.0
        _report.add_result(GradeResult(
            category="Error Handling",
            check_name="Invalid input handling",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            weight=1.5,
            fix_hint="Wrap input validation in try/except and return isError=True with helpful message instead of raising",
        ))

        assert len(violations) == 0, f"Error handling issues:\n" + "\n".join(violations)

    @pytest.mark.asyncio
    async def test_error_messages_are_actionable(self):
        """Error messages should suggest what to do next.

        TODO: Improve with LLM. Current implementation checks for keywords like 'valid',
        'try', 'should'. An LLM could assess whether an error message is truly actionable
        by understanding if it explains the problem and guides toward a solution, regardless
        of specific wording. E.g., 'Expected integer between 1-100' is actionable without
        containing 'try' or 'should'.
        """
        from main import handle_call_tool, WIDGETS

        violations = []
        # Keywords that suggest actionable guidance
        action_keywords = ['valid', 'field', 'try', 'use', 'should', 'must', 'instead', 'expected']

        for widget in WIDGETS:
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(
                    name=widget.identifier,
                    arguments={"invalid_field_for_test": "value"},
                ),
            )

            try:
                result = await handle_call_tool(request)
                if result.root.isError:
                    error_text = result.root.content[0].text.lower()
                    has_guidance = any(kw in error_text for kw in action_keywords)
                    if not has_guidance:
                        violations.append(
                            f"'{widget.identifier}' - error message lacks actionable guidance"
                        )
            except Exception:
                pass  # Covered by previous test

        score = 1.0 - (len(violations) / len(WIDGETS)) if WIDGETS else 0.0
        _report.add_result(GradeResult(
            category="Error Handling",
            check_name="Actionable error messages",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            weight=1.0,
            fix_hint="Include 'Valid fields: ...' or 'Try using ...' in error messages to guide the user",
        ))

        assert len(violations) == 0, f"Non-actionable errors:\n" + "\n".join(violations)


# =============================================================================
# 5. SERVER INSTRUCTIONS TESTS
# =============================================================================

class TestServerInstructions:
    """Tests for MCP guideline 3: Server Instructions.

    Always provide server instructions to guide LLM behavior.
    """

    def test_server_has_instructions(self):
        """Server should have instructions defined."""
        from main import mcp

        # Check if instructions are set
        has_instructions = hasattr(mcp, '_mcp_server') and mcp._mcp_server.name
        # Check for SERVER_INSTRUCTIONS constant
        from main import SERVER_INSTRUCTIONS

        passed = bool(SERVER_INSTRUCTIONS and len(SERVER_INSTRUCTIONS.strip()) > 0)
        score = 1.0 if passed else 0.0

        _report.add_result(GradeResult(
            category="Server Instructions",
            check_name="Instructions defined",
            passed=passed,
            score=score,
            details="" if passed else "Missing SERVER_INSTRUCTIONS",
            weight=1.5,
            fix_hint="Add SERVER_INSTRUCTIONS constant and pass to FastMCP(instructions=SERVER_INSTRUCTIONS)",
        ))

        assert passed, "Server should have instructions defined"

    def test_instructions_have_tool_selection_guide(self):
        """Each widget description should include 'Use this tool when:' section."""
        from main import WIDGETS

        missing = []
        for widget in WIDGETS:
            if "use this tool when:" not in widget.description.lower():
                missing.append(widget.identifier)

        score = 1.0 - (len(missing) / len(WIDGETS)) if WIDGETS else 1.0
        passed = len(missing) == 0

        _report.add_result(GradeResult(
            category="Server Instructions",
            check_name="Tool selection guide",
            passed=passed,
            score=score,
            details=f"Missing 'Use this tool when:' in: {', '.join(missing)}" if missing else "",
            weight=1.2,
            fix_hint="Add 'Use this tool when:' section to each widget's description",
        ))

        assert passed, f"Widget descriptions missing 'Use this tool when:': {', '.join(missing)}"

    def test_instructions_mention_all_tools(self):
        """Server instructions should mention each available tool."""
        from main import SERVER_INSTRUCTIONS, WIDGETS

        instructions_lower = SERVER_INSTRUCTIONS.lower()
        missing = []

        for widget in WIDGETS:
            if widget.identifier.lower() not in instructions_lower:
                missing.append(widget.identifier)

        score = 1.0 - (len(missing) / len(WIDGETS)) if WIDGETS else 0.0
        passed = len(missing) == 0

        _report.add_result(GradeResult(
            category="Server Instructions",
            check_name="All tools documented",
            passed=passed,
            score=score,
            details=f"Missing tools: {', '.join(missing)}" if missing else "",
            weight=1.0,
            fix_hint="Add '- **tool_name**: description' entry to SERVER_INSTRUCTIONS for each missing tool",
        ))

        assert passed, f"Instructions missing tools: {missing}"


# =============================================================================
# 6. INPUT VALIDATION TESTS
# =============================================================================

class TestInputValidation:
    """Tests for MCP guideline 5.1: Input Validation."""

    def _get_input_models(self) -> List[Tuple[str, type]]:
        """Get all input models from the widget registry."""
        from main import WIDGET_INPUT_MODELS
        return [(cls.__name__, cls) for cls in WIDGET_INPUT_MODELS.values()]

    def test_all_input_models_forbid_extra(self):
        """All Pydantic input models should have extra='forbid'."""
        input_models = self._get_input_models()

        violations = []
        models_checked = len(input_models)

        for name, model in input_models:
            config = getattr(model, "model_config", {})
            if config.get("extra") != "forbid":
                violations.append(f"'{name}' - missing extra='forbid'")

        score = 1.0 - (len(violations) / models_checked) if models_checked > 0 else 1.0
        _report.add_result(GradeResult(
            category="Input Validation",
            check_name="Extra fields forbidden",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else f"Checked {models_checked} models",
            weight=1.5,
            fix_hint="Add model_config = ConfigDict(extra='forbid') to each Pydantic input model",
        ))

        assert len(violations) == 0, f"Missing extra='forbid':\n" + "\n".join(violations)

    def test_all_fields_have_defaults(self):
        """Input model fields should have defaults (for optional invocation)."""
        input_models = self._get_input_models()

        violations = []
        models_checked = len(input_models)

        for name, model in input_models:
            # Try to instantiate with no args
            try:
                instance = model()
            except Exception as e:
                violations.append(f"'{name}' - cannot instantiate with defaults: {e}")

        score = 1.0 - (len(violations) / models_checked) if models_checked > 0 else 1.0
        _report.add_result(GradeResult(
            category="Input Validation",
            check_name="Fields have defaults",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else f"Checked {models_checked} models",
            weight=1.2,
            fix_hint="Add default values to all fields: field: str = Field(default='value', ...)",
        ))

        assert len(violations) == 0, f"Missing defaults:\n" + "\n".join(violations)

    def test_fields_have_descriptions(self):
        """Input model fields should have descriptions."""
        input_models = self._get_input_models()

        violations = []
        total_fields = 0
        fields_with_desc = 0

        for name, model in input_models:
            for field_name, field_info in model.model_fields.items():
                total_fields += 1
                if field_info.description:
                    fields_with_desc += 1
                else:
                    violations.append(f"'{name}.{field_name}' - missing description")

        score = fields_with_desc / total_fields if total_fields > 0 else 1.0
        _report.add_result(GradeResult(
            category="Input Validation",
            check_name="Field descriptions",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations[:5]) + (f"\n... and {len(violations)-5} more" if len(violations) > 5 else "") if violations else f"All {total_fields} fields documented",
            weight=0.8,
            fix_hint="Add description to each field: field: str = Field(default='x', description='What this field does')",
        ))

        assert len(violations) == 0, f"Missing field descriptions:\n" + "\n".join(violations)


# =============================================================================
# 7. ANTI-PATTERNS TESTS
# =============================================================================

class TestAntiPatterns:
    """Tests for MCP guideline 8: Anti-Patterns to Avoid."""

    @pytest.mark.asyncio
    async def test_no_vague_descriptions(self):
        """Tool descriptions should not be vague (Anti-Pattern 3).

        TODO: Improve with LLM. Current implementation only catches a few exact vague
        patterns like 'Process data' or 'Handle input'. An LLM could assess vagueness
        semantically - recognizing that 'Manages information according to rules' is
        vague while 'Converts CSV files to JSON format' is specific, regardless of
        whether they match predefined regex patterns.
        """
        from main import list_tools

        tools = await list_tools()
        vague_patterns = [
            r'^process(es)? (the )?data\.?$',
            r'^handle(s)? (the )?input\.?$',
            r'^do(es)? (the )?(task|operation|action)\.?$',
            r'^run(s)?\.?$',
            r'^execute(s)?\.?$',
        ]

        violations = []
        for tool in tools:
            desc_lower = tool.description.lower().strip()
            for pattern in vague_patterns:
                if re.match(pattern, desc_lower, re.IGNORECASE):
                    violations.append(f"'{tool.name}' - vague description: '{tool.description[:50]}'")
                    break

        score = 1.0 - (len(violations) / len(tools)) if tools else 0.0
        _report.add_result(GradeResult(
            category="Anti-Patterns",
            check_name="No vague descriptions",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            fix_hint="Replace vague descriptions like 'Process data' with specific ones: 'Search for users by email or username'",
        ))

        assert len(violations) == 0, f"Vague descriptions:\n" + "\n".join(violations)

    # NOTE: We intentionally removed the "no overlapping tools" test.
    # The original heuristic (checking if tools share a verb like "show_")
    # was flawed - it penalized good naming conventions (show_card, show_list)
    # rather than detecting actual functional overlap.
    # Detecting true overlap would require semantic analysis of descriptions,
    # which cannot be reliably automated.

    @pytest.mark.asyncio
    async def test_no_generic_error_messages(self):
        """Error messages should not be generic like 'Error' (Anti-Pattern 4)."""
        from main import handle_call_tool, WIDGETS

        generic_errors = ['error', 'failed', 'invalid', 'bad request']
        violations = []

        for widget in WIDGETS:
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(
                    name=widget.identifier,
                    arguments={"invalid_test_field": "value"},
                ),
            )

            try:
                result = await handle_call_tool(request)
                if result.root.isError:
                    error_text = result.root.content[0].text.strip().lower()
                    # Check if error message is just a single generic word
                    if error_text in generic_errors:
                        violations.append(f"'{widget.identifier}' - generic error: '{error_text}'")
            except Exception:
                pass

        score = 1.0 - (len(violations) / len(WIDGETS)) if WIDGETS else 0.0
        _report.add_result(GradeResult(
            category="Anti-Patterns",
            check_name="No generic errors",
            passed=len(violations) == 0,
            score=score,
            details="\n".join(violations) if violations else "",
            fix_hint="Return detailed errors: 'Invalid field \"foo\". Valid fields: title, message. Example: {\"title\": \"Hello\"}'",
        ))

        assert len(violations) == 0, f"Generic errors:\n" + "\n".join(violations)


# =============================================================================
# REPORT GENERATION
# =============================================================================

class TestGenerateReport:
    """Final test to generate and display the grade report."""

    def test_generate_grade_report(self, capsys):
        """Generate final grade report."""
        # This test runs last (alphabetically after all others)
        # Print the full report
        report = _report.generate_report()
        print("\n" + report)

        # Also write to a file for CI/CD
        report_path = Path(__file__).parent / "mcp_best_practices_report.txt"
        report_path.write_text(report)

        # Check overall grade
        overall = _report.get_overall_score()
        grade = _report.get_grade_letter()

        # Pass if grade is C or better
        assert overall >= 70, f"MCP Best Practices Grade: {grade} ({overall:.1f}%) - needs improvement"
