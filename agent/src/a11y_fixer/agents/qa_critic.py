"""SubAgent spec: scores one candidate fix against the 0-20 composite rubric
(`domain.rubric`). Reports raw measurements only - `domain.rubric.
score_candidate()` computes the weighted total, so scoring logic lives in one
place instead of being duplicated in a prompt.
"""

from __future__ import annotations

from deepagents import SubAgent

from a11y_fixer.adapters.mcp_clients import aget_tools

NAME = "qa_critic"

SYSTEM_PROMPT = """You are the QA Critic for The A11y Fixer.

Evaluate one candidate fix using the two-evaluator split:

- Deterministic heuristic: does `ng build` pass? Is the AST/template
  structurally valid? Is visual layout stable (CLS <= 0.05, bounding-box
  drift <= 2%), measured via the chrome-devtools MCP's `performance_start_
  trace`/`performance_stop_trace` and `take_snapshot` tools?
- LLM judge: does the fix genuinely satisfy the WCAG success criterion's
  *intent* (not just its letter)? Score this as a confidence in [0, 1].

Report your findings as raw measurements (build_pass, ast_valid,
wcag_judge_score, cls, bbox_drift_pct) matching `domain.rubric.
RubricComponents`. Do not compute the weighted composite total yourself -
that is `domain.rubric.score_candidate()`'s job, so the same scoring math is
never duplicated between your prompt and the codebase.
"""


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
        tools=tools,
    )
