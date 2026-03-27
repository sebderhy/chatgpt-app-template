# AGENTS.md

MCP App template: React widgets + Python MCP server. Build once, run on Claude, ChatGPT, VS Code, Goose, and other MCP hosts.

## Quick Start (Follow These Steps)

### 1. Setup and Verify
```bash
./setup.sh   # Installs deps, builds, runs tests — must pass before continuing
```

### 2. Understand the Framework
Read in this order:
- `README.md` — What MCP Apps are, why this template exists
- `docs/widget-development.md` — Hook APIs and widget patterns

### 3. Review Examples (By Complexity)

Start with simpler examples and progress to advanced ones as needed:

| Complexity | Widget | Description | Key Concepts |
|------------|--------|-------------|--------------|
| **Beginner** | `list` | Simple list display | Basic props, theme support |
| **Beginner** | `qr` | QR code generator | Single input, canvas rendering |
| **Intermediate** | `carousel` | Image slideshow | State management, navigation |
| **Intermediate** | `gallery` | Image grid | Grid layout, responsive design |
| **Intermediate** | `dashboard` | Stats cards | Multiple data types, layout |
| **Advanced** | `scenario-modeler` | Interactive charts | Chart.js, complex data |
| **Advanced** | `solar-system` | 3D visualization | Three.js, animation loops |
| **Advanced** | `map` | Interactive maps | External APIs (Leaflet), geocoding |

**Recommended starting point**: Examine the `carousel` widget:
- **Frontend**: `src/carousel/index.tsx` (entry) + `src/carousel/App.tsx` (component)
- **Server**: `server/widgets/carousel.py` — exports `WIDGET`, `INPUT_MODEL`, `handle()`

### 4. Create Your App
```bash
./create_new_app.sh --name my_app                    # Start fresh
./create_new_app.sh --name my_app --keep carousel    # Keep carousel as reference
```
Verify tests still pass after running the script.

### 5. Development Loop
For each widget you build:
```bash
# 1. Create src/my-widget/index.tsx + src/my-widget/App.tsx
# 2. Create server/widgets/my_widget.py (auto-discovered)
# 3. Build and test:
pnpm run build && pnpm run test
# 4. Visual verification:
pnpm run ui-test --tool show_my_widget
# 5. Check screenshot: /tmp/ui-test/screenshot.png
# 6. Iterate until tests pass and widget renders correctly
```

### 6. Final Verification
```bash
pnpm run test:browser   # Slower but catches rendering issues in real browser
```

Your app is production-ready.

---

## Commands Reference

| Command | Purpose |
|---------|---------|
| `./setup.sh` | First-time setup (installs deps, builds, tests) |
| `pnpm run build` | Build all widgets (REQUIRED before server) |
| `pnpm run test` | Server + UI tests (run after every change) |
| `pnpm run test:all` | All tests including browser |
| `pnpm run test:browser` | Browser compliance tests only |
| `pnpm run server` | Start MCP server at localhost:8000 |
| `pnpm run ui-test --tool <name>` | Render tool, save screenshot to `/tmp/ui-test/` |
| `pnpm run ui-test --tool <name> --theme dark` | Test tool in dark mode |

---

## Boundaries

### Always
- Run `pnpm run build` before `pnpm run server` or `pnpm run test`
- Run `pnpm run test` after every code change
- Add `extra='forbid'` and default values to all Pydantic Input models
- Support both light and dark themes in widgets
- Check test grade reports after running tests:
  - `server/tests/mcp_best_practices_report.txt`
  - `server/tests/chatgpt_app_guidelines_report.txt`
  - `server/tests/output_quality_report.txt`
  - `server/tests/agentic_ux_patterns_report.txt`
  - `server/tests/protocol_compliance_report.txt`
  - `server/tests/app_submission_report.txt`

### Ask First
- Adding new npm dependencies (especially heavy ones like `three`, `chart.js`)
- Changing the MCP server's transport or security settings
- Modifying shared hooks behavior (`useWidgetProps`, `useTheme`)

### Never
- Modify `internal/apptester/` — Testing infrastructure, not an example
- Modify `internal/sandbox-proxy/` — Testing infrastructure, not an example
- Modify `src/use-*.ts` hooks — Shared infrastructure used by all widgets
- Modify `tests/browser/apptester-e2e.spec.ts` — Core test infrastructure
- Create Input models without `extra='forbid'` (causes test failures)
- Skip running tests after changes

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Widgets | React 18, TypeScript, Tailwind CSS |
| Server | Python 3.11+, FastMCP, Pydantic |
| Protocol | MCP Apps (SEP-1865) |
| Testing | Vitest (UI), pytest (server), Playwright (browser) |

---

## File Structure

