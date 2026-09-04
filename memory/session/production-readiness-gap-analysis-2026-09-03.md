# Production Readiness Gap Analysis — 2026-09-03

**Scope:** Independent verification of `memory/plans/agent-plan.md` and
`memory/plans/PHASE-4.3-COMPLETE.md`'s "production ready" claims against the
actual codebase, config files, and result artifacts. Findings below are
evidence-backed (file paths / line numbers / grep output cited), not a
re-summary of the plan's own self-assessment.

**Bottom line:** the *agent pipeline* (audit → fix → score → route →
dry-run PR / lesson) is real and working. What's missing is entirely on the
**delivery and deployment side** — the parts that turn a scored fix into a
merged change in a real repo, and turn a merge into a live deployment.
Four concrete blockers, in priority order:

---

## 1. GITHUB_TOKEN is empty in the `.env` file that actually gets loaded

`agent/src/a11y_fixer/config.py` calls `load_dotenv(find_dotenv(usecwd=True))`,
which searches **upward from the current working directory**. Every real
entry point (`hitl_server.py`'s review subprocess, `python -m a11y_fixer.cli`,
`python -m evaluation.run_eval`) runs with cwd = `agent/`, so it finds
`agent/.env` first and stops there — it never reaches `cmu-capstone/.env`.

- `agent/.env` → `GITHUB_TOKEN=` — **empty** (verified: 0 chars).
- `cmu-capstone/.env` (repo root, one level up) → has a real-looking token
  (93 chars) and `GITHUB_REPO=mdrmtz/Hallucinate.io` — but this file is
  **never loaded** by any of the normal entry points.

Effect: clicking "Approve" → "live" in the HITL dashboard today hits
`config.resolve_pr_delivery(cli_live=True)`, which raises
`RuntimeError("--live requires GITHUB_TOKEN to be set")` before anything
happens. Same for `run_eval.py --live`. This is why the auto-merge feature
just wired into `review_queue.py`'s approve branch can't be exercised yet —
not a bug in the new code, but this pre-existing env misconfiguration.

**Fix:** move (not copy) the real token into `agent/.env`, since that's the
file `find_dotenv` actually resolves to. Also worth hardening
`config.resolve_pr_delivery` / the two `.env.example` files so this
mismatch is caught earlier next time (e.g. a note in `agent/.env.example`
warning that root-level `.env` is not read).

## 2. No live PR has ever actually been created — despite "Phase 4.3: COMPLETE ✅"

`memory/plans/PHASE-4.3-COMPLETE.md` claims *"Live PR Delivery Test —
COMPLETE"*, *"PRODUCTION READY"*, and that case-21 was *"AUTO-APPROVED"*
with *"PR Metadata: Ready for auto-approval case delivery"*.

Verified against the actual artifacts:
- `agent/evaluation/results/prs/` contains exactly **one** file pair — a
  dry-run `.diff` + `.md` (the format `deliver_dry_run()` writes, not
  `deliver_live()`) — from a different, unrelated html-has-lang case, dated
  Sep 2, hours before the Phase 4.3 test even ran.
- `grep -rn "pull_request_url\|pull_request_number\|github.com/mdrmtz" agent/evaluation/results/` 
  returns **zero matches** anywhere in the results tree.
- This is consistent with finding #1: if `agent/.env`'s token was already
  empty when this test ran, `--live` would have raised immediately rather
  than silently falling back to dry-run — so either the test's `--live`
  flag never actually reached a real GitHub call, or it was run before the
  token was cleared and nobody re-validated after. Either way, **there is
  no evidence anywhere in the repo of a real GitHub PR ever being opened**
  by this system.

**Fix:** once #1 is corrected, re-run the Phase 4.3 live test for real and
confirm a `pull_request_url` shows up in the output — that's the actual bar
for "live PR delivery verified," not a dry-run diff file.

## 3. No CI/CD exists — Phase 5 as described is not wireable yet

The plan's Phase 5 says: *"Merge to main branch → GitHub Actions triggers
CI/CD → deploy to Netlify"*. There is **no `.github/workflows/` directory
anywhere in this repo** (checked recursively, excluding `node_modules` /
`.repo-cache`). `Hallucinate.io/netlify.toml` exists (config for the fixture
app itself), but nothing connects "merge to main" to a build or a deploy.

**Fix:** either write the actual GitHub Actions workflow (test → build →
deploy) before calling Phase 5 "ready," or update the plan to describe
deployment as a manual step for now.

## 4. `auto_merge_pr()` had a real, silently-swallowed bug (now fixed)

