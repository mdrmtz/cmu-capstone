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

from deepagents import FilesystemPermission, RubricMiddleware, SubAgent
from langchain_core.language_models import BaseChatModel

from a11y_fixer import config
from a11y_fixer.adapters.mcp_clients import aget_tools

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
"""

RUBRIC_SYSTEM_PROMPT = """Grade the current candidate fix against this rubric:

- wcag_lexical_support: alt text / aria text describes semantic intent, not
  visual appearance.
- build_passes: `ng build` exits 0.
- axe_clear: re-running axe-core shows no regression for this rule.

Respond with satisfied=true only when every criterion passes.
"""


def _permissions(virtual_fixture: str) -> list[FilesystemPermission]:
    return [
        FilesystemPermission(operations=["read"], paths=[f"{virtual_fixture}/**"], mode="allow"),
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
    virtual_fixture = config.to_virtual_path(config.fixture_path())
    return SubAgent(
        name=NAME,
        description=(
            "Applies a fix candidate's code patch to the Angular fixture and "
            "verifies it builds and passes tests, using angular-cli-mcp for "
            "version-aware guidance."
        ),
        system_prompt=SYSTEM_PROMPT,
        tools=mcp_tools,
        skills=[config.to_virtual_path(config.skills_dir() / "angular-cli-mcp")],
        permissions=_permissions(virtual_fixture),
        middleware=[RubricMiddleware(model=model, system_prompt=RUBRIC_SYSTEM_PROMPT, max_iterations=3)],
    )

