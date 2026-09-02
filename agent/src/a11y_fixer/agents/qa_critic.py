"""SubAgent spec: scores one candidate fix against the 0-20 composite rubric
(`domain.rubric`). Reports raw measurements only - `domain.rubric.
score_candidate()` computes the weighted total, so scoring logic lives in one
place instead of being duplicated in a prompt.
"""

from __future__ import annotations

from deepagents import SubAgent
from langchain_core.tools import tool

from a11y_fixer.adapters.mcp_clients import aget_tools
from a11y_fixer.domain.rubric import RubricComponents, score_candidate

NAME = "qa_critic"

SYSTEM_PROMPT = """You are the QA Critic for The A11y Fixer.

Evaluate one candidate fix using the two-evaluator split:

- Deterministic heuristic: does `ng build` pass? Is the AST/template
  structurally valid? Is visual layout stable (CLS <= 0.05, bounding-box
  drift <= 2%), measured via the chrome-devtools MCP's `performance_start_
  trace`/`performance_stop_trace` and `take_snapshot` tools?
- LLM judge: does the fix genuinely satisfy the WCAG success criterion's
  *intent* (not just its letter)? Score this as a confidence in [0, 1].

You MUST call the `score_rubric` tool with your raw measurements (build_pass,
ast_valid, wcag_judge_score, cls, bbox_drift_pct) and report its returned
`total` verbatim as your final score. Never compute or guess the weighted
composite total yourself - `score_rubric` is the only source of truth for
that number, so the same scoring math is never duplicated between your
reasoning and the codebase.
"""


@tool
def score_rubric(
    build_pass: bool,
    ast_valid: bool,
    wcag_judge_score: float,
    cls: float | None = None,
    bbox_drift_pct: float | None = None,
) -> dict:
    """Compute the deterministic 0-20 composite rubric score from raw measurements.

    Always call this with your own raw measurements and report the returned
    `total` verbatim - never invent or estimate the weighted total yourself.
    """
    components = RubricComponents(
        build_pass=build_pass,
        ast_valid=ast_valid,
        wcag_judge_score=wcag_judge_score,
        cls=cls,
        bbox_drift_pct=bbox_drift_pct,
    )
    result = score_candidate(components)
    return {
        "total": result.total,
        "max_total": result.max_total,
        "components": result.components,
        "visual_stability_measured": result.visual_stability_measured,
    }


async def build() -> SubAgent:
    """Resolve this subagent's MCP tools and return its `SubAgent` spec."""
    tools = await aget_tools(["chrome-devtools"])
    return SubAgent(
        name=NAME,
        description=(
            "Scores a candidate fix against the 0-20 rubric using a "
            "deterministic build/test/CLS check plus an LLM WCAG-compliance judge."
        ),
        system_prompt=SYSTEM_PROMPT,
        tools=[*tools, score_rubric],
    )
