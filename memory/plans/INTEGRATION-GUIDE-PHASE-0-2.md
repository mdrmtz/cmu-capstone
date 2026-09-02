# Phase 0.2 Integration Guide

## How to Wire Violation Tracking into the Existing Pipeline

This guide shows the exact integration points for PrePipelineGate, auto-merge, and deduplication cleanup.

### Entry Point: `cli.py::_acmd_run()`

The violation tracking gate should be invoked **BEFORE** the full pipeline runs on each violation.

```python
# In cli.py::_acmd_run() function, AFTER loading violations but BEFORE graph.ainvoke():

from a11y_fixer.adapters.violation_store import ViolationStore, PrePipelineGate
from a11y_fixer.domain.violations import compute_violation_id
from a11y_fixer.adapters.pr.github_pr_manager import GitHubPRManager

# Load violation tracking store
store = ViolationStore()
gate = PrePipelineGate(store)

# ... existing violation loop ...
for violation in violations:
    try:
        # ** NEW: Check gate FIRST **
        action, reason, old_pr_number = gate.should_process(
            rule_id=violation["rule_id"],
            selector=violation["selector"],
            new_score=None,  # Not yet computed; set after qa_critic
            new_solution_hash=None,  # Computed after codebase_compiler
        )
        
        if action == "SKIP":
            print(f"⏭️  Skipping {violation['id']}: {reason}")
            continue
        
        # action == "CREATE" or action == "REPLACE" - proceed with full pipeline
        graph = await abuild_agent(...)
        result = await graph.ainvoke(...)
        
        # ** After graph.ainvoke(), re-call gate with ACTUAL computed values **
        if result["structured_response"]:
            response = result["structured_response"]
            solution_hash = hashlib.sha256(
                response.code.encode("utf-8")
            ).hexdigest()[:12]
            
            # Update gate decision with real score/solution
            action, reason, old_pr_number = gate.should_process(
                rule_id=violation["rule_id"],
                selector=violation["selector"],
                new_score=response.score,
                new_solution_hash=solution_hash,
            )
        
        # ... rest of existing deliver_violation + interrupt handling ...
        
    except Exception as e:
        # Existing exception handling
        pass
```

### Integration Point 2: PR Delivery (delivery.py)

Update the `PullRequestPlan.title` to include violation_id for GitHub search:

```python
# In delivery.py, wherever PullRequestPlan is created:

from a11y_fixer.domain.violations import compute_violation_id

# When building title:
violation_id = compute_violation_id(rule_id, selector)
title = f"a11y-fixer: fix {rule_id} ({selector}) [violation-{violation_id}]"

# When building body, add solution_hash:
body = f"""
## Accessibility Fix

**Violation ID:** `{violation_id}`
**Solution Hash:** `{solution_hash}`
**Quality Score:** {score}/20

...rest of existing body...
"""

pr_plan = PullRequestPlan(
    title=title,
    body=body,
    branch_name=f"a11y-fixer/{violation_id}",
    changes=changes,
)
```

### Integration Point 3: After PR Delivery, Auto-Merge + Dedup Cleanup

If PR was created successfully, auto-merge and close duplicates:

```python
# In cli.py::deliver_violation() or nearby delivery orchestration:

from a11y_fixer.adapters.pr.github_pr_manager import GitHubPRManager
from a11y_fixer.config import resolve_pr_delivery

# After delivery succeeds and PR number is known:
if delivery_result.success and delivery_result.pr_number:
    pr_number = delivery_result.pr_number
    
    # Initialize GitHub PR manager
    pr_config = resolve_pr_delivery(live=True)  # Only if live mode
    mgr = GitHubPRManager(
        github_token=pr_config.github_token,
        github_repo=pr_config.github_repo,
    )
    
    # Auto-merge if quality is high
    if response.score >= 18.0:
        merge_result = mgr.auto_merge_pr(pr_number, response.score)
        if merge_result.success:
            print(f"✅ Auto-merged PR #{pr_number} (score: {response.score:.1f})")
        
        # Clean up ALL duplicate PRs
        cleanup_results = mgr.cleanup_duplicate_prs(violation_id, pr_number)
        for result in cleanup_results:
            print(f"🔗 Closed PR #{result.pr_number} as duplicate")
```

### Integration Point 4: State Persistence

Update ViolationStatus in store after each phase:

```python
# After gate.should_process():
if action in ("CREATE", "REPLACE"):
    status = store.get(violation_id) or ViolationStatus(
        violation_id=violation_id,
        rule_id=violation["rule_id"],
        selector=violation["selector"],
        state=ViolationState.NEW,
    )
    status.state = ViolationState.PR_OPEN
    status.current_pr_number = pr_number
    status.current_score = response.score
    status.current_solution_hash = solution_hash
    status.updated_at = datetime.now(UTC)
    store.upsert(status)
    store.save()

# After auto-merge:
if merge_result.success:
    status.state = ViolationState.MERGED
    status.updated_at = datetime.now(UTC)
    store.upsert(status)
    store.save()
```

---

## Migration Checklist

### Phase 1: Persistence Infrastructure
- [ ] Add `compute_violation_id()` helper to all violation references
- [ ] Create `.violation_status.json` at repo root on first run
- [ ] Verify persistence: run twice, check store carries over

### Phase 2: Pre-Pipeline Gate
- [ ] Call `PrePipelineGate.should_process()` before graph.ainvoke()
- [ ] Skip violations that gate says "SKIP"
- [ ] Track which violations were skipped in output
- [ ] Log reason for each skip

### Phase 3: PR Title & Body Tagging
- [ ] Update PR titles to include `[violation-{id}]`
- [ ] Update PR bodies to include Solution Hash
- [ ] Verify GitHub search finds PRs by violation ID

