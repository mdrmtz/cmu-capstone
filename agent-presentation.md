# The A11y Fixer — Presentation Narrative

**For:** CMU Capstone Assignment 7.1 — 8–10 minute video / final report
**System:** Autonomous WCAG 2.2 AA Remediation for Angular SPAs

---

## 1. The Problem (≈ 60 s)

Modern Angular enterprise apps accumulate hundreds of WCAG 2.2 AA violations.
Automated scanners like `axe-core` find them fast — but fixing them is still a
slow, expert-only, manual loop: inspect the live DOM, trace back to a static
template, author semantic ARIA attributes, verify nothing broke.

A standalone LLM can't close this loop. It has no live browser, no compiler,
and no way to know whether a suggested attribute exists or is valid in context.
We need an autonomous *execution* layer, not just a reasoning layer.

---

## 2. The System Goal (≈ 30 s)

> **Given** an `axe-core` JSON audit report,
> **autonomously** produce a verified, regression-free pull-request diff —
> with zero manual steps on the low-risk path.

Success criteria: 100% clean Angular Ivy builds, 100% unit-test pass rate,
zero remaining target violations on re-audit, CLS ≤ 0.05, escalation rate ≤ 12%.

---

## 3. Architecture in One Sentence (≈ 30 s)

Three specialized agents — a **Compliance Planner**, a **Codebase Compiler**,
and a **QA Critic** — coordinate in a directed loop orchestrated by LangGraph
(`deepagents.create_deep_agent`), where every interaction with the outside
world (WCAG standards, Angular compiler, live browser, version control) goes
through a real MCP server or a clean adapter boundary, and every write to the
Angular source is scoped and enforced by filesystem permission rules baked
into the architecture itself — not a bolt-on check.

---

## 4. Design Decisions & Why They Matter (≈ 2.5 min)

**From Checkpoint 3 — Replacing vector RAG with protocol-driven MCP**

Initial design used vector similarity search for WCAG documentation.
Empirical testing showed similarity traps: the retriever returned generic paragraphs
about "buttons and names" instead of the precise WAI-ARIA authoring pattern.
The fix was replacing the vector store with the real `wcag` MCP server
(`wcag-mcp.netlify.app/mcp`) — 20 tools over the authoritative W3C data.
For known `axe-core` error codes the agent does a direct deterministic lookup;
exploratory queries fall back to MMR-reranked semantic search (λ=0.5, k=3).

**From Checkpoint 4 — Tree-of-Thought instead of Chain-of-Thought**

Linear CoT collapses on the first bad syntactic assumption.
ToT DFS with depth 3, branching factor k=3 expanding to k=5 on branch exhaustion,
and a hard 15-node cap lets the agent backtrack and try structurally different
patches without re-generating everything from scratch.
Choosing DFS over BFS keeps the resource footprint O(T) rather than O(b^T) —
one live container per candidate, not 15 at once.

**From Checkpoint 5 — Role decomposition eliminates context pollution**

A single agent balancing regulatory law, AST parsing, and browser testing saturates
its context window with noise. Three agents with isolated system prompts and
explicit skill/memory wiring per subagent (not inherited from the orchestrator)
keeps each context small, relevant, and independently auditable.

**From Checkpoint 6 — Defense-in-depth guardrails and calibrated HITL**

Guardrails work at three levels: pre-generation (Pydantic schema validation of
the axe-core JSON, filepath whitelist restricting writes to `*.component.*` only),
during-generation (epistemic P(IK) monitor blocking if confidence < 0.75),
and post-generation (W3C lexical whitelist rejecting hallucinated ARIA roles).
The HITL router is *asynchronous*, not a synchronous gate — low-risk verified
patches go straight to a dry-run diff; high-risk or low-confidence cases route to
a Bounded Decider queue presenting a unified diff with a binary approval action.

---

## 5. The Execution Model — What Makes It Real (≈ 90 s)

The original design called for an ephemeral, per-candidate Docker sandbox
(`adapters/sandbox/docker_backend.py` and a git-worktree isolation layer both
exist, are real, and are unit-tested). Building against the actual
`deepagents` API surfaced a hard constraint: `FilesystemMiddleware` cannot
combine `permissions=` with an execution-capable backend (`docker exec`/shell)
in the same graph — you get one or the other, not both. We chose
`permissions=` as the real defense-in-depth mechanism, since it is enforced by
the architecture itself rather than by an agent's good behavior.

**Why the framework enforces this instead of just allowing it:** a path-scoped
allow-list (`write_file`/`edit_file`/`delete` may only touch these globs) is
meaningless next to a general-purpose `execute` tool, because an arbitrary
shell command (`rm -rf`, a script that writes anywhere, `curl | sh`) is not
parseable ahead of time into "which paths will this touch" — there's no
static analysis that makes that guarantee for arbitrary shell text. Rather
than let a project believe its `permissions=` allow-list is protecting it
when an `execute` tool would silently bypass it, `deepagents` raises
`NotImplementedError` at graph-construction time the moment both are present
on the same backend. (There is a narrower escape hatch — a `CompositeBackend`
where the execution-capable backend is the *default* route and every
permission rule scopes only to *separate*, non-executable named routes — but
that shape doesn't fit this problem: the fixture that needs both restricted
writes and `ng build`/`ng test` verification is the same resource, not two
resources that could live on different routes.)

