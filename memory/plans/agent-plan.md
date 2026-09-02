# The A11y Fixer — Implementation Plan

**System:** Autonomous Web Accessibility (WCAG 2.2 AA) Remediation for Angular SPAs
**Repo:** `cmu-capstone/agent/`
**Date:** 2026-08-31 (Phase 0/1/2 guardrail-wiring addendum: 2026-09-01)

---

## Recent Changes (2026-08-31 — fresh-start rebuild)

Rebuilt `agent/` from scratch against this plan as the sole source of truth
(the previous session's implementation was gone except for `.venv`/`fixtures`/
`sandbox`/`wiki` leftovers). Full details and real-API corrections are in
`agent/wiki/log.md` and `agent/README.md`; summary:

| Change                                                                 | Detail                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| All phases (A-G) implemented                                           | `deep_agent.py` composition root via the real `create_deep_agent()`, 4 `SubAgent` specs, 6 MCP servers (`angular-cli`, `chrome-devtools`, `playwright`, `wcag`, `docs-langchain`, `reference-langchain` — the last two added on top of this plan's own tool list per an explicit request), domain layer (ToT DFS, rubric, guardrails, HITL policy), adapters (audit runner, wiki + MMR retrieval, git worktree, Docker sandbox, PR delivery), evaluation harness, GitHub Actions trigger. 122 tests (118 fast + 4 real e2e: axe-core, live wcag-mcp, Docker, full graph build). |
| Benchmark reconciled again                                             | "18 violation instances" was distinct (page, rule) pairs, not DOM nodes. A live audit confirms 18 such pairs across 5 rules/11 pages, but **22** individual DOM-node instances (some pages have >1 failing node for the same rule). `evaluation/benchmark_cases.json` now holds all 22, at node granularity.                                                                                                                                                                                                                                                                    |
| Real deepagents API deviations from this plan's pseudocode             | `FilesystemPermission` fields are `operations`/`paths`/`mode`, not `path=`/`mode="write"`. `RubricMiddleware` takes `model`/`system_prompt`/`max_iterations`, no `rubric=` dict. `FilesystemMiddleware` rejects `permissions=` combined with an execution-capable backend - resolved by using a non-execution `FilesystemBackend` plus the angular-cli MCP's `run_target` tool for build/test verification instead of deepagents' native `execute` tool.                                                                                                                        |
| PR delivery via GitHub REST, not `@modelcontextprotocol/server-github` | A one-shot procedural call doesn't benefit from the MCP protocol layer; `httpx` against the REST API directly is simpler and trivially mockable.                                                                                                                                                                                                                                                                                                                                                                                                                                |
| No live LLM key available                                              | `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/`OPENROUTER_API_KEY` all unset in this environment. Graph construction, all MCP connections, and every adapter are verified for real; no live subagent turn has been exercised end-to-end.                                                                                                                                                                                                                                                                                                                                                 |

**Update (later, same day):** a live key was provisioned. The full three-subagent
chain (`compliance_planner` → `codebase_compiler` → `qa_critic`, with a real
iterative refinement loop) has now run end-to-end for real, via OpenRouter's
`meta-llama/llama-3.3-70b-instruct`, producing a correct `ViolationResponse`.
Getting there required one more real code fix beyond this table: forcing
`response_format=ToolStrategy(schema=ViolationResponse)` instead of the bare
schema class, because `create_deep_agent`'s auto-selected `ProviderStrategy`
returned an empty response for this model/provider combination. See
`agent/wiki/log.md` and `agent-presentation.md` §6 for the full account.

---

## Recent Changes (2026-09-01 — dormant guardrail wiring: Phase 0-3)

A follow-up architecture audit (`Module-07-Capstone-Project/capstone-system-architecture-diagrams.md`)
found that `domain/guardrail_rules.py`, `domain/rubric.py`, and `domain/hitl_policy.py`
were real and unit-tested but had **zero callers from live code** - the running
agent never actually used any of them; routing was just the top-level LLM's own
judgment. Wired three of these in, numbered as phases layered on top of (not
replacing) the A-G plan above:

| Phase | What was wired | Detail |
| ----- | --------------- | ------ |
| 0 — Input validation | `guardrail_rules.validate_raw_axe_reports()` | Called from `AxeAuditRunner.audit_pages()` and `cli.py`'s `--audit <path>` loader - a malformed axe-core report now fails fast (exit code 2) before the agent is even built. `check_confidence_calibration()` also wired via a new `cli.warn_on_overconfidence()` helper, called after every resolved violation in both `cli.py` and `run_eval.py`. |
| 1 — Deterministic rubric scoring | `agents/qa_critic.py::score_rubric` | A new `@tool`-wrapped call into `domain/rubric.score_candidate()`, added to `qa_critic`'s tool list; its system prompt now mandates calling it and reporting the returned `total` verbatim instead of inventing a score. **Live-verified**: a real run confirmed the model calls `score_rubric` with real build/AST/WCAG/CLS measurements. |
| 2 — Risk-based routing | `domain/hitl_policy.assess_risk()` | Wired into `cli.py::deliver_violation()` - the model's self-reported `route` is no longer trusted on its own. `assess_risk()` checks the rule, the actually-changed file path(s), the rubric score, and P(IK) (`score/20`), and may escalate `"auto"` to `"human"` - never the reverse; the model's own `"human"` call is always honored. |
| 3 — Path + epistemic guardrails | `guardrail_rules.validate_write_path()` + `epistemic_gate()` | Both wired into `cli.py::deliver_violation()` as two more escalate-only signals alongside `assess_risk()`. `validate_write_path()` flags any changed file outside the fixture root or with a non-whitelisted extension (`.html`/`.ts`/`.scss`) - genuine defense-in-depth on top of deepagents' own `permissions=` allow-list. `epistemic_gate()` records its own PASS/BLOCK verdict in the queued JSON (`"epistemic_gate"` key) - **note:** at this call site it never disagrees with `assess_risk()`'s own `low_confidence` check, since both derive from the identical `p_ik = score / 20` and `15/20 == 0.75` matches `p_ik_floor` exactly - it adds an independently-recorded audit trail, not new escalation coverage, today. |

**Bundled bug fix (Phase 2):** `deliver_violation()` previously returned immediately
on `route == "human"` without ever calling `_capture_and_reset_git_changes()` -
any real file writes were left uncommitted in the fixture's working tree,
contaminating the next violation. Now the git diff is always captured (and the
tree always reset) regardless of route.

**Still genuinely open (not wired in this pass):** `hitl/review_queue.py`
(this plan's originally-envisioned calibrated ROC/AUC Bounded Decider) still
was never built - `assess_risk()` is a simpler, real substitute, not that
design; see the Phase E row below. The plan's "Reject with Constraint"
continual-learning loop is also **100% unimplemented** - `wiki_pipeline.
ingest_lesson()` is real and tested but has zero live callers, and the
dashboard's Approve/Reject buttons only write to `localStorage` with an
`alert()` - no backend ever receives a human's actual decision.

Verified: 246 tests passed, 4 e2e deselected, zero regressions. Full account
in `agent/wiki/log.md`.

---

## Recent Changes (2026-09-01 — Phase E.3: calibrated ROC/AUC review queue)

Built the plan's last missing Phase E piece: `hitl/review_queue.py`, porting
Module-06 Lab 6.2's `TrajectoryLogger -> Monitor -> ReviewQueue` pattern (the
lab this plan's own Phase E always cited) onto this domain, with the
polarity flipped - that lab flags HIGH suspicion and calibrates against
BENIGN traffic; this domain flags LOW confidence (P(IK)) and calibrates
against historically-CLEARED cases (the closest equivalent of "benign" -
the ones a false escalation would waste review time on).

- `roc_auc`/`roc_points` - ported near-verbatim (AUC = P(score(positive) >
  score(negative)), ties count half).
- `calibrate_p_ik_floor(cleared_p_iks, target_fpr=0.05)` - the HIGHEST P(IK)
  floor whose false-escalation rate on historically-cleared cases stays
  within budget (the lab's `calibrate_threshold` picks the LOWEST
  threshold within a benign false-positive budget; escalating below a
  floor instead of above a threshold flips which end of the scale is
  "most sensitive, still affordable").
- `calibrate_from_results(results_path)` - loads a real `run_eval.py`
  `results_summary.json` and calibrates from it; **falls back to
  `hitl_policy.DEFAULT_P_IK_FLOOR` (uncalibrated) since that file still
  doesn't exist** - running the real 22-case benchmark remains a
  prerequisite this function does not perform itself. Not yet wired to
  override `assess_risk()`'s live defaults for the same reason - there is
  no real data to calibrate from yet, so doing so would not actually be
  "calibrated," just a renamed hardcoded default.
- `ReviewQueue` class wraps the existing filesystem `hitl_queue/` directory
  (`list_pending()`/`review()`/`get_stats()`). **`review()` is the first
  real capture point for a human's actual decision** - closes the
  previously-flagged "Reject with Constraint" gap: reject calls
  `wiki_pipeline.ingest_lesson()` for real; approve re-applies the
  persisted diff via `pr_delivery.deliver()` (both were 100% dead ends
  before this). `deliver_violation()` now also persists the actual
  `changes` (file diffs) into the queued JSON so a later `review()` call
  has something real to act on - previously only `response.code` (a
  single snippet, not necessarily the full diff) survived past queueing.
- New `cli.py review` subcommand: `a11y-fixer review --list`,
  `a11y-fixer review <queue-file> --approve|--reject --notes "..."` -
  without this, `ReviewQueue` would just be another dormant, unit-tested-
  only module, exactly the anti-pattern this whole engagement has been
  fixing.

**Genuinely still open after this pass:** live calibration against real
data (blocked on the same `run_eval.py` run as the compendium
reconciliation); wiring `calibrate_from_results()`'s output into
`deliver_violation()`'s `assess_risk()` call once real data exists; a
dashboard-side UI for the new `review` subcommand (currently CLI-only).

Verified: 272 tests passed (was 246, +26 new), 4 e2e deselected, zero
regressions.

---

## Recent Changes (2026-09-01 — audit_crawler discover+audit encapsulation)

Closed the gap flagged by the architecture audit: `audit_crawler` was wired
as one of 4 live subagents but never actually reachable - neither `cli.py`
nor `run_eval.py` ever asks the top-level agent to discover pages, since
both always hand it an already-known violation. Added the actual mechanism
to `agents/audit_crawler.py`:

- `DiscoveredRoutes(BaseModel)` - a real Pydantic schema for the crawler's
  output, replacing the old free-form "return the discovered route list"
  prose (which had zero structure or validation).
- `discover_routes(base_url) -> list[str]` - a **standalone single-agent
  graph** (no subagent delegation - a one-shot task doesn't need it) built
  from this module's own `SYSTEM_PROMPT` + Playwright tools, with
  `response_format=ToolStrategy(schema=DiscoveredRoutes)`. Never raises -
  returns `[]` on any failure so callers can fall back to `DEFAULT_PAGES`.
- `discover_and_audit(runner: AxeAuditRunner) -> dict` - a route-aware
  drop-in replacement for `runner.run()`: start the server, discover real
  routes, run **one combined `audit_pages()` call** across all of them
  (already produces a single normalized report), always stop the server.
- `audit_crawler.build()`/`discover_routes()`/`discover_and_audit()` all
  default to `DEFAULT_CRAWLER_MODEL = "openrouter:openrouter/free"` - a
  narrow, bounded discovery task doesn't need the paid default the rest of
  the agent uses, using the per-subagent `SubAgent["model"]` override
  mechanism confirmed in `deepagents.graph` (`spec.get("model", model)`).
- `config.is_default_fixture()` - new gate: `DEFAULT_PAGES` is only ever
  correct for the bundled Hallucinate.io fixture, never a `--repo` override.
- Wired into both `cli.py::_cmd_audit` and `_acmd_run`'s "run a fresh
  audit" branch, gated on `is_default_fixture()` - the bundled fixture
  keeps using the fast, free, known-good `DEFAULT_PAGES` path unchanged;
  anything else now genuinely calls the crawler instead of silently
  scanning Hallucinate.io's own (wrong) route list against a different app.

**Deliberately out of scope for this pass** (separate, still-open thread):
reverting `.env`'s `A11Y_LLM_BACKEND` to ollama for the other 3 subagents.

Verified: 284 tests passed (was 272, +10 new: 2 `is_default_fixture` tests,
6 `discover_routes`/`discover_and_audit` tests, 2 cli.py gating tests), 4
e2e deselected, zero regressions.

---

## Recent Changes (2026-09-01 — `--url` live-site audit-only mode)

Added the mode flagged as out-of-scope in the previous pass: `python -m
a11y_fixer.cli audit --url <live-url>` audits an already-running site
directly - no clone, no `npm install`, no `ng serve`.

- `AxeAuditRunner.audit_urls(urls: list[str]) -> dict` - new method that
  scans arbitrary full URLs directly (no assumption they're this runner's
  own `host`/`port`), and touches no server lifecycle at all - a live site
  needs nothing started. `audit_pages()` is refactored to delegate to it
  (build `http://{host}:{port}{page}` urls, then call `audit_urls()`) -
  same observable behavior, confirmed by all its existing tests still
  passing unchanged.
- `cli.py::_audit_live_url(url)` - calls `audit_crawler.discover_routes(url)`
  directly (no `AxeAuditRunner` needed for discovery against a live site),
  joins each discovered relative route onto the given base URL via
  `urllib.parse.urljoin`, then calls the new `audit_urls()`. Falls back to
  auditing just the one given URL if discovery finds nothing -
  `DEFAULT_PAGES` would be actively wrong for an arbitrary external site.
- New `--url` flag on the `audit` subcommand only (mutually exclusive with
  `--repo`) - deliberately **not** added to `run`, since fixing a violation
  needs a real local, writable clone for `codebase_compiler` and PR
  delivery; there's nothing to write to for a live external URL.
- `agents/audit_crawler.py`'s `SYSTEM_PROMPT` tightened: routes must be
  relative paths (e.g. `"/about"`), not full URLs - the caller now joins
  them with whichever base URL applies (local dev server or live site),
  so this ambiguity needed to be pinned down explicitly rather than left
  implicit.

Verified: 291 tests passed (was 284, +7 new: 3 `audit_urls`/`audit_pages`-
delegation tests, 4 cli.py `--url` parser/dispatch tests), 4 e2e
deselected, zero regressions.

---

## Status At A Glance (2026-08-31, Phase E updated 2026-09-01, audit_crawler wired 2026-09-01)

**"Next Steps (What Remains)" section below is stale** — every item in it was
completed during the fresh-start rebuild. Kept as-is further down for the
migration reasoning; this table is the accurate status:

| #   | Planned step                            | Status  | Evidence                                                                                                                     |
| --- | --------------------------------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------- |
| 1   | Create `deep_agent.py`                  | ✅ Done | `abuild_agent()`/`build_agent()` call the real `create_deep_agent()`                                                         |
| 2   | Convert agents to `SubAgent` specs      | ✅ Done | all 4 `agents/*.py` modules return `deepagents.SubAgent`                                                                     |
| 3   | Wire HITL via `interrupt_on`            | ✅ Done | `deep_agent.py`: `interrupt_on={"write_file": ..., "edit_file": ...}`                                                        |
| 4   | Wire `RubricMiddleware`                 | ✅ Done | `codebase_compiler.py` attaches `RubricMiddleware(max_iterations=3)`                                                         |
| 5   | Wire `MemoryMiddleware`                 | ✅ Done | `memory=[...]` -> wiki `AGENTS.md`; `wiki_pipeline.py`                                                                       |
| 6   | Delete `orchestrator.py`                | ✅ Done | never exists in the rebuild; `ports.py` also correctly absent (layering superseded, per this doc's own Architecture section) |
| 7   | Phase C-G subagents as `SubAgent` specs | ✅ Done | `codebase_compiler`/`qa_critic`/`audit_crawler` all `SubAgent` specs                                                         |

**Phase-by-phase reality check:**

| Phase | Deliverable                                  | Status                   | Notes                                                                                                                                                                                                                                                                                                                                                                                                     |
| ----- | -------------------------------------------- | ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A     | Fixture app + submodule + benchmark          | ✅ Done                  | `Hallucinate.io` submodule; **22** real DOM-node violation instances (not 16, not 18 - see reconciliation note above)                                                                                                                                                                                                                                                                                     |
| B     | Skills, wiki, `deep_agent.py`                | ✅ Done                  | `.agents/skills/a11y-fixer/`, `wiki_pipeline.py`, `deep_agent.py`                                                                                                                                                                                                                                                                                                                                         |
| C     | ToT DFS + Codebase Compiler                  | ⚠️ Done differently      | `RubricMiddleware` replaces the live ToT loop (per this doc's own migration note); `domain/tot_search.py` kept as a pure algorithm for **offline** eval scoring only, not live. `adapters/sandbox/git_worktree.py` is real/tested but **not wired into the live Codebase Compiler** - it applies patches directly (permission-scoped) and verifies via the angular-cli MCP's `run_target`, not a worktree |
| D     | QA Critic + rubric                           | ✅ Done                  | `domain/rubric.py`, `agents/qa_critic.py` (chrome-devtools MCP)                                                                                                                                                                                                                                                                                                                                           |
| E     | Orchestration/guardrails/HITL/delivery       | ⚠️ Nearly done (data-calibration still pending) | `orchestrator.py` correctly deleted; `adapters/pr/delivery.py` matches the plan exactly. All 4 `guardrail_rules.py` predicates, `hitl_policy.assess_risk()`, **and now `hitl/review_queue.py`'s ROC/AUC Bounded Decider + a real `cli.py review` subcommand** are wired (see Recent Changes above) - routing, guardrails, and the reject/approve review loop are all real, not just the LLM's opinion. **Still missing:** `calibrate_from_results()` has never run against REAL data (`run_eval.py` still hasn't been executed for real) - `assess_risk()`'s floors remain the original hardcoded defaults, not yet data-calibrated                         |
| F     | Evaluation + trigger + report reconciliation | ⚠️ Partial               | `benchmark_cases.json` (22 real cases) + `run_eval.py` exist and are unit-tested; `triggers/github-actions/a11y-fixer.yml` exists. **`run_eval.py` has never actually been executed** - no `results_summary.json` exists yet. **`capstone-complete-compendium.md` §7 still has its original placeholder numbers**, not reconciled                                                                         |
| G     | Docker sandbox                               | ⚠️ Built, not integrated | `docker_backend.py` + `sandbox/Dockerfile` are real and tested (unit + real e2e container lifecycle) - confirmed via full-repo grep: zero references anywhere outside their own test files. Not used by the live agent (`permissions=` is incompatible with an execution-capable backend) or by `run_eval.py`                                                                                             |

**Genuinely still open, not just stale documentation:**

- Run `run_eval.py` for real against all 22 benchmark cases -> generate a real `results_summary.json`.
- Reconcile `capstone-complete-compendium.md` §7 against those real numbers.
- Decide whether to wire the Docker/git-worktree sandbox into something real, or relabel it in the file tree as reference-only.
- Backlog subagents (`color_contrast_vision`, `alt_text_context`) - never started, but that's expected: they were always labeled Future Enhancements, not a phase deliverable.
- **(2026-09-01)** Once a real `run_eval.py` run exists, wire `hitl/review_queue.calibrate_from_results()`'s output into `deliver_violation()`'s `assess_risk()` call so the P(IK) floor is actually data-calibrated instead of the current hardcoded default.
- **(2026-09-01)** The new `cli.py review` subcommand is CLI-only - the dashboard's Approve/Reject buttons still only write to `localStorage`; wiring them to actually invoke it (or an equivalent backend) remains open if a GUI reviewer flow is wanted.

| Change                               | Detail                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Skill architecture refactored        | Deleted `agent/skills/wcag-remediation/SKILL.md` + `references/`. Created `.agents/skills/a11y-fixer/SKILL.md` as composition root. WCAG knowledge fetched **live** from `wcag-mcp` at runtime — no static cache, no `lint` reconciliation.                                                                                                                                                                                                                                        |
| Renamed skill                        | `a11y-fixer-docs` → `cmu-capstone-docs` (matches `.vscode/mcp.json` exactly: wraps `https://mdrmtz.mintlify.site/mcp`, 9 published capstone pages).                                                                                                                                                                                                                                                                                                                                |
| a11y-fixer / cmu-capstone-docs split | `a11y-fixer` = runtime orchestration of the subagent (which skills to call, in what order, safety gates). `cmu-capstone-docs` = project knowledge (architecture, RAG design, ToT internals). DRY applied — no duplicated "Architecture Context" / "Key Source Files".                                                                                                                                                                                                              |
| Fixture: registered as git submodule | `Hallucinate.io/` formally registered as a git submodule at the repo root. `config.py` resolves `fixture_path` by walking `__file__` up 3 parent dirs — no hardcoded absolute path. `A11Y_FIXTURE_PATH` env var overrides if needed (CI always passes it explicitly for reliability across all checkout layouts).                                                                                                                                                                  |
| CLI default                          | `--live` / `--no-live` flags. Default follows `GITHUB_TOKEN` presence: live if set, dry-run otherwise. `--live` requires the token (else exit 3).                                                                                                                                                                                                                                                                                                                                  |
| Wiki role                            | Institutional memory only (HITL rejection lessons). Never authoritative for WCAG content.                                                                                                                                                                                                                                                                                                                                                                                          |
| AuditRunner adapter                  | `adapters/audit_runner.py` (243 lines) — lifecycle-managed `AxeAuditRunner` (`start_server()` → `audit_pages()` → `stop_server()`). `orchestrator.py` injects it via `audit_runner=`; `run(audit=None)` auto-runs. 20 adapter unit tests added (88 total: 68 domain + 20 adapter). `@axe-core/cli` installed in Hallucinate.io.                                                                                                                                                    |
| Benchmark reconciled                 | Real `npx @axe-core/cli --tags wcag2a,wcag2aa` against Hallucinate.io → **18 violations across 5 rules on 11 pages**. `html-has-lang` is site-wide (all 11 pages). `/home` and `/status` are NOT clean baselines. Rules not seen: `keyboard`, `label`, `heading-order`. New rules: `link-name`. Audit saved to `evaluation/results/audit.json`. `benchmark_cases.json` updated.                                                                                                    |
| Orchestrator fail-fast               | `orchestrator.run()` raises `RuntimeError` if `fixture_path` does not exist.                                                                                                                                                                                                                                                                                                                                                                                                       |
| pyproject.toml fixed                 | `dependencies` was a TOML table instead of a PEP 508 array; `pip install -e .` now succeeds.                                                                                                                                                                                                                                                                                                                                                                                       |
| AuditCrawlerAgent created            | `agents/audit_crawler.py` (244 lines) — LLM-powered audit that crawls the live app via Playwright MCP. Discovers routes dynamically from nav links (`browser_snapshot` + LLM parsing). Falls back to HTTP probing if Playwright MCP is not wired. **NOT yet wired into orchestrator** — next step.                                                                                                                                                                                 |
| Orchestration: deepagents adopted    | Phase B adopts `create_deep_agent` from `deepagents>=0.3.0` as the sole orchestration layer. Custom `Orchestrator` class replaced — no dual-path. Subagents (`CompliancePlanner`, `CodebaseCompiler`, `QACritic`, `AuditCrawlerAgent`) become `SubAgent` specs passed to `create_deep_agent` with `system_prompt`, `tools`, `skills`, `permissions`. HITL wired via `interrupt_on`. `RubricMiddleware` replaces manual ToT DFS. `MemoryMiddleware` replaces manual wiki retrieval. |
| CompliancePlanner wires wcag-mcp     | `CompliancePlanner._fetch_wcag_context()` calls `wcag-mcp` live: `search-wcag` → `get-full-criterion-context`. `RULE_TO_WCAG_QUERY` map bridges axe-core rule IDs. Still returns `fix_kind: stub` + `score: 0` — candidate generation is the next step.                                                                                                                                                                                                                            |

---

## Next Steps (What Remains)

> **Migration note (2026-08-31):** Phase A built a custom `Orchestrator` class. Phase B adopts `deepagents` as the sole orchestration layer. `agents/` remain as `SubAgent` specs (logic preserved; wiring changes only). Domain, ports, and adapters are unchanged.

1. **Create `deep_agent.py`** — call `create_deep_agent()` in `cli.py` instead of `Orchestrator`. Migrate all injection fields from `Orchestrator.__init__` to `create_deep_agent()` kwargs: `model`, `tools`, `subagents`, `skills`, `memory`, `permissions`, `interrupt_on`.
2. **Convert agents to `SubAgent` specs** — each `agents/*.py` becomes a `SubAgent` TypedDict with `name`, `description`, `system_prompt`, `tools`, `skills`. Remove `__init__` constructors; keep logic as pure functions called by the deep agent's tool wrappers.
3. **Wire HITL via `interrupt_on`** — migrate `domain/hitl_policy.py` decision logic to `interrupt_on` config. When `interrupt_on` fires, deep agent checkpoints and awaits human approval before continuing via LangSmith UI.
4. **Wire `RubricMiddleware`** — Phase C ToT DFS is replaced by `RubricMiddleware` (grader sub-agent loops until `satisfied`). Migrate `domain/tot_search.py` criteria to rubric JSON declared in `response_format`.
5. **Wire `MemoryMiddleware`** — replace `adapters/retrieval/wiki_pipeline.py` with `memory=["wiki/"]` passed to `create_deep_agent()`. HITL "reject + lesson" writes to `wiki/lessons/` via the deep agent's filesystem tool.
6. **Delete `orchestrator.py`** — all composition moves to `deep_agent.py`. Keep `config.py` and `ports.py`.
7. **Phase C–G subagents** — `CodebaseCompiler`, `QACritic`, `AuditCrawlerAgent` become `SubAgent` specs in the same `subagents=[]` list.

---

## Architecture

Ports & adapters layering is superseded by the `deepagents` middleware stack:

**Middleware stack order** (per `create_deep_agent`):
SkillsMiddleware → FilesystemMiddleware → SubAgentMiddleware → SummarizationMiddleware → PatchToolCallsMiddleware → AsyncSubAgentMiddleware → RubricMiddleware → MemoryMiddleware → HumanInTheLoopMiddleware (`interrupt_on`).

**Domain** (`domain/`) stays as pure logic (ToT, rubric math, HITL calibration). **Ports** (`ports.py`) defines contracts for adapters used by subagent tools (MCP clients, sandbox execute, PR delivery). **CLI** (`cli.py`) is the single entrypoint that builds the deep agent graph.

```
flowchart TD
    A["axe-core audit JSON"] --> A11Y["A11y Fixer\ncreate_deep_agent()"]
    A11Y --> CP["Compliance Planner\nSubAgent spec\n(wcag-mcp + a11y-fixer Skill)"]
    CP --> CC["Codebase Compiler\nSubAgent spec\n(angular-cli-mcp + sandbox execute)"]
    CC <--> SB["Docker Sandbox\n(git worktree + ng build/test + headless Chrome)"]
    CC --> QC["QA Critic\nSubAgent spec\n(RubricMiddleware: deterministic + LLM judge)"]
    QC -->|prune ≤5| CC
    QC -->|satisfied| FT["Fix delivery\n(interrupt_on → auto PR)"]
    QC -->|needs_revision| CC
    FT --> HITL["HITL: interrupt_on\nBounded Decider"]
    HITL -->|auto| PR["PR delivery\n(token-aware: --live/--no-live)"]
    HITL -->|human| HUMAN["Human review queue\n(checkpoint + resume)"]
    HUMAN -->|reject + lesson| MEM["MemoryMiddleware\n(wiki: ingest HITL lesson)"]
    MEM -.->|continual learning| CP
    A11Y -.->|SkillsMiddleware| A11Y_SKILL[".agents/skills/a11y-fixer/"]
    A11Y -.->|MemoryMiddleware| WIKI["wiki/lessons/\n(institutional memory)"]
```

**Parallelizable from day one** (no dependencies on fixture app or MCP wiring):

| Module               | Location                    | Content                                   |
| -------------------- | --------------------------- | ----------------------------------------- |
| ToT DFS              | `domain/tot_search.py`      | DFS algorithm, adaptive sibling inflation |
| Rubric scorer        | `domain/rubric.py`          | 0-20 composite scoring function           |
| Guardrail predicates | `domain/guardrail_rules.py` | P(IK), ECE, Brier calibration math        |
| HITL routing rules   | `domain/hitl_policy.py`     | Risk-routing decision predicates          |

All four are pure functions over plain data — buildable and unit-testable before any network tool exists.

---

## Phases

### Phase A — Scaffolding & Fixture App

**Depends on:** nothing
**Produces:**

- `agent/` package skeleton (`pyproject.toml`, `.env.example`, `src/a11y_fixer/` hierarchy)
  mirroring the `Module-07-Capstone-Project/capstone_samples_solution` README conventions
- `Hallucinate.io` is registered as a submodule at the repo root
  (`cmu-capstone/Hallucinate.io/`, upstream: `https://github.com/mdrmtz/Hallucinate.io.git`).
  No nested copy inside `agent/`. `config.py` resolves `fixture_path` by walking
  `__file__` up 3 parents to the repo root, then joining `Hallucinate.io`. Override
  with `A11Y_FIXTURE_PATH` for non-standard checkouts (CI always passes it explicitly).
  **Prerequisite:** run `cd Hallucinate.io && npm install --save-dev @axe-core/cli`
  before using the audit runner for the first time.
- No `ng new` needed. The fixture is Angular **22.1**, standalone components,
  `ChangeDetectionStrategy.OnPush`, `@angular/build:application` builder, **Vitest** test runner.

**Benchmark (reconciled with real axe-core output, 2026-08-30):**
**18 violation instances across 5 distinct rules, 11 pages.** (Plan originally projected
16 instances / 9 rules / 8 pages — those numbers were aspirational; the table below is the
ground truth from a real `npx @axe-core/cli --tags wcag2a,wcag2aa` run captured to
`evaluation/results/audit.json`.)

| Page            | axe-core rule(s)                               | WCAG tag(s)                        |
| --------------- | ---------------------------------------------- | ---------------------------------- |
| `/`             | `html-has-lang`                                | wcag311                            |
| `/product`      | `color-contrast`, `html-has-lang`              | wcag143, wcag311                   |
| `/case-studies` | `image-alt`, `html-has-lang`                   | wcag111, wcag311                   |
| `/docs`         | `html-has-lang`                                | wcag311                            |
| `/careers`      | `html-has-lang`                                | wcag311                            |
| `/blog`         | `button-name`, `link-name`, `html-has-lang`    | wcag412, wcag244, wcag311          |
| `/pricing`      | `html-has-lang`                                | wcag311                            |
| `/about`        | `image-alt`, `html-has-lang`                   | wcag111, wcag311                   |
| `/contact`      | `color-contrast`, `link-name`, `html-has-lang` | wcag143, wcag244, wcag412, wcag311 |
| `/home`         | `html-has-lang`                                | wcag311                            |
| `/status`       | `html-has-lang`                                | wcag311                            |

**Notes on the reconciliation:**

- `html-has-lang` is **site-wide** (every page inherits the missing `<html lang="en">`
  from `index.html`). The plan originally expected it only on `/`. All 11 pages audited
  are missing it.
- `/home` and `/status` are **NOT clean** as the plan claimed. Both have `html-has-lang`.
  They are still valid baselines for non-lang regressions once that's fixed.
- Rules from the plan that did NOT show up in real audit: `keyboard`, `label`, `heading-order`.
  Either the fixture's actual state is better than the plan assumed, or those rules are
  satisfied by the existing markup. Re-run after `html-has-lang` is fixed to be sure.
- Rules found that were NOT in the plan's table: `link-name` (appeared in `/blog` and
  `/contact`).

Phase A gate passes — fixture builds, dev server starts, axe-core runs against it, and the
audit captures all 18 violations in a single normalized JSON.

- Confirmed `wcag`/`angular-cli` MCP server connectivity from `cmu-capstone/.vscode/mcp.json`

**Done when:** `npm install && npm run build` passes inside the submodule;
`@axe-core/cli` is installed as a dev dependency in the submodule (`npm install --save-dev @axe-core/cli`);
`python -m evaluation.audit_runner --output evaluation/results/audit.json` exits 0,
spawns `ng serve`, runs `npx @axe-core/cli --save` against every Phase A page, and writes the
combined audit.json. (The `/home` / `/status` clean-baseline expectation was wrong — both have
`html-has-lang` site-wide; they remain clean for _every other rule_.)
**Produces:**

- `.agents/skills/a11y-fixer/SKILL.md` — a **Skill** that teaches the Compliance Planner
  how to query `wcag-mcp` at runtime to fix axe-core violations. The skill is the domain
  layer on top of `wcag-mcp`; wcag-mcp is the live authoritative source. The
  `cmu-capstone-docs` Skill provides the CMU capstone project documentation.
  No static `references/` cache — wcag-mcp is called live per violation.
- init/ingest/query pipeline (`adapters/retrieval/wiki_pipeline.py`).
  **Wiki is institutional memory only** — stores lessons from past HITL rejections.
  WCAG knowledge comes live from `wcag-mcp` at runtime; no static cache.
  No `lint` step — `wcag-mcp` is always current.
- MMR semantic-search fallback (`adapters/retrieval/semantic_search.py`, λ=0.5, k=3 diverse chunks)
  ported near-verbatim from `Module-03/hybrid_retrieval_demo.py`
-
- `deep_agent.py` — replaces `orchestrator.py`. Calls `create_deep_agent()` with:
  - `model` from `config.selected_llm_backend()` (Ollama/Anthropic/OpenAI/OpenRouter)
  - `tools` = axe-core audit runner + MCP tool wrappers (wcag, angular-cli, chrome-devtools, playwright)
  - `subagents` = list of `SubAgent` specs (CompliancePlanner, CodebaseCompiler, QACritic, AuditCrawlerAgent)
  - `skills` = `[".agents/skills/a11y-fixer/", ".agents/skills/cmu-capstone-docs/"]`
  - `memory` = `["wiki/"]` (MemoryMiddleware for HITL lessons)
  - `permissions` = Angular file scope (`**/*.component.{html,ts,scss}`)
  - `interrupt_on` = PR merge + high-risk rule edits (HITL Bounded Decider)
  - `response_format` = structured JSON per violation
- `agents/audit_crawler.py` — converted to `SubAgent` spec. **Update 2026-09-01:** now wired - `deep_agent.py` builds it alongside `compliance_planner`/`codebase_compiler`/`qa_critic` as one of 4 live subagents.
- `agents/compliance_planner.py` — converted to `SubAgent` spec with wcag-mcp tools. **explicitly attached** (subagents inherit neither
  skills nor memory from the orchestrator — confirmed by `deepagents-deep-dive` skills notebook)

**Wiki role:** institutional memory only — records HITL rejection lessons.
Never authoritative for WCAG content. Storage: local filesystem (`wiki/` dir).
Optional LangSmith ContextHub upgrade: documented as an upgrade path in the README.

**Done when:** `CompliancePlanner.plan()` calls `wcag-mcp` live for every violation;
no static `references/` cache is used.

---

### Phase C — Codebase Compiler Subagent + ToT Engine

**Depends on:** Phase B's compliance manifest schema (interface only; can start `tot_search.py`
pure logic before Phase B ships)
**Produces:**

- `domain/tot_search.py` — DFS, depth T=3, k=3→5 adaptive sibling inflation
  (contrastive negative constraints + temperature 0.2→0.6 on exhaustion), global cap 15 node evals,
  45 s/candidate timeout, prune at composite score ≤5
- `adapters/sandbox/git_worktree.py` — git-worktree isolation as plain Python tool functions
  (not a bespoke MCP server; internal and single-consumer so MCP protocol overhead is unjustified)
- `agents/codebase_compiler.py` using:
  - `angular-cli` MCP read-only: `get_best_practices`, `search_documentation`
    (version-aware — Angular 22 standalone components, no NgModules, `@if`/`@for` control flow)
  - deepagents' native `edit_file`/`write_file`
  - deepagents' filesystem `permissions=` rules: write-allow `**/*.component.{html,ts,scss}`,
    deny-all else — the guardrail is the architecture, not a bolt-on check
  - AST patches must preserve `ChangeDetectionStrategy.OnPush` and standalone `imports[]`;
    `get_best_practices` from the Angular CLI MCP returns version-specific guidance for both

**Done when:** one seeded violation produces a syntactically valid candidate patch on an isolated
worktree with zero bleed into the parent branch.

---

### Phase D — QA Critic Subagent & Rubric

**Depends on:** nothing for the scorer itself (pure function); wires into Phase G for live inputs
**Produces:**

- `domain/rubric.py` — pure 0–20 composite scorer:

  | Dimension                                               | Weight |
  | ------------------------------------------------------- | ------ |
  | Angular Ivy compile safety                              | 8 pts  |
  | AST/template structural validity                        | 4 pts  |
  | WCAG semantic compliance (LLM judge)                    | 5 pts  |
  | Visual layout stability (CLS ≤ 0.05, bounding-box ≤ 2%) | 3 pts  |

- Two-evaluator split per the `deepagents-deep-dive` evals notebook pattern:
  deterministic heuristic evaluator (build/test/CLS) + an LLM-judge WCAG-compliance check
- `agents/qa_critic.py` wiring the rubric to live tool outputs
- Test execution uses **Vitest** — the fixture's `npm run test` invokes
  `vitest` directly; `ng test` routes through the same runner via the Angular build configuration

**Done when:** scorer produces correct composite scores against hand-crafted fixture inputs
with no live tools involved.

---

### Phase E — Orchestration, Guardrails, HITL, Delivery

**Depends on:** B, C, D as importable subagents
**Produces:**

- `orchestrator.py` — one composition root via `create_deep_agent`, wires every port to its
  adapter; `interrupt_on` for high-blast-radius edits and PR merges (LangGraph native HITL)
- `domain/guardrail_rules.py`:
  - Pre-generation: Pydantic schema validation of inbound axe-core JSON; filepath
    path-traversal guard (extension whitelist)
  - During-generation: P(IK) epistemic monitor (block if < 0.75); overconfidence scanner
    — patterns ported from Module-06 Lab 1 notebook
- `hitl/review_queue.py` — Bounded Decider: triage/review, calibrated threshold (target FPR),
  ROC/AUC evaluation — ported from Module-06 Lab 2's `TrajectoryLogger→Monitor→ReviewQueue`
- Continual learning: HITL "Reject with Constraint" writes the lesson to
  `wiki/lessons/` — HITL lessons written by Phase E — pattern from
  `deepagents-with-langsmith/agents/memory_backed_agent/`
- `adapters/pr/delivery.py` implementing the `PRDelivery` port:
  - **Default (token-aware):** live if `GITHUB_TOKEN` is set in `.env`, dry-run otherwise.
    `--no-live` forces dry-run even with a token; `--live` requires a token (else exit 3).
  - **Dry-run path:** writes a unified diff + markdown PR description to disk — the
    safe default for unattended GitHub Action runs.
  - **Live path:** real GitHub PR via `@modelcontextprotocol/server-github`, gated on
    `GITHUB_TOKEN` + explicit user opt-in.

**Done when:** one low-risk seeded violation runs unattended to a dry-run diff; one high-risk
case routes to the human queue; one rejection cycles a lesson back into the wiki.

---

### Phase F — Evaluation, Autonomy Trigger, Report Reconciliation

**Depends on:** E
**Produces:**

- `evaluation/benchmark_cases.json` — **16 benchmark cases** derived directly from the
  Hallucinate.io fixture, one entry per violation instance:
  `{ "page": "/blog", "rule": "button-name", "selector": "article:first-child button",
"wcag": "4.1.2", "ground_truth_fix": "add [attr.aria-label]\"..\" to the button" }`
- `evaluation/run_eval.py` — full end-to-end pipeline over each case, computing real
  HELM-aligned metrics:

  | Metric                            | Tool                                              |
  | --------------------------------- | ------------------------------------------------- |
  | Build pass rate                   | `ng build` (via Angular CLI MCP)                  |
  | Unit test pass rate               | `ng test` (via Angular CLI MCP)                   |
  | Violation clearance               | `lighthouse_audit` (chrome-devtools MCP)          |
  | W3C Lexical Support Metric ≥ 0.85 | LLM judge + wcag MCP                              |
  | ECE, Brier score                  | `domain/guardrail_rules.py`                       |
  | CLS, bounding-box drift           | chrome-devtools `performance_*` + `take_snapshot` |
  | Latency                           | wall-clock per violation                          |
  | Human escalation rate             | `hitl/review_queue.py` stats                      |

- Reconcile Section 7 of `Module-07-Capstone-Project/capstone-complete-compendium.md` —
  replace fabricated numbers with real measured results, with transparent sample-size notation
- `triggers/github-actions/a11y-fixer.yml` — minimal unattended trigger: on new axe-core
  audit file landing → invoke `python -m a11y_fixer.cli run --audit <path>` with no manual step
  (the concrete proof of "autonomous," not just the narrative)

Optional upgrade: pass `LANGSMITH_API_KEY` + `LANGSMITH_TRACING=true` to stream full
execution traces to LangSmith; not required for grading.

**Done when:** `results_summary.json` contains real numbers; trigger fires without a human
touching the CLI; report numbers are reconciled.

---

### Phase G — Containerized Execution Sandbox

**Depends on:** conceptually nothing (adapter swap); practically, build after C/D prove out
against a simple local backend — Phase G is a **drop-in replacement** for that backend, with
zero changes to domain or subagent code
**Produces:**

- `sandbox/Dockerfile` — FROM the official Playwright image (Chromium, OS deps, Node LTS) plus `@angular/cli` global and fixture `node_modules`
- `adapters/sandbox/docker_backend.py` — custom `DockerSandboxBackend(BaseSandbox)`:
  - `execute(cmd)` → `docker exec <container> sh -lc "<cmd>"`
  - File transfer → `docker cp`
  - "Sandbox as tool" pattern (LangChain's recommended approach): agent code and all credentials
    stay on the host; only shell calls hop into the container
  - One ephemeral `docker run --rm` container per ToT node eval, worktree mounted at `/workspace`
  - Container entrypoint: headless Chrome (`--remote-debugging-port=9222 --no-sandbox
--headless=new`) + `ng serve --host 0.0.0.0`; ports mapped dynamically
- Host-level MCP servers (from `cmu-capstone/.vscode/mcp.json`) attach to the in-container browser:
  - `chrome-devtools` via `--browser-url=http://127.0.0.1:<mapped-9222-port>`
  - `playwright` via `--cdp-endpoint=` same port
  - MCP processes themselves never run inside the container

**Cost split** (per playwright-mcp's own README guidance on token efficiency):

| Phase                           | Check                 | Tools used                                                                                         |
| ------------------------------- | --------------------- | -------------------------------------------------------------------------------------------------- |
| Inner DFS loop (≤15 candidates) | `ng build`, `ng test` | `execute()` only                                                                                   |
| Surviving branch                | Full rich audit       | `take_snapshot`, `lighthouse_audit`, `list_console_messages`, `performance_start_trace/stop_trace` |

**Network guardrail:** `--allowedUrlPattern` (chrome-devtools) + `--allowed-origins`
(playwright) locked to `http://127.0.0.1:4200` only — network exfiltration guardrail at
browser level, layered on Docker's own network restriction.
`docker rm -f` in a `finally` block on every node eval — full OS-level teardown regardless of
outcome.

**Done when:** `DockerSandboxBackend` is swapped in with no domain or subagent code changes;
container is confirmed absent from `docker ps` after both success and failure paths.

---

## File Tree (`cmu-capstone/agent/`)

```
agent/
├── pyproject.toml
├── .env.example
├── README.md
├── sandbox/
│   └── Dockerfile
├── skills/
│   └── (runtime skills live in `.agents/skills/`)
├── wiki/
│   ├── lessons/                   # HITL rejection lessons (institutional memory)
│   └── log.md                    # architectural decisions
├── src/
│   └── a11y_fixer/
│       ├── config.py
│       ├── cli.py
│       ├── deep_agent.py          # create_deep_agent() composition root
│       ├── ports.py              # Protocol ABCs only where 2+ impls exist
│       ├── domain/
│       │   ├── tot_search.py
│       │   ├── rubric.py
│       │   ├── guardrail_rules.py
│       │   └── hitl_policy.py
|       ├── agents/
│       │   ├── audit_crawler.py          # LLM-powered Playwright crawler (not yet wired)
│       │   ├── compliance_planner.py
│       │   ├── codebase_compiler.py
│       │   └── qa_critic.py
│       ├── adapters/
│       │   ├── mcp_clients.py
│       │   ├── retrieval/
│       │   │   ├── semantic_search.py
│       │   │   └── wiki_pipeline.py
│       │   ├── sandbox/
│       │   │   ├── docker_backend.py
│       │   │   └── git_worktree.py
│       │   └── pr/
│       │       └── delivery.py
│       └── hitl/
│           └── review_queue.py
├── evaluation/
│   ├── benchmark_cases.json
│   ├── run_eval.py
│   └── results/
│       └── results_summary.json
├── triggers/
│   └── github-actions/
│       └── a11y-fixer.yml
└── tests/
    ├── domain/        # zero network/Docker/Ollama — pure unit tests
    ├── adapters/      # mocked ports
    └── e2e/           # one real fixture run
```

---

## Verification Gates

| Gate                          | What runs                              | Dependency        |
| ----------------------------- | -------------------------------------- | ----------------- |
| `domain/` unit tests          | pytest, zero network                   | Nothing — day one |
| `adapters/` tests             | mocked ports                           | Nothing — day one |
| Single end-to-end (low risk)  | Full pipeline → `--no-live` diff       | E                 |
| Single end-to-end (high risk) | Full pipeline → HITL queue             | E                 |
| Benchmark run                 | `run_eval.py` → `results_summary.json` | F                 |
| Autonomy trigger              | GitHub Action fires CLI on new audit   | F                 |

---

## Key Decisions

| Decision          | Choice                                     | Rationale                                                                          |
| ----------------- | ------------------------------------------ | ---------------------------------------------------------------------------------- |
| Agent framework   | `deepagents` SDK (`create_deep_agent`)     | Need explicit ToT DFS control; `dcode` CLI is too opinionated                      |
| LLM backend       | Local Ollama default, pluggable            | Matches existing demos; zero API key; cloud provider via env var                   |
| Execution sandbox | Custom `DockerSandboxBackend`              | No paid cloud sandbox required; deepagents ships no local Docker backend           |
| Browser MCP       | `chrome-devtools` + `playwright` host-side | Both already in `.vscode/mcp.json`; attach to container's CDP port                 |
| angular-cli-mcp   | Real official `@angular/cli mcp`           | Already configured; no bespoke server needed                                       |
| a11y-state-mcp    | Plain Python tool functions                | Internal/single-consumer; MCP overhead unjustified                                 |
| PR delivery       | Token-aware default; `--no-live` to force  | Live if `GITHUB_TOKEN` is set, dry-run otherwise; CI passes `--no-live` for safety |
| Knowledge base    | Local Skill/wiki on FilesystemBackend      | Free, offline; ContextHubBackend is a documented optional upgrade                  |
| Evaluation output | Local JSON default                         | LangSmith tracing stays optional throughout                                        |
| Report numbers    | Reconcile with real results                | Fabricated numbers in compendium Section 7 are a rigor gap                         |

---

## deepagents SDK Reference

### Entry point: `create_deep_agent`

```python
from deepagents import create_deep_agent, SubAgent

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-20250514",  # config.selected_llm_backend()
    tools=[axe_audit_tool, mcp_wcag_tool, mcp_angular_tool, mcp_chrome_tool, mcp_playwright_tool],
    subagents=[
        SubAgent(name="compliance_planner", description="Resolves WCAG 2.2 AA violations using wcag-mcp live.", system_prompt="...", skills=[".agents/skills/a11y-fixer/"]),
        SubAgent(name="codebase_compiler", description="Compiles and builds Angular accessibility fixes.", system_prompt="...", skills=[".agents/skills/angular-cli-mcp/"]),
        SubAgent(name="qa_critic", description="Scores fix candidates against a 0-20 rubric.", system_prompt="..."),
        SubAgent(name="audit_crawler", description="Crawls the app and discovers routes for axe-core audit.", system_prompt="...", skills=[".agents/skills/playwright-mcp/"]),
    ],
    skills=[".agents/skills/a11y-fixer/", ".agents/skills/cmu-capstone-docs/"],
    memory=["wiki/"],                              # MemoryMiddleware: HITL lessons persist here
    permissions=[
        FilesystemPermission(path="Hallucinate.io/**/*.component.{html,ts,scss}", mode="write"),
        FilesystemPermission(path="Hallucinate.io/**/*", mode="read"),
    ],
    interrupt_on={                                 # HITL Bounded Decider
        "write_file": InterruptOnConfig(when="always"),
        "execute": InterruptOnConfig(when="always"),
    },
    response_format=ViolationResponse,
    backend=DockerSandboxBackend(...),
)
```

### SubAgent spec

```python
from deepagents import SubAgent

SubAgent(
    name="compliance_planner",          # used in task() tool call
    description="Resolves WCAG 2.2 AA violations using wcag-mcp live.",  # model routes by this
    system_prompt="You are a WCAG compliance planner. Given an axe-core violation...",  # injected on activation
    tools=[mcp_wcag_tool, mcp_angular_tool],   # or None → inherits main agent tools
    skills=[".agents/skills/a11y-fixer/"],     # loaded only when this subagent is called
    permissions=[...],                          # replaces parent permissions for this subagent
    interrupt_on={...},                         # per-subagent HITL
)
```

### Middleware stack (in order)

| #   | Middleware                 | Purpose                                                   |
| --- | -------------------------- | --------------------------------------------------------- |
| 1   | `SkillsMiddleware`         | Loads `.agents/skills/*/` on subagent activation          |
| 2   | `FilesystemMiddleware`     | Built-in: `ls`, `read_file`, `write_file`, `glob`, `grep` |
| 3   | `SubAgentMiddleware`       | Routes `task()` calls to named subagents                  |
| 4   | `SummarizationMiddleware`  | Keeps transcript under context window                     |
| 5   | `PatchToolCallsMiddleware` | Patches tool call format                                  |
| 6   | `AsyncSubAgentMiddleware`  | Background subagent lifecycle                             |
| 7   | `RubricMiddleware`         | Self-evaluated iteration loop (Phase C ToT replacement)   |
| 8   | `MemoryMiddleware`         | `wiki/` persistent HITL lesson memory                     |
| 9   | `HumanInTheLoopMiddleware` | `interrupt_on` checkpoint + resume                        |

### HITL via `interrupt_on`

```python
from langchain.agents.middleware import InterruptOnConfig

interrupt_on={
    "write_file": InterruptOnConfig(when="always"),   # human approves every file edit
    "edit_file": InterruptOnConfig(when="always"),
    "execute": InterruptOnConfig(when="always"),       # human approves ng build
    "pr_submit": InterruptOnConfig(when="always"),    # human approves merge
}
```

When `interrupt_on` fires: deep agent checkpoints graph state, awaits human via LangSmith UI or webhook, then resumes. No custom `hitl/review_queue.py` needed — `HumanInTheLoopMiddleware` handles the lifecycle.

### RubricMiddleware (Phase C ToT replacement)

```python
from deepagents import RubricMiddleware

RubricMiddleware(
    rubric={
        "wcag_lexical_support": "Alt text describes semantic intent, not visual description.",
        "build_passes": "ng build exits 0.",
        "axe_clear": "Re-run axe-core; no regressions in this rule.",
    },
    max_iterations=3,   # k=3→5 adaptive sibling inflation maps to this
)
```

Grader sub-agent loops until `satisfied` or `max_iterations` — replaces the manual ToT DFS loop.

---

## Further Considerations

1. **Docker:** Confirm Docker Desktop (or equivalent) + Node/`npx` are available in this
   dev environment before Phase G starts.
2. **Live GitHub PR:** defaults follow `GITHUB_TOKEN` presence — live if set,
   dry-run otherwise. `--no-live` forces dry-run even with a token; `--live` requires
   the token. Token already provisioned in `.env` (PAT scoped to `mdrmtz/Hallucinate.io`,
   Contents + Pull requests + Metadata R/W). Dry-run remains the safest default for
   unattended triggers (`triggers/github-actions/a11y-fixer.yml` passes `--no-live`).
3. **LangSmith:** all LangSmith features (Context Hub, evals tracing) remain optional
   throughout — no account required by default.

---

## Future Enhancements (Backlog)

### Feature: Vision-Assisted Contrast Validation (Playwright + VLM)

**Status:** Idea / Nice-to-Have

**Component:** Agentic Routing Engine & Evaluation Tools

**Targeted WCAG Rule:** `color-contrast` (1.4.3)

#### 1. Problem Statement

Currently, the `color-contrast` rule is hardcoded as a `HIGH_RISK_RULE` in the HITL routing policy. Static DOM analysis tools (like axe-core) routinely fail to evaluate text contrast over CSS gradients, multi-layered opacities, or complex background images. As a result, all contrast fixes are routed to the async human review queue, creating a potential bottleneck.

#### 2. Proposed Architecture

To reduce the manual review queue, we can upgrade the agent with multimodal evaluation capabilities, transitioning contrast validation from a strict "always human" rule to a dynamic, confidence-based routing model.

The proposed workflow integrates three components:

- **Playwright Bounding-Box Snapshots:** Instead of analyzing the raw DOM, the agent uses a Playwright tool integration to capture a targeted, element-level screenshot (`elementHandle.screenshot()`) of the flagged UI component, representing the exact pixels rendered to the user.
- **Deterministic Image Processing (The Math):** Because Vision-Language Models (VLMs) cannot mathematically calculate relative luminance and will hallucinate passing scores based on "vibes," the agent triggers a deterministic Python tool (via OpenCV or Pillow). This tool extracts the dominant foreground and background pixels to calculate the precise WCAG ratio (e.g., 4.5:1).
- **VLM Orchestration & Confidence Routing (The Judge):** An LLM evaluates the results. If the mathematical tool returns high confidence on a solid background, the agent auto-applies the fix (Low Risk). If the tool struggles to isolate a single background color (e.g., text layered over a busy photograph), the agent flags low confidence and routes the task to the HITL queue.

#### 3. Expected Impact

- **Efficiency:** Significantly reduces the volume of the HITL queue by safely auto-resolving standard, solid-color contrast violations.
- **Accuracy:** Eliminates false positives caused by static DOM scanners failing to read CSS visual layers.
- **Human Focus:** Ensures human reviewers only spend time on genuine visual edge cases requiring subjective judgment.

### Feature: Context-Aware Alt Text Generation (DOM + VLM)

**Status:** Advanced / Research

**Component:** Semantic Analysis Engine

**Targeted WCAG Rule:** `image-alt` (1.1.1)

#### 1. The MCP Toolchain

To solve the "intent" problem, the agent needs three specific context-gathering tools before it makes a decision:

- **`Get_DOM_Neighborhood` (Text & Structure Tool):** An MCP that extracts the raw HTML of the image's parent container and its immediate siblings. It extracts any visible text immediately preceding or following the image.
- **`Check_Interactivity` (Functional Tool):** An MCP that determines if the image is wrapped inside an `<a>`, `<button>`, or has a JavaScript `onClick` event bound to it.
- **`Playwright_Screenshot` (Spatial Tool):** Captures the visual layout to see _where_ the image sits (e.g., is it a tiny icon next to a text label, or a massive hero image?).

#### 2. The LLM "Chain-of-Thought" Decision Tree

Once the MCPs gather the data, the LLM is prompted to execute the official W3C Alt Text Decision Tree, categorizing the image into one of three states before writing _any_ text:

**State A: Functional / Interactive**

- _Data:_ `Check_Interactivity` returns `True` (e.g., a magnifying glass icon inside a `<button>`).
- _Agent Action:_ Ignore what the image looks like. The alt text MUST describe the _action_.
- _Output:_ `alt="Search"`

**State B: Redundant / Decorative**

- _Data:_ `Get_DOM_Neighborhood` reveals the adjacent text is "Download PDF". The VLM sees an icon of a floppy disk next to it.
- _Agent Action:_ The image adds no new semantic value; the adjacent text handles the job.
- _Output:_ `alt=""` (Null, effectively silencing it for screen readers).

**State C: Informative**

- _Data:_ The image is a standalone infographic. `Get_DOM_Neighborhood` shows no adjacent text explaining the data.
- _Agent Action:_ Now, and only now, does the LLM act as a vision captioner to describe the data.
- _Output:_ `alt="Bar chart showing Q3 revenue growth of 15%..."`

#### 3. Confidence & HITL Routing

Just like the contrast tool, you keep the human in the loop for ambiguity.

- If the image is a complex graph, a meme, or a highly abstract brand illustration, the VLM flags its semantic confidence as low.
- The agent drafts a _suggested_ alt text and routes it to the human review queue, attaching the DOM context for the reviewer to approve or reject.

By building this MCP toolchain, the agent stops blindly describing "a brown dog" and starts understanding that the dog is just a decorative mascot next to an "About Us" paragraph.

---

### Cross-Cutting Backlog Principle: Sub-Agent Per Specialised Case

All backlog items above (and any future case-specific enhancements) follow the same architectural pattern: **each one is implemented as its own dedicated sub-agent**, invoked by the orchestrator only when its targeted rule is encountered. This keeps each capability isolated, independently testable, and swappable without touching the core pipeline.

**Why sub-agents, not inline code:**

- **Single responsibility.** A `ColorContrastVisionSubagent` owns Playwright screenshots + OpenCV luminance + VLM confidence routing. A `AltTextContextSubagent` owns DOM neighborhood + interactivity + W3C decision tree. Neither knows about the other.
- **Independent verification.** Each sub-agent has its own rubric entry, its own test fixtures, and its own confidence threshold. You can score them separately in `run_eval.py`.
- **Lazy wiring.** The orchestrator instantiates a sub-agent only when the rule is present in the audit. If Hallucinate.io has no `color-contrast` violations after a fix, the sub-agent is never loaded — zero cost.
- **Reusable in isolation.** A reviewer can invoke `python -m a11y_fixer.agents.color_contrast_vision --url <page>` for a one-off check, without running the full ToT DFS pipeline.
- **Swappable implementations.** Today's `color-contrast` heuristic is deterministic math + VLM judge. Tomorrow it can be a fine-tuned model. The orchestrator contract stays the same.

**Concretely, each backlog item becomes:**

| Backlog item                        | `SubAgent` spec                               | deepagents wiring                                |
| ----------------------------------- | --------------------------------------------- | ------------------------------------------------ |
| Vision-Assisted Contrast Validation | `SubAgent(name="color_contrast_vision", ...)` | Added to `subagents=[]` in `create_deep_agent()` |
| Context-Aware Alt Text Generation   | `SubAgent(name="alt_text_context", ...)`      | Added to `subagents=[]` in `create_deep_agent()` |
| (future) Keyboard trap detection    | `SubAgent(name="keyboard_trap", ...)`         | Added to `subagents=[]` in `create_deep_agent()` |
| (future) Focus order validation     | `SubAgent(name="focus_order", ...)`           | Added to `subagents=[]` in `create_deep_agent()` |

The backlog subagents slot into the same `subagents=[]` list. `SubAgentMiddleware` routes by `name` — no custom registry needed. Each sub-agent is independently testable via `create_deep_agent(tools=[...], subagents=[<SubAgent>])`.
