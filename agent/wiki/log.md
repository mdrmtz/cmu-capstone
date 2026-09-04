# Architectural Decision Log

## 2026-08-31 — Fresh-start rebuild of `agent/`

Rebuilt `cmu-capstone/agent/` from scratch per `agent-plan.md`, using the
plan as the source of truth (not any prior session's implementation).
`deepagents` 0.7.11 was already available; every design decision below was
verified against the *real* installed API, not the plan's illustrative
pseudocode, where the two disagreed.

**Real API corrections found during the rebuild:**

- `FilesystemPermission` fields are `operations`/`paths`/`mode` (`allow` |
  `deny` | `interrupt`), not `path=`/`mode="write"`.
- `RubricMiddleware(model=, system_prompt=, max_iterations=, ...)` has no
  structured `rubric=` dict kwarg - the criteria live in `system_prompt`.
- `interrupt_on` values may be a plain `bool`, or an `InterruptOnConfig` whose
  `when` is a `Callable[[ToolCallRequest], bool]`, not the string `"always"`.
- `FilesystemMiddleware` raises `NotImplementedError` if `permissions=` is
  combined with an execution-capable backend (`LocalShellBackend`/
  `DockerSandboxBackend`). Resolution: keep `permissions=` (real write-scope
  enforcement) on a non-execution `FilesystemBackend`; `codebase_compiler`
  verifies builds via the angular-cli MCP's `run_target` tool instead of
  deepagents' native `execute` tool. This also means git-worktree-per-
  candidate isolation doesn't compose with deepagents' single shared
  backend - `git_worktree.py`/`DockerSandboxBackend` remain real, tested
  adapters used procedurally by the evaluation harness, not wired as live
  agent tools.
- `deepagents.backends.sandbox.BaseSandbox` derives `ls`/`read`/`glob`/
  `grep`/`edit` from `execute()` via server-side `python3 -c "..."` scripts -
  any custom sandbox image needs `python3` on PATH (`alpine:latest` does
  not; added an explicit install to `sandbox/Dockerfile`).

**Benchmark reconciliation:** `agent-plan.md`'s "18 violation instances"
counts distinct (page, rule) pairs. A live audit (axe-core 4.13,
`wcag2a,wcag2aa`) confirms 18 such pairs across 5 rules on 11 pages, but 22
individual DOM-node instances (some pages have >1 failing node for the same
rule). `evaluation/benchmark_cases.json` uses the 22-instance, node-level
granularity - the unit an actual fix targets.

**Scope note:** the LangChain docs/reference MCP servers
(`docs-langchain`, `reference-langchain`) were added to the top-level
orchestrator's tools per an explicit user request during the rebuild, beyond
what `agent-plan.md`'s illustrative code sample listed.

No LLM API key was available in this environment during the rebuild
(`ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/`OPENROUTER_API_KEY` all unset); the
full pipeline is proven as far as is possible without one - deep agent graph
construction, all 6 MCP server connections, and every adapter/domain module
are verified for real (122 tests: 118 fast + 4 e2e), but no live subagent
turn has actually been exercised end-to-end.
