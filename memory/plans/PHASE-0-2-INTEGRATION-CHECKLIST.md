# Phase 0.2 Integration Checklist

**Goal:** Wire violation tracking, auto-merge, and dedup cleanup into the live pipeline
**Status:** Starting 2026-09-01
**Expected Duration:** 1-2 hours
**Success Criteria:** 3-case test passes with Phase 0.2 gate preventing duplicates

---

## Step 1: Integrate PrePipelineGate into cli.py

### Location: `src/a11y_fixer/cli.py::_acmd_run()`

**Task 1.1: Load violation store and gate at function start**

```python
# BEFORE: existing imports and function start
from a11y_fixer.adapters.violation_store import ViolationStore, PrePipelineGate
from a11y_fixer.domain.violations import compute_violation_id

async def _acmd_run(args, audit_result: dict):
    """Run the agent on violations from audit_result."""
    
    # NEW: Initialize violation tracking
    store = ViolationStore()
    gate = PrePipelineGate(store)
    
    # EXISTING: Load violations from audit_result
    violations = audit_result.get("violations", [])
    metrics = {
        "processed": 0,
        "skipped": 0,
        "created": 0,
        "replaced": 0,
        "auto_merged": 0,
        "duplicates_closed": 0,
    }
    
    # Loop through violations
    for violation in violations:
        try:
            # NEW: Check gate FIRST
            violation_id = compute_violation_id(violation["rule_id"], violation["selector"])
            action, reason, old_pr_number = gate.should_process(
                rule_id=violation["rule_id"],
                selector=violation["selector"],
                new_score=None,  # Will update after qa_critic
                new_solution_hash=None,  # Will update after codebase_compiler
            )
            
            if action == "SKIP":
                print(f"⏭️  Skipping {violation_id}: {reason}")
                metrics["skipped"] += 1
                continue
            
            # action == "CREATE" or "REPLACE" — proceed with full pipeline
            print(f"▶️  Processing {violation_id}: {action}")
            metrics["created"] += 1
            
            # EXISTING: Build and run agent
            graph = await abuild_agent(...)
            result = await graph.ainvoke(...)
            
            # Continue with existing delivery logic...
            
        except Exception as e:
            # Existing exception handling
            pass
    
    # NEW: Print metrics at end
    print(f"""
=== Phase 0.2 Metrics ===
Violations processed: {len(violations)}
Skipped (duplicates prevented): {metrics['skipped']}
Created: {metrics['created']}
Replaced (better solution): {metrics['replaced']}
Auto-merged: {metrics['auto_merged']}
Duplicates closed: {metrics['duplicates_closed']}
""")
```

**Task 1.2: Add violation tracking after graph.ainvoke()**

After the agent returns a result with computed score and solution, re-call the gate with actual values:

```python
# AFTER: graph.ainvoke() succeeds and result.structured_response exists
if result.get("structured_response"):
    response = result["structured_response"]
    solution_hash = hashlib.sha256(
        response.code.encode("utf-8")
    ).hexdigest()[:12]
    
    # Update gate decision with ACTUAL computed values
    action, reason, old_pr_number = gate.should_process(
        rule_id=violation["rule_id"],
        selector=violation["selector"],
        new_score=response.score,
        new_solution_hash=solution_hash,
    )
    
    # If gate says REPLACE, note it
    if action == "REPLACE":
        metrics["replaced"] += 1
        print(f"🔄 Replacing PR #{old_pr_number} with better solution (score: {response.score})")
```

---

## Step 2: Update PR Title & Body with Violation ID

### Location: `src/a11y_fixer/adapters/pr/delivery.py::create_pr_plan()`

**Task 2.1: Add violation_id to PR title**

```python
# BEFORE: existing title generation
from a11y_fixer.domain.violations import compute_violation_id

def create_pr_plan(violation: dict, response: ViolationResponse, ...) -> PullRequestPlan:
    """Create PR plan for a violation fix."""
    
    # NEW: Compute violation ID
    violation_id = compute_violation_id(
        rule_id=violation["rule_id"],
        selector=violation["selector"]
    )
    
    # EXISTING: Build title, NOW with violation ID
    title = (
        f"a11y-fixer: fix {violation['rule_id']} "
        f"({violation['selector']}) [violation-{violation_id}]"
    )
    
    # ... rest of function
```