### Phase 4: Auto-Merge & Dedup
- [ ] After successful delivery, call `auto_merge_pr(pr_number, score)`
- [ ] If auto-merge succeeds, call `cleanup_duplicate_prs(violation_id, pr_number)`
- [ ] Log each closed duplicate with reason
- [ ] Verify PRs are visible on GitHub as closed with comments

### Phase 5: Testing Against Real Fixture
- [ ] Dry-run on current Hallucinate.io state (PRs #2-9)
- [ ] Verify PrePipelineGate correctly identifies duplicates
- [ ] Verify action=SKIP for identical solution
- [ ] Verify action=REPLACE if new score > old + 1.5
- [ ] Verify auto-merge succeeds if score >= 18.0
- [ ] Verify cleanup_duplicate_prs closes all old PRs

---

## Key Configuration Constants

In your code, reference these from the modules:

```python
# From PrePipelineGate:
BETTER_SOLUTION_MARGIN = 1.5  # New score must exceed current by this
AUTO_MERGE_THRESHOLD = 18.0   # Score threshold for auto-merge

# From ViolationState enum:
NEW, PR_OPEN, MERGED
WONT_FIX
CLOSED_DUMMY, CLOSED_CONFLICT, CLOSED_SUPERSEDED, BETTER_SOLUTION_READY

# From ViolationStatus:
violation_id: str            # Deterministic 12-char hash
current_pr_number: int | None
current_score: float
best_score: float
best_solution_hash: str
solution_hash: str
state: ViolationState
```

---

## Error Handling

### GitHub API Failures

```python
try:
    result = mgr.auto_merge_pr(pr_number, score)
except GitHubPRManagerError as e:
    print(f"⚠️  Failed to auto-merge PR #{pr_number}: {e}")
    # Continue without auto-merge, PR awaits human review
    return
```

### Missing Credentials (Dry-Run Mode)

```python
pr_config = resolve_pr_delivery(live=False)  # Dry-run
if not pr_config.github_token:
    print("ℹ️  Dry-run mode: skipping auto-merge and dedup cleanup")
    return
```

### Stale Violation Store

```python
# If .violation_status.json becomes corrupted:
try:
    store = ViolationStore()
except Exception as e:
    print(f"⚠️  Violation store corrupted: {e}")
    store = ViolationStore()  # Creates fresh empty store
    store.save()
```

---

## Expected Output on First Run After Integration

```
[html-has-lang] Scanning...
⏭️  Skipping html-has-lang: marked_wont_fix (reason: previous run decided not to attempt fix)

[image-alt] Scanning...
🔍 Running full pipeline (first violation)
✅ PR #10 created successfully
⏱️  Running qa_critic...
✅ Quality score: 19.0/20

🚀 Auto-merging PR #10 (score: 19.0 >= 18.0)
✅ Auto-merged PR #10

🔗 Closing duplicate PRs:
🔗 Closed PR #2 as duplicate of PR #10
🔗 Closed PR #3 as duplicate of PR #10
🔗 Closed PR #4 as duplicate of PR #10
🔗 Closed PR #5 as duplicate of PR #10
🔗 Closed PR #6 as duplicate of PR #10
🔗 Closed PR #7 as duplicate of PR #10
🔗 Closed PR #8 as duplicate of PR #10
🔗 Closed PR #9 as duplicate of PR #10

✅ All duplicates cleaned up. Main branch now has best solution.
```

---

## Testing the Integration (Before Live)

Run a **dry-run** first:

```bash
# Dry-run (no real PRs created)
python -m a11y_fixer.cli run --no-live --case-from 0 --case-to 5

# Verify .violation_status.json was created
cat cmu-capstone/agent/.violation_status.json

# Run again - should see SKIP messages for same violations
python -m a11y_fixer.cli run --no-live --case-from 0 --case-to 5

# Verify state machine transitions were logged
```

Once dry-run looks good, enable live mode with a single high-confidence violation:

```bash
# Live: single violation, auto-merge enabled
python -m a11y_fixer.cli run --live --case-ids image-alt

# Check GitHub for the new PR, auto-merge, and closed duplicates
```

---

## Rollback Plan

If Phase 0.2 causes issues in production:

1. **Disable PrePipelineGate:** Comment out gate call in `_acmd_run()`, always use action=CREATE
2. **Disable Auto-Merge:** Comment out auto-merge call, default to awaiting human review
3. **Keep Dedup Cleanup:** Leave cleanup_duplicate_prs() active (it only helps, doesn't hurt)
4. **Revert `.violation_status.json`:** Delete the file to start fresh next run

```bash
# Quick rollback
rm cmu-capstone/agent/.violation_status.json
git checkout cmu-capstone/agent/src/a11y_fixer/cli.py  # Revert gate integration
```

---

## Monitoring Metrics

After Phase 0.2 is live, track these to confirm it's working:

- **Duplicate PRs prevented per run:** Count `SKIP` messages in logs
- **Auto-merges per run:** Count successful `auto_merge_pr` calls
- **Dedup cleanup success rate:** Verify cleanup_duplicate_prs closes all duplicates
- **False positive rate:** Manual review of SKIP decisions (should be < 5%)

Add a simple metrics counter:

```python
metrics = {
    "skipped": 0,
    "created": 0,
    "replaced": 0,
    "auto_merged": 0,
    "duplicates_closed": 0,
}

# At end of run:
print(f"""
=== Phase 0.2 Metrics ===
Violations processed: {len(violations)}
Skipped (duplicates prevented): {metrics['skipped']}
Created: {metrics['created']}
Replaced (better solution): {metrics['replaced']}
Auto-merged: {metrics['auto_merged']}
Duplicates closed: {metrics['duplicates_closed']}
Compute time saved: {metrics['skipped'] * 3} min
""")
```
