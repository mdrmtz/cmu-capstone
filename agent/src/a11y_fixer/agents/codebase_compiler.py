"""SubAgent spec: applies a fix candidate's code patch to the Angular fixture
and verifies it with `ng build`/`ng test`. Filesystem `permissions` enforce
the write scope in the architecture itself, not as a bolt-on check - first
matching rule wins, and an unmatched path defaults to allow, so the
allow-list must be followed by an explicit catch-all deny.

Build/test verification runs through the angular-cli MCP's `run_target` tool
rather than deepagents' native `execute` tool: `FilesystemMiddleware` does
not support `permissions` together with an execution-capable backend (raises
`NotImplementedError`), and the official MCP server already exposes exactly
this capability, so no bespoke shell execution is needed.

`RubricMiddleware` is Phase C's ToT DFS replacement: a grader sub-agent loops
over candidates (`max_iterations=3`, mirroring the plan's k=3 base sibling
count) until the rubric is satisfied. `domain.tot_search` still exists as a
pure, directly-testable algorithm - `evaluation/run_eval.py` uses it for
offline benchmark scoring, decoupled from any live LLM.
"""

from __future__ import annotations

from pathlib import Path
from deepagents import (
    FilesystemMiddleware,
    FilesystemPermission,
    RubricMiddleware,
    SubAgent,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import tool

from a11y_fixer import config
from a11y_fixer.adapters.mcp_clients import aget_tools
from a11y_fixer.adapters.file_locator import (
    locate_selector_in_component as _locate_selector,
)

NAME = "codebase_compiler"

SYSTEM_PROMPT = """You are the Codebase Compiler for The A11y Fixer.

Given a fix candidate JSON from the Compliance Planner, apply the proposed
code patch to the Hallucinate.io fixture and verify it with the angular-cli
MCP's `run_target` tool (`ng build`, then `ng test`). The fixture is Angular
22.1, standalone components, `ChangeDetectionStrategy.OnPush`, `@if`/`@for`
control flow - no NgModules. Preserve `OnPush` and each component's
standalone `imports[]` array. Use `get_best_practices` and
`search_documentation` from the angular-cli MCP for version-specific
guidance before editing.

You may only write within the allow-listed component file globs (and
`src/index.html` for the site-wide `html-has-lang` fix) - any other target is
denied by the filesystem permission layer itself, not merely discouraged.

## File Discovery Strategy

Before applying any fix to a component template, use the `locate_selector_in_component` tool
to find the exact file and line where the violation occurs:

1. Extract the CSS selector from the violation (e.g., "img[src$='atlas-dashboard.svg']")
2. Extract a hint text if present (e.g., "atlas-dashboard.svg" from the selector)
3. Call locate_selector_in_component with:
   - selector: the CSS selector string
   - hint_text: specific value to narrow the search (if available)
   - codebase_root: the fixture root directory
4. Review the top result(s) and confirm the file and line number
5. Only then read and modify the EXACT component file at the returned location

Example workflow:
  Violation: "img[src$='atlas-dashboard.svg'] missing alt text"
  → Call locate_selector_in_component(
      selector="img[src$='atlas-dashboard.svg']",
      hint_text="atlas-dashboard.svg",
      codebase_root=config.fixture_path()
    )
  → Result: [{"file_path": "src/app/pages/case-studies/case-studies.component.html",
              "line_number": 42, "confidence": 0.75, ...}]
  → Read that file, find line 42, add alt attribute to <img>

This deterministic approach prevents the 40-66% file-location failures seen in prior runs.
"""


@tool
def locate_selector_in_component(
    selector: str,
    hint_text: str | None = None,
    codebase_root: str | None = None,
) -> list[dict]:
    """Locate component files matching a CSS selector.

    Uses deterministic file discovery (hint-text grepping + HTML regex matching)
    to find Angular component templates containing elements matching the provided
    CSS selector. Returns ranked results by confidence (0.0-1.0).

    Args:
        selector: CSS selector string (e.g., "img[src$='atlas-dashboard.svg']")
        hint_text: Specific text value to narrow search (e.g., "atlas-dashboard.svg")
        codebase_root: Root directory to search from (defaults to fixture root)

    Returns:
        List of dicts sorted by confidence (descending):
        {
            "file_path": str (path to component file),
            "line_number": int (1-indexed),
            "element_html": str (matched element),
            "confidence": float (0.0-1.0, higher = more certain)
        }
        Returns empty list if no matches found.
    """
    if codebase_root is None:
        codebase_root = config.fixture_path()
    else:
        codebase_root = Path(codebase_root)

    return _locate_selector(
        selector=selector,
        hint_text=hint_text,
        glob_pattern="src/**/*.component.html",
        codebase_root=codebase_root,
    )


RUBRIC_SYSTEM_PROMPT = """Grade the current candidate fix against this rubric:

- wcag_lexical_support: alt text / aria text describes semantic intent, not
  visual appearance.
- build_passes: `ng build` exits 0.
- axe_clear: re-running axe-core shows no regression for this rule.

Respond with satisfied=true only when every criterion passes.
"""


def _permissions(virtual_fixture: str) -> list[FilesystemPermission]:
    return [
        FilesystemPermission(
            operations=["read"], paths=[f"{virtual_fixture}/**"], mode="allow"
        ),
        FilesystemPermission(
            operations=["write"],
            paths=[
                f"{virtual_fixture}/src/app/**/*.component.html",
                f"{virtual_fixture}/src/app/**/*.component.ts",
                f"{virtual_fixture}/src/app/**/*.component.scss",
                f"{virtual_fixture}/src/index.html",
            ],
            mode="allow",
        ),
        FilesystemPermission(operations=["write"], paths=["/**"], mode="deny"),
    ]


async def build(model: str | BaseChatModel) -> SubAgent:
    """Resolve this subagent's MCP tools and return its `SubAgent` spec."""
    mcp_tools = await aget_tools(["angular-cli"])
    # Filter out list_projects tool: it returns invalid structured content (missing parsingErrors field)
    mcp_tools = [t for t in mcp_tools if getattr(t, "name", None) != "list_projects"]
    virtual_fixture = config.to_virtual_path(config.fixture_path())
    return SubAgent(
        name=NAME,
        description=(
            "Applies a fix candidate's code patch to the Angular fixture and "
            "verifies it builds and passes tests, using angular-cli-mcp for "
            "version-aware guidance."
        ),
        system_prompt=SYSTEM_PROMPT,
        tools=[*mcp_tools, locate_selector_in_component],
        skills=[config.to_virtual_path(config.skills_dir() / "angular-cli-mcp")],
        permissions=_permissions(virtual_fixture),
        middleware=[
            FilesystemMiddleware(
                tools=["read_file", "write_file", "edit_file"],
                _permissions=_permissions(virtual_fixture),
            ),
            RubricMiddleware(
                model=model, system_prompt=RUBRIC_SYSTEM_PROMPT, max_iterations=3
            ),
        ],
    )
