# Plan: Full E2E validation of The A11y Fixer against 100% of agent-plan.md

## Context/findings (grounded this session)
- `cmu-capstone/` is its OWN nested git repo (remote `mdrmtz/cmu-capstone`, currently
  on branch `mdrmtz/dormant-to-live`, tracks `origin/main`). `cmu-capstone/agent/`
  has no separate `.git` - plain subdirectory. Outer workspace repo
  (`mdrmtz/cmu-agentic-ai-program-2026`, branch `master`) is unrelated to this work.
- `cmu-capstone/.env` has REAL secrets (GITHUB_TOKEN fine-grained PAT scoped to
  mdrmtz/Hallucinate.io w/ Contents+PRs R/W; OPENROUTER_API_KEY paid;
  LANGSMITH_API_KEY, LANGSMITH_TRACING=true). Gitignored, never committed - but
  now sits in this chat transcript. User decision: proceed now, rotate after.
- `A11Y_LLM_BACKEND=openrouter`, `A11Y_LLM_MODEL=meta-llama/llama-3.3-70b-instruct`
  (paid, not free-tier) drives compliance_planner/codebase_compiler/qa_critic.
  audit_crawler alone defaults to `openrouter:openrouter/free`.
- `run_eval.py` defaults live=False regardless of GITHUB_TOKEN presence (argparse
  --live/--no-live both `store_true`, default False) - explicit `--live` always
  required, even for a phases.yaml phase with `live: true` (e.g. `f3` just prints
  a warning and stays dry-run unless `--live` passed).
