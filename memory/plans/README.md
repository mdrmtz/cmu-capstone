# E2E Validation Plans for The A11y Fixer

This folder contains the comprehensive plan for validating The A11y Fixer against all deliverables in `agent-plan.md`. Plans are tracked here for version control and future reference.

## Files

### 0-MAIN-PLAN.md
The 8-phase validation plan (Phases 0-8):
- **Phase 0:** Prerequisite code fixes (file locator tool, git-reset bug, calibration wiring)
- **Phase 1:** Smoke test (1 case, dry-run)
- **Phase 2:** Full 22-case dry-run benchmark
- **Phase 3:** Human review loop
- **Phase 4:** Calibration proof
- **Phase 5:** Live PR delivery (1-2 cases)
- **Phase 6:** GitHub Actions CI trigger
- **Phase 7:** Documentation reconciliation
- **Phase 8:** Wrap-up

See `0-MAIN-PLAN.md` for full scope, dependencies, and file references.

### 0-1-FILE-LOCATOR-IMPLEMENTATION.md
Detailed implementation spec for Phase 0.1 (File Locator Tool):
- **Problem:** codebase_compiler fails to locate Angular component template files matching CSS selectors (40-66% failure rate in prior runs)
- **Solution:** New `locate_selector_in_component()` function using deterministic file discovery (grep + HTML regex heuristics) instead of pure LLM reasoning
- **Code:** Full implementation of `file_locator.py`, integration into codebase_compiler, and unit tests
- **Success criteria:** ≥90% file discovery accuracy; ≥70% success rate improvement in Phase 1 smoke test

**Evidence of need:**
- PHASE_F_FINDINGS.md documents case-06 (atlas-dashboard.svg) failure
- GitHub PRs #8, #9 on mdrmtz/Hallucinate.io show placeholder edits instead of real component fixes

## How to use

1. **Before implementation:** Review `0-MAIN-PLAN.md` to understand full scope and Phase 0 blockers
2. **Phase 0.1 implementation:** Follow code snippets and success criteria in `0-1-FILE-LOCATOR-IMPLEMENTATION.md`
3. **During execution:** Cross-reference file paths and phase dependencies in `0-MAIN-PLAN.md`
4. **After completion:** Update with real numbers and outcomes (defer to Phase 8 wrap-up)

## Dependencies

- Phase 0 **blocks** Phase 2 (full benchmark can't run until Phase 0 fixes are in place)
- Phase 2 **produces** `results_summary.json` needed by Phase 3 and Phase 4
- Phases 5 and 6 can run any time after Phase 0 (independent)
- Phases 7-8 depend on data from Phases 2-4

## Scope (In vs. Out)

**Included (Phases 0-8):**
- File locator tool implementation and integration
- Git-reset bug fix and calibration wiring
- Full 22-case dry-run benchmark
- Human review, calibration proof, live PR smoke test
- CI trigger deployment
- Documentation reconciliation

**Excluded (Out of scope, per user decision):**
- Phase G (Docker/git-worktree integration)
- Backlog subagents (color_contrast_vision, alt_text_context)
- Dashboard Approve/Reject backend wiring (stays localStorage-only)

---

Generated: 2026-09-01