`agent/src/a11y_fixer/cli.py`'s automated pipeline (`deliver_violation()`,
the *only* other place in the codebase that calls `GitHubPRManager`) called:

```python
merge_result = pr_mgr.auto_merge_pr(pr_number, response.score, threshold=auto_merge_threshold)
```

but `GitHubPRManager.auto_merge_pr()`'s real signature takes
`merge_threshold`, not `threshold`. Every attempted auto-merge (score ≥ 18,
live mode) would have raised `TypeError: auto_merge_pr() got an unexpected
keyword argument 'threshold'` — caught by a broad `except Exception`, logged
as `"⚠️ Auto-merge/cleanup failed: ..."`, and silently ignored. Combined
with #1/#2, auto-merge has most likely **never actually executed
successfully** in this codebase, in either the automated pipeline or (until
today) the HITL dashboard path.

**Status:** fixed this session in both call sites —
`cli.py::deliver_violation()` (the pre-existing bug) and the new
`ReviewQueue.review()` approve-branch wiring (`agent/src/a11y_fixer/hitl/review_queue.py`),
which now calls `GitHubPRManager.auto_merge_pr(pr_number, score, merge_threshold=AUTO_MERGE_THRESHOLD)`
correctly. Not yet *exercised* end-to-end because of #1.

---

## Secondary findings (lower severity / doc hygiene)

- **Plan's own go/no-go checklist is unchecked.** `agent-plan.md`'s "4.4:
  Readiness Check for Phase 5" section has every item as `- [ ]`, including
  "Branch pushed to GitHub" — the surrounding prose calling the project
  "PRODUCTION READY" contradicts the plan's own stated gate.
- **"Auto-approve rate ≥ 80%" claim vs. actual routing.** Phase 4.3's own
  data (`phase_4_3_live_test.json`): 5 cases, `route == "auto"` for 2 of
  them (case-02, case-21) = 40% auto-approve rate, not the ≥80% the success
  criteria in `agent-plan.md` claims was hit. The 80% figure that *is*
  accurate is *violation_clearance_rate* (4/5 cases cleared on re-audit) —
  a different metric than "auto-approve rate." Worth correcting the
  terminology so the two numbers aren't conflated.
- **A real GitHub PAT sits in plaintext at `cmu-capstone/.env`.** Verified
  it is `.gitignore`'d (`git check-ignore -v .env` confirms) and has never
  been committed (`git log --all -- .env` is empty) — so it's not publicly
  exposed. Still worth treating with normal credential hygiene (don't leave
  it lying around longer than needed, rotate if this machine/session
  context is ever untrusted).
- **`agent-plan.md`'s "Next Steps (What Remains)" section (dated
  2026-08-31)** describes an Orchestrator → `deepagents` migration as
  not-yet-done. Verified this is actually **complete**:
  `agent/src/a11y_fixer/deep_agent.py` exists and calls
  `deepagents.create_deep_agent()` with `interrupt_on`, `memory=[...]`
  (wiki), `permissions`, and `subagents` all wired; `orchestrator.py` no
  longer exists. This section is just stale — worth archiving/removing so
  it doesn't read as an open TODO to a future reader.
