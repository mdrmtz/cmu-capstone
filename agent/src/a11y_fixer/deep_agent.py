"""Composition root: builds the A11y Fixer deep agent graph.

Superseded design note: Phase A built a custom `Orchestrator` class; this
module replaces it entirely per the plan's Phase B migration - `deepagents.
create_deep_agent()` is the sole orchestration layer, and every injected
dependency (model, tools, subagents, skills, memory, permissions,
interrupt_on) is a keyword argument to a single call.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from deepagents import FilesystemPermission
from deepagents.backends import BackendProtocol, FilesystemBackend
from langchain.agents.middleware import InterruptOnConfig
from langchain.agents.structured_output import ToolStrategy
from langchain_core.tools import tool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field

from a11y_fixer import config
from a11y_fixer.adapters.audit_runner import AxeAuditRunner
from a11y_fixer.adapters.mcp_clients import aget_tools
from a11y_fixer.adapters.retrieval import wiki_pipeline
from a11y_fixer.agents import (
    audit_crawler,
    codebase_compiler,
    compliance_planner,
    qa_critic,
)


class ViolationResponse(BaseModel):
    """Structured output for one resolved (or escalated) axe-core violation."""

    rule: str
    wcag: str
    selector: str
    technique_id: str
    technique_type: Literal["sufficient", "advisory"]
    code: str
    rationale: str
    score: float = Field(ge=0.0, le=20.0)
    route: Literal["auto", "human"]


@tool
def run_axe_audit() -> dict:
    """Run a full axe-core WCAG 2.2 AA audit against the Hallucinate.io
    fixture (starts `ng serve`, runs `@axe-core/cli`, tears the server back
    down) and return the normalized violation report.
    """
    runner = AxeAuditRunner(fixture_path=config.fixture_path())
    return runner.run()


TOP_LEVEL_SYSTEM_PROMPT = """You are The A11y Fixer: an autonomous WCAG 2.2 AA
remediation agent for the Hallucinate.io Angular SPA.

You MUST NOT call `ls`, `read_file`, `glob`, `grep`, `write_file`, or
`edit_file` yourself - those tools are reserved for your subagents.
Investigating or editing the codebase directly instead of delegating is a
failure of your job, even if delegating seems slower.

For each axe-core violation you are given, delegate through all three
subagents in order - never skip a subagent and never produce a final answer
before all three have run:
1. Delegate to `compliance_planner` to produce a fix candidate.
2. Delegate to `codebase_compiler` to apply and verify the patch.
3. Delegate to `qa_critic` to score the candidate against the rubric.
4. Combine the QA Critic's rubric score with your own confidence to decide
   whether the fix should be delivered automatically (`route: "auto"`) or
   escalated to a human (`route: "human"`) - never assume auto-delivery for
   a rule you are not fully confident about.

Before you return a final `ViolationResponse`, count your own `task()` tool
calls in this conversation: if it is fewer than 3 - one each to
`compliance_planner`, `codebase_compiler`, and `qa_critic` - you are NOT
done. Stopping after only `compliance_planner` and fabricating a `score`
is a critical failure, even if the plan looks correct - the score MUST come
from `qa_critic`'s real rubric evaluation, never a guess.

Return your final answer as the structured `ViolationResponse` schema.
"""


def _default_permissions(virtual_fixture: str) -> list[FilesystemPermission]:
    """Read-only at the top level; only `codebase_compiler`'s own permission
    override (a narrower allow-list) may write fixture files.
    """
    return [
        FilesystemPermission(
            operations=["read"], paths=[f"{virtual_fixture}/**"], mode="allow"
        ),
        FilesystemPermission(operations=["write"], paths=["/**"], mode="deny"),
    ]


async def abuild_agent(
    *,
    backend: BackendProtocol | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Async composition root: resolves every MCP-backed tool/subagent, then
    calls `create_deep_agent()` exactly once.
    """
    from deepagents import (
        create_deep_agent,
    )  # noqa: PLC0415 - deferred: keeps module import side-effect-free for tests

    config.configure_model_providers()
    model_spec = config.selected_llm_backend().model
    virtual_fixture = config.to_virtual_path(config.fixture_path())
    wiki_pipeline.init_wiki(config.wiki_dir())

    top_level_tools, subagents = await asyncio.gather(
        aget_tools(["docs-langchain", "reference-langchain"]),
        asyncio.gather(
            compliance_planner.build(),
            codebase_compiler.build(model_spec),
            qa_critic.build(),
            audit_crawler.build(),
        ),
    )

    resolved_backend = backend or FilesystemBackend(root_dir=str(config.repo_root()))

    return create_deep_agent(
        model=model_spec,
        tools=[run_axe_audit, *top_level_tools],
        system_prompt=TOP_LEVEL_SYSTEM_PROMPT,
        subagents=list(subagents),
        skills=[
            config.to_virtual_path(config.skills_dir() / "a11y-fixer"),
            config.to_virtual_path(config.skills_dir() / "cmu-capstone-docs"),
        ],
        memory=[
            config.to_virtual_path(wiki_pipeline.memory_file_path(config.wiki_dir()))
        ],
        permissions=_default_permissions(virtual_fixture),
        interrupt_on={
            "write_file": InterruptOnConfig(allowed_decisions=["approve", "reject"]),
            "edit_file": InterruptOnConfig(allowed_decisions=["approve", "reject"]),
        },
        # ToolStrategy (structured output emitted as a tool call), not the
        # bare schema (which lets create_deep_agent auto-pick ProviderStrategy
        # per-model) - ProviderStrategy's native JSON-schema mode reproducibly
        # returns an empty response for openrouter:meta-llama/llama-3.3-70b-
        # instruct; ToolStrategy is far more broadly compatible across providers.
        response_format=ToolStrategy(schema=ViolationResponse),
        backend=resolved_backend,
        # This graph is invoked directly (a root graph, not a subgraph), so
        # `checkpointer=True` is invalid here - LangGraph requires a real
        # BaseCheckpointSaver instance to persist state across HITL interrupts.
        checkpointer=checkpointer or InMemorySaver(),
    )


def build_agent(
    *,
    backend: BackendProtocol | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Sync wrapper around `abuild_agent`, for callers outside an event loop (`cli.py`)."""
    return asyncio.run(abuild_agent(backend=backend, checkpointer=checkpointer))
