"""SubAgent spec: crawls the running app via Playwright MCP to discover
routes dynamically, instead of relying on `adapters.audit_runner.
DEFAULT_PAGES`'s hardcoded list going stale as the fixture grows.
"""

from __future__ import annotations

from deepagents import SubAgent
from langchain.agents.structured_output import ToolStrategy
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel

from a11y_fixer import config
from a11y_fixer.adapters.audit_runner import DEFAULT_PAGES, AxeAuditRunner
from a11y_fixer.adapters.mcp_clients import aget_tools

NAME = "audit_crawler"

# A narrow, bounded discovery task (navigate, snapshot, extract hrefs) doesn't
# need, and shouldn't cost, the paid model the rest of the agent uses by default.
DEFAULT_CRAWLER_MODEL = "openrouter:openrouter/free"

SYSTEM_PROMPT = """You are the Audit Crawler for The A11y Fixer.

Discover every route in the running app: navigate to its root page, use
`browser_snapshot` to read the rendered DOM, and follow in-app navigation
links (parse anchor `href`s from the nav). Return the discovered routes as
relative paths (e.g. "/about"), not full URLs - the caller joins them with
its own base URL, whether that's a local dev server or a live external
site. If the Playwright MCP tools are unavailable, report that plainly so
the caller can fall back to `adapters.audit_runner.DEFAULT_PAGES`.
"""


async def build(model: str = DEFAULT_CRAWLER_MODEL) -> SubAgent:
    """Resolve this subagent's MCP tools and return its `SubAgent` spec.

    A `SubAgent` dict's own `"model"` key overrides the top-level model for
    just this subagent (per `deepagents.graph`'s `spec.get("model", model)`).
    """
    tools = await aget_tools(["playwright"])
    return SubAgent(
        name=NAME,
        description="Crawls the running app via Playwright MCP to discover routes dynamically for the axe-core audit.",
        system_prompt=SYSTEM_PROMPT,
        tools=tools,
        skills=[config.to_virtual_path(config.skills_dir() / "playwright-mcp")],
        model=model,
    )


class DiscoveredRoutes(BaseModel):
    """Structured output for the standalone discovery agent below - replaces
    the free-form "return the discovered route list" prose with a real,
    validated data structure.
    """

    routes: list[str]


async def discover_routes(
    base_url: str, *, model: str = DEFAULT_CRAWLER_MODEL
) -> list[str]:
    """Run this module's own prompt/tools as a standalone single-agent
    graph and return the routes it discovers - no subagent delegation is
    needed for a one-shot discovery task.

    Never raises: any failure (MCP unavailable, model error, malformed
    output) returns an empty list so callers can fall back to a known-good
    page list instead of blocking the audit outright.
    """
    from deepagents import (
        create_deep_agent,
    )  # noqa: PLC0415 - deferred: keeps module import side-effect-free for tests

    config.configure_model_providers()
    try:
        tools = await aget_tools(["playwright"])
        graph = create_deep_agent(
            model=model,
            tools=tools,
            system_prompt=SYSTEM_PROMPT,
            skills=[config.to_virtual_path(config.skills_dir() / "playwright-mcp")],
            response_format=ToolStrategy(schema=DiscoveredRoutes),
            checkpointer=InMemorySaver(),
        )
        result = await graph.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": f"Discover every route in the running app at {base_url}.",
                    }
                ]
            },
            config={
                "configurable": {
                    "thread_id": "audit-crawler-discovery",
                    "recursion_limit": 30,
                }
            },
        )
        response = result.get("structured_response")
        return list(response.routes) if response else []
    except (
        Exception
    ):  # noqa: BLE001 - discovery failing must not block the caller's fallback path
        return []


async def discover_and_audit(
    runner: AxeAuditRunner, *, model: str = DEFAULT_CRAWLER_MODEL
) -> dict:
    """Route-aware drop-in replacement for `runner.run()`: start the server,
    discover real routes via this module's own crawler prompt, run one
    combined axe-core scan across all of them, then always stop the server.

    Falls back to `DEFAULT_PAGES` if discovery finds nothing - a broken or
    unavailable crawler must never block the audit outright.
    """
    runner.start_server()
    try:
        # http:// is correct here: `ng serve` is a local dev server with no TLS.
        base_url = f"http://{runner.host}:{runner.port}"  # noqa: S310
        routes = await discover_routes(base_url, model=model)
        return runner.audit_pages(pages=tuple(routes) if routes else DEFAULT_PAGES)
    finally:
        runner.stop_server()