- **Test suite:** could not execute pytest in this device_bash sandbox —
  the package requires Python ≥3.11 (`datetime.UTC`, used in
  `adapters/pr/delivery.py`, doesn't exist before 3.11) and this sandbox
  only has Python 3.10 with no sudo to install a newer interpreter. Static
  check: of the 3 tests the Sep 3 verification report flagged as failing,
  `test_html_lang_applier.py` and `test_run_eval.py` were both edited today
  (Sep 3, later than the verification report) in ways that match the exact
  fixes needed (baseline-build sequencing comment; `use_worktree` added to
  the mock signature) — plausibly resolved, but not independently re-run.
  `test_coverage_100_percent.py` hasn't been touched since Sep 2 — its
  collection error is likely still unresolved.

---

## What's actually solid (verified, not just claimed)

- Phase 2's 22-case benchmark numbers check out exactly against the real
  `results_summary.json` (22 cases, 63.6% clearance, 100% html-lang,
  121.2s mean latency, per-rule breakdown all match).
- The calibrated P(IK) floor (0.75) is consistently wired: matches
  `hitl_policy.py`'s `DEFAULT_P_IK_FLOOR` and `results_summary.json`'s
  `calibrated_p_ik_floor` / `calibration_metadata`.
- The deepagents migration (Orchestrator → `create_deep_agent`) is
  genuinely complete, not just claimed.
- The HITL review flow (dashboard → `/api/review` → `ReviewQueue.review()`)
  works end-to-end for both decisions: reject correctly files a lesson via
  `wiki_pipeline.ingest_lesson()`; approve correctly builds and delivers a
  `PullRequestPlan` (dry-run today, live once #1 is fixed).

---

## Recommended order of operations to actually reach production

1. Fix the `.env` token location (#1) — 5 minutes.
2. Re-run Phase 4.3's live test for real; confirm an actual PR URL appears
   in the output — proves #2 is closed.
3. Confirm the auto-merge fix (#4) fires correctly on that real PR if its
   score ≥ 18.
4. Write the actual GitHub Actions workflow (#3), or explicitly scope
   Phase 5 down to "manual merge + manual deploy" until it exists.
5. Get pytest running somewhere with Python ≥3.11 and confirm the real
   current pass/fail count (this sandbox can't do it).
6. Correct the "80% auto-approve rate" wording and archive the stale
   "Next Steps (What Remains)" section in `agent-plan.md`.

---

## FOLLOW-UP PASS (same day, later session) — additional findings + fixes applied

**pytest now runnable** (this environment has Python 3.14.7, not 3.10) —
ran the real full suite. Found and fixed a **second, more severe** bug on
the way: `tests/evaluation/__init__.py` was an orphaned empty package
(zero real test content, confirmed via `grep -rn "tests.evaluation"` =
no references anywhere) that shadowed the real `evaluation` package once
pytest's rootdir-insertion put `tests/` ahead of `.` in `sys.path` for any
test needing `evaluation.run_eval` — this made pytest **abort collection
of the ENTIRE suite**, not just fail one file. Deleted it.
**Real result: 371 passed, 4 deselected (e2e), 0 failed.** The 335/336
and 319/323 figures cited elsewhere in `agent-plan.md` never reflected a
completed full-suite run either (collection always aborted before them).

**GITHUB_TOKEN confirmed real** by user (40-char token, active in the
current shell session) — live PR delivery is credential-ready *for this
session*, but finding #1 (empty `agent/.env`) is still open for any fresh
session/terminal.

**Re-tested finding #2 again** (case-09 + case-10, `--live`, both env vars
set): both routed to `"human"` → neither ever reached the GitHub API at
all (`deliver_violation()` only calls PR delivery on `route == "auto"`).
Still zero evidence of a real PR ever being created.

**NEW finding (#5): case-10's HITL queue write silently did not persist.**
- `case-09` (html-has-lang, `.element-7224`) correctly hit `HITLQueueGate`'s
  identical-score SKIP path (score 20.0 == already-queued 20.0 from an
  earlier run) — dedup working exactly as designed here.
- `case-10` (link-name, `.element-5333`, page `/features`) scored 15.0,
  cleared on re-audit, and `deliver_violation()` returned `route: "human"`
  — but **no entry for this violation exists anywhere**: not in
  `hitl_queue/` (checked by filename pattern and by every file's mtime —
  nothing from today), not in `.violation_status.json` (checked all 15
  entries individually, none match `rule="link-name"` +
  `selector=".element-5333"`).
- Per `HITLQueueGate.should_queue()`'s own logic, a never-before-seen
  violation ID hits "Case 1" and **unconditionally** calls
  `store.upsert()` + `store.save()` before any other branch runs — so
  reaching `route == "human"` should make this impossible to skip.
  Root cause NOT yet identified (ruled out: wrong selector lookup, wrong
  rule_id, `no_changes` early-return doesn't apply to the human route,
  CaseResult.route is read directly from `deliver_violation()`'s return
  dict with no other fallback path that could fabricate `"human"` for a
  non-timeout, non-error case). Needs a targeted repro with tracing/
  breakpoints inside `deliver_violation()`'s `route == "human"` branch.

**Applied directly to `agent-plan.md`** (not just this file) this pass:
- New "🔴 PRODUCTION READINESS GAP ANALYSIS" section at the very top,
  consolidating both sessions' findings, replacing the false "PRODUCTION
  READY ✅" banner.
- Phase 4.3 section corrected: 80%→40% auto-approve rate distinction,
  "COMPLETE"→"PARTIAL", PR-creation status re-verified as still open,
  test count corrected to 371/371.
- Phase 4.4 checklist changed from 100% unchecked to reflecting real
  state (4/7 pass, 3 fail with evidence cited inline).
- "CRITICAL PATH TO PRODUCTION" status summary corrected end-to-end.

**Still NOT done** (deliberately out of scope for a plan-verification
pass): actually moving the token into `agent/.env`, root-causing finding
#5, writing the CI workflow, committing/pushing the branch. All are now
explicit, ordered next steps in `agent-plan.md`'s gap-analysis section.