**Task 2.2: Add solution_hash to PR body**

```python
# AFTER: existing body construction
import hashlib

solution_hash = hashlib.sha256(response.code.encode("utf-8")).hexdigest()[:12]

body = f"""
## Accessibility Fix

**Violation ID:** `{violation_id}`
**Solution Hash:** `{solution_hash}`
**Quality Score:** {response.score}/20
**WCAG Criterion:** {violation['wcag']}

### Violation Details
- **Rule:** {violation['rule_id']}
- **Selector:** {violation['selector']}
- **Page:** {violation['page']}

### Fix Applied
```
{response.code}
```

### Why This Fix
{response.reasoning}

---
*Generated by A11y Fixer on {datetime.now().isoformat()}*
"""

pr_plan = PullRequestPlan(
    title=title,
    body=body,
    branch_name=f"a11y-fixer/{violation_id}",
    # ... rest of existing fields
)
```

---

## Step 3: Wire Auto-Merge + Dedup Cleanup After Delivery

### Location: `src/a11y_fixer/cli.py::deliver_violation()`

**Task 3.1: Call auto_merge_pr after successful delivery**

```python
# AFTER: pr_delivery succeeds and delivery_result.pr_number is known
from a11y_fixer.adapters.pr.github_pr_manager import GitHubPRManager
from a11y_fixer.config import resolve_pr_delivery

if delivery_result.success and delivery_result.pr_number:
    pr_number = delivery_result.pr_number
    violation_id = compute_violation_id(violation["rule_id"], violation["selector"])
    
    # Only attempt auto-merge if we have GitHub credentials
    try:
        pr_config = resolve_pr_delivery(live=True)
        if pr_config.github_token:
            mgr = GitHubPRManager(
                github_token=pr_config.github_token,
                github_repo=pr_config.github_repo,
            )
            
            # Auto-merge if quality is high enough
            if response.score >= 18.0:
                merge_result = mgr.auto_merge_pr(pr_number, response.score)
                if merge_result.success:
                    print(f"✅ Auto-merged PR #{pr_number} (score: {response.score:.1f})")
                    metrics["auto_merged"] += 1
                    
                    # Clean up ALL duplicate PRs
                    cleanup_results = mgr.cleanup_duplicate_prs(violation_id, pr_number)
                    for result in cleanup_results:
                        print(f"🔗 Closed PR #{result.pr_number} as duplicate")
                        metrics["duplicates_closed"] += 1
            else:
                print(f"⏱️  PR #{pr_number} awaiting review (score: {response.score:.1f} < 18.0)")
    except Exception as e:
        print(f"⚠️  Failed to auto-merge: {e}")
        # Continue without auto-merge, PR awaits human review
```

**Task 3.2: Persist violation status after delivery**

```python
# AFTER: all delivery steps complete
status = store.get(violation_id) or ViolationStatus(
    violation_id=violation_id,
    rule_id=violation["rule_id"],
    selector=violation["selector"],
    state=ViolationState.NEW,
)

if delivery_result.success:
    status.state = ViolationState.PR_OPEN
    status.current_pr_number = pr_number
    status.current_score = response.score
    status.current_solution_hash = solution_hash
    status.updated_at = datetime.now(UTC)
    
    # If auto-merged, update state
    if merge_result.success:
        status.state = ViolationState.MERGED
    
    store.upsert(status)
    store.save()
```

---

## Step 4: Test Pre-Pipeline Gate Dry-Run

**Task 4.1: Run against case-01, case-03, case-13 (dry-run, no live)**

