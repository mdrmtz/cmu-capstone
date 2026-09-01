"""SubAgent spec: crawls the running app via Playwright MCP to discover
routes dynamically, instead of relying on `adapters.audit_runner.
DEFAULT_PAGES`'s hardcoded list going stale as the fixture grows.
"""

from __future__ import annotations

from deepagents import SubAgent

from a11y_fixer import config
from a11y_fixer.adapters.mcp_clients import aget_tools

NAME = "audit_crawler"

SYSTEM_PROMPT = """You are the Audit Crawler for The A11y Fixer.

Discover every route in the running Hallucinate.io app: navigate to its root
page, use `browser_snapshot` to read the rendered DOM, and follow in-app
navigation links (parse anchor `href`s from the nav). Return the discovered
route list so the orchestrator can run `AxeAuditRunner.audit_pages()` against
exactly the routes that exist, instead of a hardcoded page list. If the
Playwright MCP tools are unavailable, report that plainly so the caller can
fall back to `adapters.audit_runner.DEFAULT_PAGES`.
"""


async def build() -> SubAgent:
    """Resolve this subagent's MCP tools and return its `SubAgent` spec."""
    tools = await aget_tools(["playwright"])
    return SubAgent(
        name=NAME,
        description="Crawls the running app via Playwright MCP to discover routes dynamically for the axe-core audit.",
        system_prompt=SYSTEM_PROMPT,
        tools=tools,
        skills=[config.to_virtual_path(config.skills_dir() / "playwright-mcp")],
    )