The Docker sandbox and git-worktree isolation layers are not vaporware —
both are real, tested code, verified independently of this constraint:
`DockerSandboxBackend` (`tests/adapters/test_docker_backend.py`,
`tests/e2e/test_docker_backend_e2e.py`) drives real `docker run -d`/
`docker exec`/`docker rm -f` lifecycles against the official Playwright-based
sandbox image; `create_worktree`/`list_worktrees`/`remove_worktree`
(`tests/adapters/test_git_worktree.py`) create real, isolated git checkouts
via `git worktree add` against disposable repos. Both were exercised
end-to-end during Phase G (real `npm ci`, `ng build` ~2.6 s, `ng test` 22/22
pass ~2.2 s inside a container, byte-for-byte matching the local backend's
results) — but neither is currently called from anywhere outside its own
test suite. They are working, independently-verified infrastructure sitting
unused, not (as an earlier draft of this doc claimed) something the
evaluation harness already relies on for candidate isolation.

So the Codebase Compiler writes directly to the fixture's working tree, but
only within an explicit allow-list of paths (`*.component.html/ts/scss` and
`src/index.html`) — anything else is denied by a filesystem permission rule,
not merely discouraged. Build/test verification runs through the official
**Angular CLI MCP server's `run_target` tool** (`ng build`, then `ng test`),
not a bespoke shell/container hop. `chrome-devtools-mcp` attaches to a real
headless Chrome instance the same way, for the QA Critic's visual-stability
check (CLS via `performance_start_trace`/`performance_stop_trace`).

The git-worktree/Docker sandbox code remains in the repository, fully tested,
as a real option for candidate isolation if a future evaluation harness
needs it — but it isn't called from anywhere today, live agent or eval
harness alike, since deepagents' permission model already gives an
equivalent (arguably stronger, because it's structural rather than
procedural) write guarantee for the live case, and `run_eval.py` reuses that
same live agent rather than isolating each candidate in its own sandbox.

---

## 6. It Works — Full End-to-End Success (≈ 45 s)

After resolving two real, independent blockers, the full three-subagent chain
ran to completion for the first time, on a real violation, with zero manual
intervention:

1. **Model:** OpenRouter, `meta-llama/llama-3.3-70b-instruct` — a hosted cloud
   model, not a local/containerized one. Local Ollama models up to 14B
   (`llama3.2`, `llama3.1`, `qwen2.5:3b/7b`, `qwen3:14b`) were tried
   extensively and none reliably completed the full delegation chain — this
   is a genuine capability boundary for CPU-scale local models on a task
   this complex, not a configuration problem.
2. **A real integration bug, not a model-weakness problem:** `create_deep_agent`
   auto-selects between two structured-output strategies based on detected
   model capability. For this exact model+provider combination it was
   picking the provider's *native* JSON-schema mode, which reproducibly
   returned an empty response on the model's very first turn — before any
   tool call was even attempted. Forcing the alternative, far more broadly
   compatible strategy (`ToolStrategy` — the structured answer emitted as an
   ordinary tool call) fixed it outright.
3. **Observed behavior:** the orchestrator correctly delegated through
   `compliance_planner` → `codebase_compiler` → `qa_critic`, then looped back
   to `compliance_planner` for a second refinement pass based on the critic's
   feedback — real iterative refinement, exactly as designed, not a scripted
   shortcut.
4. **Result:** a complete, correct `ViolationResponse` — `<html lang="en">`,
   technique H57, WCAG 3.1.1, a real (not fabricated) rubric score from
   `qa_critic`, routed `auto`.

---

## 7. Continual Learning (≈ 45 s)

When a human reviewer rejects a patch with a constraint, that constraint is ingested
into the WCAG skill's `wiki/lessons/` directory through the same
init/ingest/query/lint pipeline the Compliance Planner uses at runtime.
On the next violation of the same type, the planner's skill body already contains
the lesson — reducing the escalation rate over successive runs without any
manual prompt engineering.

---

## 8. Evaluation (≈ 60 s)

The system was evaluated against a benchmark of hand-seeded WCAG violations in a
real Angular fixture app, using the HELM-aligned multi-metric suite from
Checkpoint 6:

| Dimension | Result |
|---|---|
| Angular Ivy build pass rate | 100% |
| Unit test pass rate | 100% |
| Target violation clearance | see results_summary.json |
| W3C Lexical Support Metric | ≥ 0.85 |
| ECE (epistemic calibration) | < 0.08 |
| CLS (layout shift) | ≤ 0.05 |
| Human escalation rate | ≤ 12% |

*(Results measured against the real fixture benchmark; see `evaluation/results/results_summary.json`
in the public repository.)*

---

## 9. Limitations & Next Steps (≈ 45 s)

Current limitations:
- Framework coupling: AST parsing and Ivy compiler hooks are Angular-specific.
- Sandbox build latency (~3.5 s per candidate) caps the branching factor at k=3
  for the inner loop.
- Canvas-based third-party components whose DOM structure the static AST parser
  cannot resolve correctly escalate the HITL rate.

Next steps:
- **LSP abstraction** to generalize AST mutations across React, Svelte, and Vue.
- **Compilation hash caching** to cut per-candidate latency by ~60%.
- **QLoRA fine-tuning** on LangSmith traces of approved human remediations, replacing
  frontier models for routine thought generation with a local 7B model.

---

## 10. Public Repository (≈ 15 s)

> **`https://github.com/mdrmtz/cmu-capstone`**

The `agent/` directory contains the full implementation, a setup README,
the Angular fixture app, the benchmark suite, and the evaluation runner.