| Path | Purpose |
|------|---------|
| `src/{widget}/index.tsx` | Widget entry point (targets `{widget}-root` element) |
| `src/{widget}/App.tsx` | Widget React component (optional but recommended) |
| `src/use-*.ts` | Shared hooks — DO NOT MODIFY |
| `server/widgets/{widget}.py` | Widget server module (auto-discovered) |
| `server/widgets/_base.py` | Base classes and helpers |
| `server/main.py` | MCP server setup (rarely needs editing) |
| `internal/` | Test infrastructure — DO NOT MODIFY |
| `tests/*.test.ts` | UI unit tests (Vitest) |
| `tests/browser/*.spec.ts` | Browser compliance tests (Playwright) |
| `server/tests/test_*.py` | Server tests and grading (pytest) |

---

## Adding a Widget (Quick Reference)

### Frontend: `src/my-widget/index.tsx`
```tsx
import { createRoot } from "react-dom/client";
import App from "./App";

createRoot(document.getElementById("my-widget-root")!).render(<App />);
```

### Frontend: `src/my-widget/App.tsx`
```tsx
import { useWidgetProps } from "../use-widget-props";
import { useTheme } from "../use-theme";

type Props = { title: string; message: string };

export default function App() {
  const props = useWidgetProps<Props>({ title: "Default", message: "Hello" });
  const theme = useTheme();

  if (!props) return <div>Loading...</div>;

  return (
    <div className={theme === "dark" ? "bg-gray-900 text-white" : "bg-white text-gray-900"}>
      <h1>{props.title}</h1>
      <p>{props.message}</p>
    </div>
  );
}
```

### Server: `server/widgets/my_widget.py`
```python
"""My widget module — auto-discovered by server/widgets/__init__.py"""

from typing import Any, Dict
import mcp.types as types
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from ._base import Widget, format_validation_error, get_invocation_meta

WIDGET = Widget(
    identifier="show_my_widget",
    title="Show My Widget",
    description="Displays my widget. Use when user wants X.",
    template_uri="ui://widget/my-widget.html",
    invoking="Loading...",
    invoked="Ready",
    component_name="my-widget",
)

class MyWidgetInput(BaseModel):
    title: str = Field(default="My Widget", description="Widget title")
    message: str = Field(default="Hello!", description="Message to display")
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

INPUT_MODEL = MyWidgetInput

async def handle(widget: Widget, arguments: Dict[str, Any]) -> types.ServerResult:
    try:
        payload = MyWidgetInput.model_validate(arguments)
    except ValidationError as e:
        error_msg = format_validation_error(e, MyWidgetInput)
        return types.ServerResult(types.CallToolResult(
            content=[types.TextContent(type="text", text=error_msg)],
            isError=True,
        ))

    return types.ServerResult(types.CallToolResult(
        content=[types.TextContent(type="text", text=f"Widget: {payload.title}")],
        structuredContent={"title": payload.title, "message": payload.message},
        _meta=get_invocation_meta(widget),
    ))
```

Then: `pnpm run build && pnpm run test && pnpm run ui-test --tool show_my_widget`

---

## Documentation Index

| Document | When to Read |
|----------|--------------|
| `docs/widget-development.md` | Hook APIs (`useWidgetProps`, `useTheme`, `useWidgetState`) |
| `docs/mcp-development-guidelines.md` | Tool naming, descriptions, error handling |
| `docs/what-makes-a-great-chatgpt-app.md` | Know/Do/Show framework, UX patterns |
| `docs/15-lessons-building-chatgpt-apps.md` | Context asymmetry, front-loading, interactive state sync |
| `docs/mcp-apps-docs.md` | MCP Apps protocol overview |
| `docs/mcp-apps-specs.mdx` | Full protocol specification (SEP-1865) |

---

## Local Testing

### App Tester (No API Key Required)
```bash
pnpm run build && pnpm run server
# Open http://localhost:8000/assets/apptester.html
```

### With Claude (Web or Desktop)
```bash
pnpm run server                                      # Terminal 1
npx cloudflared tunnel --url http://localhost:8000   # Terminal 2
# Add tunnel URL as custom connector in Claude settings
```

### With MCP Apps Basic Host
```bash
git clone https://github.com/modelcontextprotocol/ext-apps
cd ext-apps/examples/basic-host
npm install && SERVERS='["http://localhost:8000"]' npm start
```

---

## Browser Tests

Run after development is complete:
```bash
pnpm run setup:test          # One-time: install Playwright
pnpm run test:browser        # Run browser compliance tests
```

Tests verify: no JS errors, renders content, dark theme works, images have alt text, no duplicate IDs, callTool invocations are valid.

---

## Deployment

For VPS or remote server, set `BASE_URL`:
```bash
BASE_URL=http://YOUR_IP:8000/assets pnpm run server
```

Or use `.env` file (see `.env.example`).