```bash
cd cmu-capstone/agent

# First run - creates violations in store
python -m a11y_fixer.cli run --no-live --case-ids case-01,case-03,case-13

# Check: .violation_status.json should be created with 3 violations
cat .violation_status.json | python -m json.tool

# Expected output:
# {
#   "violation_1a2b3c": { "rule_id": "html-has-lang", "state": "PR_OPEN", ... },
#   "violation_2d3e4f": { "rule_id": "color-contrast", "state": "PR_OPEN", ... },
#   "violation_3g4h5i": { "rule_id": "link-name", "state": "PR_OPEN", ... }
# }
```

**Task 4.2: Run again - should see SKIP messages**

```bash
# Second run - should skip same violations
python -m a11y_fixer.cli run --no-live --case-ids case-01,case-03,case-13

# Expected output:
# ⏭️  Skipping violation_1a2b3c: identical_solution
# ⏭️  Skipping violation_2d3e4f: identical_solution
# ⏭️  Skipping violation_3g4h5i: identical_solution
#
# === Phase 0.2 Metrics ===
# Violations processed: 3
# Skipped (duplicates prevented): 3
# Created: 0
# Replaced: 0
# Auto-merged: 0
# Duplicates closed: 0
```

---

## Step 5: Verify Against Real PRs (Hallucinate.io)

**Task 5.1: Identify existing image-alt PRs**

```bash
# Check GitHub for existing PRs on Hallucinate.io
# Expected: PRs #2-9 all fixing image-alt (identical violation)
# Verify they all have the same selector or similar solutions
```

**Task 5.2: Dry-run against Hallucinate.io**

```bash
# Run against image-alt violation
python -m a11y_fixer.cli run --no-live --case-ids case-06,case-07,case-08

# Check: Should see all 3 SKIPPED if identical solutions
# Expected:
# ⏭️  Skipping violation_image_alt_1: identical_solution
# ⏭️  Skipping violation_image_alt_2: identical_solution
# ⏭️  Skipping violation_image_alt_3: identical_solution
```

---

## Checklist

### Phase 0.2 Integration Tasks

- [ ] **1.1** Add imports to cli.py (ViolationStore, PrePipelineGate, compute_violation_id)
- [ ] **1.2** Load gate in _acmd_run() function start
- [ ] **1.3** Call gate.should_process() before graph.ainvoke()
- [ ] **1.4** Update gate with actual score/solution_hash after graph.ainvoke()
- [ ] **1.5** Add metrics dict and tracking

- [ ] **2.1** Add compute_violation_id to delivery.py
- [ ] **2.2** Update PR title with [violation-{id}]
- [ ] **2.3** Add solution_hash to PR body

- [ ] **3.1** Add GitHubPRManager import
- [ ] **3.2** Wire auto_merge_pr() call after successful delivery
- [ ] **3.3** Wire cleanup_duplicate_prs() call after auto-merge
- [ ] **3.4** Add violation status persistence

- [ ] **4.1** Run 3-case dry-run, verify .violation_status.json created
- [ ] **4.2** Run again, verify SKIP messages appear
- [ ] **4.3** Verify metrics output shows correct counts

- [ ] **5.1** Identify existing image-alt PRs on Hallucinate.io
- [ ] **5.2** Dry-run against image-alt cases, verify duplicates detected

---

## Success Criteria

✅ `.violation_status.json` persists between runs
✅ PrePipelineGate correctly identifies identical violations and returns SKIP
✅ Metrics printed at end of run show correct counts
✅ No errors or exceptions during dry-run
✅ All 3-case test violations appear in store

---

## Rollback Instructions

If integration causes issues:

```bash
# Revert Phase 0.2 changes
git checkout cmu-capstone/agent/src/a11y_fixer/cli.py
git checkout cmu-capstone/agent/src/a11y_fixer/adapters/pr/delivery.py

# Delete violation store
rm cmu-capstone/agent/.violation_status.json

# Tests still pass (Phase 0.2 modules are independent)
pytest tests/adapters/test_violation_store.py -v
```

---

## Next: Move to Step 2?

Once checklist above is complete, confirm:
```
✅ All tasks done
✅ 3-case dry-run passes
✅ Metrics show expected counts
✅ No errors or regressions

→ Ready to move to Step 2 (3-case live test with auto-merge)?
```
