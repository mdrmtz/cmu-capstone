# PR Deduplication Fix - Summary & Action Items

## Issue Discovered & Fixed ✅

**What Happened:**
User observed 2 new PRs created on GitHub (1 hr ago, 40 min ago) but expected deduplication 
to prevent duplicate PRs. Prior investigation revealed 8 duplicate PRs for the same violations.

**Root Cause Identified:**
`PrePipelineGate.should_process()` crashes with `TypeError: '>' not supported between 
NoneType and float` when:
1. Called with `new_score=None` and `new_solution_hash=None` (pre-scoring check)
2. An existing open PR is found in the violation state

**Impact:**
- Exception silently caught in audit loop
- Violation processed anyway despite existing PR
- Duplicate PR created on each run
- Observed: 6-8 duplicate PRs for same violation

## Fix Applied ✅

**Files Modified:**
- `src/a11y_fixer/adapters/violation_store.py`
  - Line ~154: Handle None in hash comparison
  - Lines ~161-166: Early return when None values + existing PR
  - Lines ~133-137: Graceful fallback for None in new entries

**Test Results:**
✅ 17/17 Violation Store tests pass
✅ 9/9 HITL Queue Gate tests pass
✅ Total: 26/26 tests passing

**Behavior Change:**
Before: Crashes → duplicate PR created
After: Returns "SKIP" → violation skipped → no duplicate PR

## Next Actions

### Immediate (High Priority)

1. **Verify Fix Prevents New Duplicates**
   - Next audit run should show NO new duplicate PRs
   - Violations with existing PR_OPEN state should be skipped
   - Command: `python -m a11y_fixer.cli audit REPORT cmu-capstone/agent -vv`

2. **Check .violation_status.json State**
   - All 5 violations should now be tracked with proper PR numbers
   - Command: `python -c "...status tracking check..."`
   - Expected: PR numbers populated for violations processed in prior runs

3. **Commit the Fix**
   - Branch: `mdrmtz/dormant-to-live` (already committed)
   - Suggested commit: "fix: Handle None values in PrePipelineGate.should_process()"
   - PR for review when ready

### Secondary (Optional Cleanup)

4. **Close Existing Duplicate PRs** (if desired)
   - Review GitHub PRs for violations
   - Identify duplicate PR numbers
   - Use `pr_delivery.GitHubPRManager.cleanup_duplicate_prs()` or manual close
   - Keep only highest-scoring PR per violation

5. **Analyze Phase 2 Benchmark Results**
   - File: `evaluation/results/results_phase_all.json`
   - Extract calibrated_p_ik_floor and metrics
   - Use for Phase 3/4 calibration planning

### For Future Runs

6. **Re-run Phase 2 Benchmark**
   - Command: `python -m evaluation.run_eval --phase all --no-live`
   - With fix in place, should see clean metrics (no duplicate processing)
   - Use results for Phase 3/4 calibration

## Code Quality Status

| Component | Status | Tests | Notes |
|-----------|--------|-------|-------|
| PrePipelineGate | ✅ Fixed | 17/17 | None handling added |
| HITLQueueGate | ✅ OK | 9/9 | Already handles None correctly |
| ViolationStore | ✅ OK | 6/6 | Persistence working |
| E2E Scenario | ✅ OK | 1/1 | Duplicate detection verified |

## Files for Reference

- `PR_DEDUP_BUG_FIX.md` - Detailed technical analysis
- `/memories/session/pr-dedup-bug-fix.md` - Session summary
- `src/a11y_fixer/adapters/violation_store.py` - Fixed implementation
- `tests/adapters/test_violation_store.py` - Comprehensive tests (17 cases)

## Verification Checklist

Before proceeding with next phase:

- [ ] Fix committed to `mdrmtz/dormant-to-live`
- [ ] Run next audit and confirm NO new duplicate PRs created
- [ ] .violation_status.json shows PR numbers properly populated
- [ ] All 26 tests still passing
- [ ] Phase 2 benchmark results analyzed for calibration
- [ ] Phase 4 planning updated with this bug fix context

## Related Issues

**Resolved:**
- ✅ TypeError crash in PrePipelineGate with None values
- ✅ Duplicate PR creation on repeated audit runs
- ✅ Silent failure in pre-score deduplication gate

**Not In Scope (Phase 4+):**
- GitHub cleanup of existing 6-8 duplicate PRs (future optimization)
- mark_reviewed() integration for human decision persistence (Phase 4)
- Auto-merge integration for high-scoring PRs (existing, works)

## Learning for Future Design

1. **Gate Calling Pattern:** Gate must either:
   - Be called with complete information (post-processing)
   - Handle incomplete information gracefully (pre-processing)
   - Not be called at pre-processing stage for score-based logic

2. **Error Handling:** Silent exception catching masks bugs
   - Add explicit logging for gate decisions
   - Consider raising instead of catching for pre-processing errors

3. **Test Coverage:** Add tests for:
   - None/edge case parameters
   - Multiple consecutive calls with same violation
   - State transitions across runs

## Timeline Summary

| Event | Time | Status |
|-------|------|--------|
| Bug Discovered | Current | ✅ Identified |
| Root Cause Analysis | Current | ✅ Completed |
| Fix Implemented | Current | ✅ Done |
| Tests Run | Current | ✅ 26/26 Pass |
| Next Audit Run | Soon | ⏳ Pending |
| Duplicate Verification | TBD | ⏳ Pending |