- BUG FOUND: `_run_one_case()` (evaluation/run_eval.py) only calls
  `cli.deliver_violation()` (which resets the fixture's git working tree) on the
  success path. On `asyncio.TimeoutError` (120s cap) or any `Exception`, it
  returns early WITHOUT resetting - codebase_compiler's real file writes to the
  actual Hallucinate.io fixture can leak uncommitted into the next case's diff.
- `assess_risk()` (domain/hitl_policy.py) ALREADY accepts an optional
  `p_ik_floor` param (defaults to `DEFAULT_P_IK_FLOOR=0.75`) - the gap is purely
  that `cli.py::deliver_violation()`'s call site never passes anything else, and
  no caller ever invokes `hitl/review_queue.py::calibrate_from_results()`. No
  `calibrate` CLI subcommand exists.
- `wiki_pipeline.ingest_lesson()` DOES have a real caller now (`ReviewQueue.
  review(decision="reject")`, added in Phase E.3) - agent-plan.md's "zero live
  callers" claim is STALE (written before E.3), needs correcting.
- GitHub Actions trigger (`agent/triggers/github-actions/a11y-fixer.yml`) is a
  reference copy; real deploy target is `cmu-capstone/.github/workflows/`
  (confirmed via cmu-capstone/.git/config's own remote) - `cmu-capstone/.github/`
  exists but has no `workflows/` yet. Workflow needs repo secrets
  (OPENROUTER_API_KEY etc.) + a repo/env var (A11Y_LLM_BACKEND) configured on
  `mdrmtz/cmu-capstone` GitHub settings - manual, no tool available to set these.
  MCP servers used at runtime: 3 stdio (`npx @angular/cli mcp`,
  `chrome-devtools-mcp@latest`, `@playwright/mcp@latest` - spawned on demand,
  need only Node+network) + 3 streamable_http (wcag/docs-langchain/
  reference-langchain - just need outbound network). No explicit browser-install
  step in the workflow - real first CI fire is a legitimate risk point.
- Phase F's `compute_metrics()` only produces: total_cases,
  violation_clearance_rate, human_escalation_rate, error_rate,
  mean_latency_seconds, brier_score, expected_calibration_error, by_rule. It
  does NOT surface build-pass-rate, unit-test-pass-rate, W3C LSM, or CLS as
  top-level metrics (Phase F's originally-envisioned full metric table is a
  superset of what's actually aggregated today).
- `capstone-complete-compendium.md` "## 7. Evaluation and Results" (~line 1223)
  is 100% fabricated (50 cases, invented numbers) - reconciliation target.
- Backlog subagents (`color_contrast_vision`, `alt_text_context`): confirmed no
  files exist anywhere - never started, always Future Enhancements, out of scope.
- Dashboard (`cmu-capstone/dashboard/hitl_queue/index.html`): confirmed static
  HTML+JS, Approve/Reject buttons only write to localStorage - no backend call.

## User decisions (via vscode_askQuestions this session)
- Live PR delivery: LIVE for a small subset (1-2 cases only), not all/none.
- GitHub Actions: deploy + fire a REAL run (not just local simulation).
- Phase G (Docker/git-worktree sandbox): leave OUT of scope now, note as future work.
- Timeout/reset bug: FIX FIRST, before running the real 22-case benchmark.
- Credentials: proceed now with current keys, rotate AFTER everything below.

## Phases (Phase 0 blocks Phase 2; Phase 3/4 depend on Phase 2's data; Phase 5/6 independent, can run any time after Phase 0; Phase 7/8 depend on all data-producing phases)

### Phase 0 - Prerequisite code changes

**Phase 0.1 — File Locator Tool** *(Critical blocker, fixes codebase_compiler file-discovery failures)*
- Create `adapters/file_locator.py`: new `locate_selector_in_component()` function to map CSS selectors to component template files
- Integrate into codebase_compiler's SYSTEM_PROMPT; tool uses `glob` + `grep` + HTML regex heuristics
- Add unit tests; target ≥90% file location accuracy
- **Evidence of need:** PHASE_F_FINDINGS.md showed 40-66% file-location failures; PRs #8/#9 on mdrmtz/Hallucinate.io show placeholder edits instead of real component fixes
- **Detailed implementation plan:** see `0-1-FILE-LOCATOR-IMPLEMENTATION.md` (in this folder)
- **Timeline:** ~2 hours (runs in parallel with 0.2 and 0.3 below)

**Phase 0.2 — Fix git-reset bug**
1. Fix `_run_one_case()` (evaluation/run_eval.py): ensure the fixture's git
   working tree is ALWAYS reset after each case, even on timeout/exception -
   e.g. wrap each attempt's body so `cli._capture_and_reset_git_changes(fixture)`
   runs unconditionally (idempotent: a no-op if `deliver_violation` already
   consumed/reset it on the success path).

**Phase 0.3 — Wire real P(IK) calibration**
2. Thread an optional `p_ik_floor` parameter from
   `cli.py::deliver_violation()` down into its `assess_risk()` call (the param
   already exists on `assess_risk`, just never populated). Resolve the floor
   once per run in `_cmd_run`/`_acmd_run` (cli.py) and `_arun_eval`
   (run_eval.py) by calling `hitl.review_queue.calibrate_from_results()`
   against the latest `evaluation/results/results_summary.json` if it exists
   (already falls back to `DEFAULT_P_IK_FLOOR` otherwise - no behavior change
   until real data exists).

**Phase 0.4 — Full test suite**
3. Add unit tests for 0.2 and 0.3; run full suite (expect >291 passing, zero
   regressions)

### Phase 1 - Smoke validation (cheap, dry-run, first-ever real LLM call through this harness)
1. `python -m evaluation.run_eval --phase smoke` (case-01 only, dry-run).
2. Inspect `results_phase_smoke.json`: sane route/rubric_score/cleared/latency,
   no LangSmith/OpenRouter errors. Stop and diagnose before Phase 2 if this fails.

### Phase 2 - Full 22-case dry-run benchmark (the core Phase F deliverable)
1. `python -m evaluation.run_eval --phase all` (all 22 cases, dry-run).
2. Exercises: Phase A (real audit re-check per case), B (real abuild_agent/
   skills/wiki), C (real RubricMiddleware refinement, direct-write-then-reset
   on the real fixture, no sandbox), D (real score_rubric calls), E (real
   assess_risk/validate_write_path/epistemic_gate/deliver_violation routing +
   dry-run PR adapter), F (real aggregate metrics) - everything except Phase G,
   live PR delivery, the CI trigger, and any human review decision.
3. Produces the first-ever real `results_summary.json`/`results_phase_all.json`.

### Phase 3 - Human review loop (*depends on Phase 2*; exercises what a benchmark run alone can't)
1. `python -m a11y_fixer.cli review --list` to see any case routed to "human".
2. If ≥1 exists: `review <item> --reject --notes "..."` on one (exercises
   `ingest_lesson()` for real, first-ever write to `wiki/lessons/`) and
   `--approve` on another if available (exercises the re-apply-persisted-diff
   path for the first time).
3. If zero cases escalate: note as an accepted gap rather than contriving one
   (flag to user as a Further Consideration, don't force it silently).

### Phase 4 - Calibration in effect (*depends on Phase 2 + Phase 0.2*)
1. Confirm `calibrate_from_results()` now returns a real calibrated floor
   (not the hardcoded default) once `results_summary.json` exists.
2. Re-run a small subset (e.g. `--case-ids` a handful spanning multiple rules)
   with the calibrated floor active; compare human-escalation-rate/routing
   against Phase 2's run to demonstrate the calibration loop is real.

### Phase 5 - Live PR delivery smoke test (*independent of 3/4; manual, local, NOT via CI*)
1. Pick 1-2 low-risk cases (e.g. simple image-alt fixes) via
   `--case-ids case-XX,case-YY`.
2. `python -m evaluation.run_eval --case-ids case-XX,case-YY --live` - requires
   typing "yes" at the interactive confirmation prompt.
3. Verify on GitHub that a real PR was opened on `mdrmtz/Hallucinate.io` with
   the expected diff/description.
4. **Requires an explicit in-the-moment go-ahead at execution time** (opening
   a live PR is hard to reverse) - this plan documents the step, doesn't
   pre-authorize the action itself.

### Phase 6 - GitHub Actions CI trigger validation (*independent; always dry-run by the workflow's own design*)
1. Create `cmu-capstone/.github/workflows/a11y-fixer.yml` with the contents of
   `cmu-capstone/agent/triggers/github-actions/a11y-fixer.yml` (`cmu-capstone/
   .github/` already exists with just a `skills/` subfolder; `workflows/` does
   not exist yet - creating the file creates that directory too, same as any
   normal file write to a new path. No separate "set up workflows dir" step
   or GitHub-side registration needed - it's auto-discovered on next push).
2. **Manual prerequisite (user, not me):** configure `mdrmtz/cmu-capstone`
   repo secrets (OPENROUTER_API_KEY or ANTHROPIC/OPENAI) + repo/env var
   `A11Y_LLM_BACKEND` - no available tool sets GitHub repo secrets.
3. Commit + push a change to `cmu-capstone/agent/evaluation/results/audit.json`
   (regenerate via a fresh audit) to trigger the workflow's `on: push: paths:`
   condition. **Requires explicit go-ahead at execution time** (push to a
   shared remote).
4. Watch the real run complete; confirm it's dry-run (`--no-live --yes`
   hardcoded) - produces log/diff artifacts, never a PR.
5. Known risk: no explicit browser-install step for Playwright/chrome-devtools
   MCP servers - first real fire may fail on that; be ready to add
   `npx playwright install --with-deps chromium` if so.

### Phase 7 - Documentation reconciliation (*depends on Phase 2/4's real numbers*)
1. Replace `Module-07-Capstone-Project/capstone-complete-compendium.md`'s
   "## 7. Evaluation and Results" fabricated 50-case table with real 22-case
   numbers, honest sample-size notation. Flag which metrics `compute_metrics()`
   doesn't surface today (build/test pass rate, W3C LSM, CLS) as a scoping
   note rather than inventing them.
2. Fix agent-plan.md's stale "ingest_lesson() has zero live callers" claim.
3. Document the Phase G "left out of scope, future work" decision explicitly
   in agent-plan.md's Phase-by-phase table.

### Phase 8 - Wrap-up
1. Full test suite run, confirm zero regressions.
2. Update agent-plan.md changelog + "Genuinely still open" bullets (close:
   run_eval executed, compendium reconciled, calibration wired; keep Phase G
   and dashboard wiring as explicitly deferred).
3. Update `/memories/repo/a11y-fixer-agent.md` with real benchmark numbers,
   calibration outcome, live PR proof, CI trigger proof.
4. Credential rotation reminder (GitHub PAT, OpenRouter key, LangSmith key).

## Relevant files

**Phase 0 (Prerequisite code changes):**
- `cmu-capstone/agent/src/a11y_fixer/adapters/file_locator.py` — NEW, Phase 0.1 file-locator implementation (see `0-1-FILE-LOCATOR-IMPLEMENTATION.md` in this folder)
- `cmu-capstone/agent/src/a11y_fixer/agents/codebase_compiler.py` — integrate file_locator into SYSTEM_PROMPT (Phase 0.1)
- `cmu-capstone/agent/evaluation/run_eval.py` - `_run_one_case` (git-reset bug fix, Phase 0.2), `_arun_eval` (calibration floor threading, Phase 0.3)
- `cmu-capstone/agent/src/a11y_fixer/cli.py` - `deliver_violation`, `_cmd_run`, `_acmd_run` (floor threading, Phase 0.3)
- `cmu-capstone/agent/src/a11y_fixer/hitl/review_queue.py` - `calibrate_from_results` (wired into Phase 0.3)
- `cmu-capstone/agent/src/a11y_fixer/domain/hitl_policy.py` - `assess_risk` (no change needed, already accepts `p_ik_floor`)
- `tests/test_file_locator.py` — NEW unit tests for Phase 0.1

**Phase 6 & 7 (CI/docs):**
- `cmu-capstone/.github/workflows/a11y-fixer.yml` - NEW, copied from the reference (Phase 6)
- `Module-07-Capstone-Project/capstone-complete-compendium.md` - §7 (~line 1223) (Phase 7)
- `cmu-capstone/agent-plan.md` - changelog/status/stale-claim fixes (Phase 7)

**Context & Evidence:**
- `cmu-capstone/agent/PHASE_F_FINDINGS.md` - documents codebase_compiler file-discovery failures (case-06 atlas-dashboard.svg)
- `cmu-capstone/agent/src/a11y_fixer/adapters/mcp_clients.py` - MCP tool registry
- GitHub PRs #8, #9 on mdrmtz/Hallucinate.io - evidence of minimal placeholder edits from file-location failures

## Scope boundaries
- IN: Phases 0-8 above.
- OUT (explicit, per user decisions): Phase G Docker/git-worktree integration;
  backlog subagents (color_contrast_vision, alt_text_context); dashboard
  Approve/Reject backend wiring (stays localStorage-only for now).
