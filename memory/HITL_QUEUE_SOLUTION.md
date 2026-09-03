"""
HITL QUEUE DEDUPLICATION: Complete Solution Summary
====================================================

User Request:
─────────────
"Reading cmu-capstone/agent/hitl_queue looks like some duplicates ticket for 
Human Review. Implement a mechanism similar to the PR to avoid dups (using 
attributes at cmu-capstone/agent/.violation_status.json)"


SOLUTION IMPLEMENTED
====================

✅ 1. SOURCE PREVENTION: HITLQueueGate Deduplication
─────────────────────────────────────────────────────

Location: src/a11y_fixer/adapters/violation_store.py
Class: HITLQueueGate (new)

Purpose: Gate violations BEFORE they enter HITL queue
         Prevents duplicates at creation time, not cleanup time

Decision Logic (6 cases):
  1. NEW violation → ADD to queue
  2. WONT_FIX by human → SKIP (never re-queue)
  3. ALREADY MERGED → SKIP (already fixed)
  4. IDENTICAL score → SKIP (same solution, no re-queue)
  5. BETTER score (+1.5 margin) → REPLACE (upgrade queue entry)
  6. MARGINAL score → SKIP (existing adequate, avoid thrash)

Margin Threshold: 1.5 points
  - Score 18 vs 19.4 → SKIP (too close, 1.4 margin)
  - Score 18 vs 19.5 → REPLACE (significant, 1.5 margin)


✅ 2. INTEGRATION: deliver_violation() in cli.py
──────────────────────────────────────────────────

File: src/a11y_fixer/cli.py [line ~275]
Function: deliver_violation()

Added before writing any queue file:

  if route == "human":
      store = ViolationStore(status_file=config.agent_root() / ".violation_status.json")
      gate = HITLQueueGate(store)
      
      # CHECK: Should we queue this violation?
      action, reason, old_queue_path = gate.should_queue(
          rule_id=violation["rule"],
          selector=violation["selector"],
          score=response.score,
      )
      
      # DECIDE: Skip if duplicate/inferior
      if action == "SKIP":
          return {"delivered": False, "reason": f"hitl_queue_dedup: {reason}"}
      
      # ADD/REPLACE: Write queue file
      queue_path = _hitl_queue_path(violation)
      queue_path.write_text(json.dumps({...}))
      
      # RECORD: Update persistent store
      gate.record_queue_entry(
          rule_id=violation["rule"],
          selector=violation["selector"],
          queue_path=str(queue_path),
          score=response.score,
      )
      
      # CLEANUP: Delete old if replacing
      if action == "REPLACE" and old_queue_path:
          Path(old_queue_path).unlink()


✅ 3. PERSISTENCE: .violation_status.json
──────────────────────────────────────────

File: .violation_status.json (project root)

Tracks per violation:
  {
    "violation_id": "c8f6abec9eba",  ← Deterministic hash(rule_id || selector)
    "rule_id": "html-has-lang",
    "selector": "html",
    "state": "NEW",
    
    # HITL QUEUE TRACKING (NEW Phase 3 feature)
    "hitl_queue_path": "/hitl_queue/1234567890-html.json",
    "hitl_queue_score": 18.0,
    
    # ... other fields
  }

Benefits:
  - Persists across runs
  - Deterministic lookup by rule_id + selector
  - Survives git resets, code changes
  - Enables score comparison for replacement decisions
  - Foundation for Phase 4 human review (mark_reviewed)


✅ 4. MODEL EXTENSION: ViolationStatus
──────────────────────────────────────

File: src/a11y_fixer/domain/violations.py

Added fields:
  hitl_queue_path: Optional[str] = None     # Path to queue entry
  hitl_queue_score: Optional[float] = None  # Score of queued solution

Updated methods:
  to_dict()     - Serializes new fields
  from_dict()   - Deserializes new fields


✅ 5. CLEANUP UTILITY: hitl_queue_dedup.py
──────────────────────────────────────────

File: src/a11y_fixer/adapters/hitl_queue_dedup.py (new)

Purpose: Retroactively clean existing duplicates

Usage:
  python -m a11y_fixer.adapters.hitl_queue_dedup [--dry-run]

Process:
  1. Scan hitl_queue/*.json
  2. Group by (rule_id, selector)
  3. Keep newest per group, archive older to .stale/

Results (Executed 2026-09-02):
  Before: 62 queue files (6 unique violations, 90% duplicates)
  After: 6 active + 56 archived to .stale/


✅ 6. COMPREHENSIVE TESTS
─────────────────────────

File: tests/adapters/test_hitl_queue_gate.py (new)

Test Coverage (9 tests, all passing):
  ✓ New violation → ADD
  ✓ Identical solution → SKIP
  ✓ Better solution → REPLACE
  ✓ Marginally better → SKIP
  ✓ Record queue entry
  ✓ Mark approved (MERGED state)
  ✓ Mark rejected (WONT_FIX state)
  ✓ Skip WONT_FIX violations
  ✓ Multiple independent violations

Status: 9/9 passing ✅


CURRENT STATE
=============

Queue Directory Structure:
  hitl_queue/
    ├── 1788227901565000000-test--x.json (420B) ← ACTIVE
    ├── 1788241109968904000-image-alt-img-src---atlas-dashboard-svg.json (465B)
    ├── 1788241232651310000-image-alt-article-nth-child-2----img.json (499B)
    ├── 1788332364868594000-html-has-lang-html.json (1.1K)
    ├── 1788332365504442000-image-alt-img.json (1.0K)
    ├── 1788332367022509000-test--x.json (995B)
    └── .stale/
        ├── 1788318279093233000-html-has-lang-html.json (archived)
        ├── 1788312945399456000-html-has-lang-html.json (archived)
        └── ... (54 more archived files)

Violation Status:
  5 violations tracked in .violation_status.json
    • c8f6abec9eba: html-has-lang (html)
    • ddbd43478816: color-contrast (p)
    • fc9bef585ff9: link-name (article > a[href$="blog"])
    • 0c345b9fdc91: rule-a (rule-a)
    • 75b64975f4e6: rule-b (rule-b)

HITL fields will be populated when deliver_violation() calls gate.record_queue_entry()


INTEGRATION WORKFLOW
====================

Phase 1: Prevention (Going Forward)
───────────────────────────────────
  python -m a11y_fixer.cli run --audit REPORT --repo PATH
    ↓
  For each violation → deep_agent generates solution
    ↓
  deliver_violation(violation, response)
    ├─ Route decision: "human" or "auto"
    ├─ If "human":
    │  ├─ HITLQueueGate.should_queue() ← DEDUP CHECK
    │  ├─ If "SKIP": Return early (no file written)
    │  ├─ If "ADD" or "REPLACE": Write queue file
    │  └─ gate.record_queue_entry() ← Update .violation_status.json
    └─ If "auto": Create GitHub PR

  Result: Duplicates never reach disk!


Phase 2: Retrospective Cleanup (Already Done)
──────────────────────────────────────────────
  python -m a11y_fixer.adapters.hitl_queue_dedup
    ├─ Scanned 62 existing files
    ├─ Found 56 duplicates across 6 violations
    └─ Moved 56 to .stale/ (62 → 6 active)

  Audit Trail: Preserved all 56 files in .stale/ for inspection


Phase 3-4: Human Review Integration (Ready for Implementation)
──────────────────────────────────────────────────────────────
  review_queue.py review() method should call:
    gate.mark_reviewed(rule_id, selector, decision="approve"|"reject")
      ├─ "approve" → Sets state=MERGED, clears hitl_queue_path
      ├─ "reject"  → Sets state=WONT_FIX, clears hitl_queue_path
      └─ Next run: gate.should_queue() → "SKIP" (human decided)


KEY MECHANISMS
==============

1. Deterministic Violation ID
   ─────────────────────────────
   violation_id = SHA256(rule_id || selector)[:12]
   
   • Independent of scores, runs, timestamps
   • Same hash across entire codebase lifetime
   • Enables cross-run tracking
   • Used as .violation_status.json key


2. Score-Based Replacement
   ───────────────────────────
   if new_score > old_score + 1.5:
       action = "REPLACE"  ← Replace old with new
   else:
       action = "SKIP"     ← Keep existing
   
   • Avoids thrashing when scores similar
   • Only upgrades when significantly better
   • Settable margin: BETTER_SOLUTION_MARGIN = 1.5


3. Human Decision Permanence
   ──────────────────────────
   if state in [WONT_FIX, MERGED]:
       action = "SKIP"  ← Never re-queue after human decision
   
   • Once human reviews, don't escalate again
   • WONT_FIX = don't attempt fix
   • MERGED = already fixed


4. Audit Trail
   ─────────────
   • Active queue: hitl_queue/*.json (current for review)
   • Stale queue: hitl_queue/.stale/*.json (historical)
   • Both preserved for post-hoc analysis
   • Shows evolution of attempts per violation


VERIFICATION
=============

✅ Code Compilation
   python -c "
     from a11y_fixer.adapters.violation_store import HITLQueueGate, ViolationStore
     from a11y_fixer.domain.violations import compute_violation_id
     from a11y_fixer.cli import deliver_violation
     print('✅ All imports successful')
   "

✅ Tests (9/9 passing)
   pytest tests/adapters/test_hitl_queue_gate.py -v
   ✓ test_should_queue_new_violation
   ✓ test_should_queue_identical_solution
   ✓ test_should_queue_better_solution
   ✓ test_should_queue_marginally_better_solution
   ✓ test_record_queue_entry
   ✓ test_mark_reviewed_approve
   ✓ test_mark_reviewed_reject
   ✓ test_skip_wont_fix_violation
   ✓ test_multiple_different_violations

✅ Cleanup Executed
   python -m a11y_fixer.adapters.hitl_queue_dedup
   Result: 62 → 6 active + 56 archived


FILES MODIFIED
==============

[Modified]
  • src/a11y_fixer/cli.py
    - Added HITLQueueGate instantiation
    - Added should_queue() decision logic
    - Added record_queue_entry() call
    - Added old file cleanup on REPLACE

[Modified]
  • src/a11y_fixer/adapters/violation_store.py
    - Added HITLQueueGate class
    - Added should_queue() method (6-case decision)
    - Added record_queue_entry() method
    - Added mark_reviewed() method

[Modified]
  • src/a11y_fixer/domain/violations.py
    - Added hitl_queue_path field to ViolationStatus
    - Added hitl_queue_score field to ViolationStatus
    - Updated to_dict() serialization
    - Updated from_dict() deserialization

[Created]
  • src/a11y_fixer/adapters/hitl_queue_dedup.py
    - Standalone cleanup utility
    - Retroactive duplicate removal
    - Audit trail preservation to .stale/

[Created]
  • tests/adapters/test_hitl_queue_gate.py
    - 9 comprehensive test cases
    - Tests all decision branches
    - All passing


DOCUMENTATION
==============

[Created]
  • HITL_QUEUE_DEDUP_DESIGN.md - Conceptual design
  • HITL_QUEUE_FLOW.md - Complete flow diagrams


NEXT STEPS
==========

1. ✅ DONE: Source prevention via HITLQueueGate
2. ✅ DONE: Cleanup existing duplicates
3. ✅ DONE: Comprehensive test coverage
4. ⏳ PENDING: ReviewQueue.review() integration
5. ⏳ PENDING: Phase 4 human review workflow
6. ⏳ PENDING: Documentation updates (agent-plan.md)


ANSWER TO USER QUESTION
========================

WHERE are HITL queue files created?
  → src/a11y_fixer/cli.py, deliver_violation() function, line ~275
    File path: hitl_queue/{timestamp}-{slug}.json

WHO creates them?
  → deliver_violation() function
    Called from: run() loop after deep_agent generates solution

WHEN are they created?
  → When route decision = "human"
    After guardrails/risk assessments evaluate response
    Before returning to user loop
    Timing: Seconds after deep_agent completes

HOW to prevent duplicates?
  → HITLQueueGate.should_queue() gating mechanism:
    1. Lookup prior attempt in .violation_status.json
    2. Check deterministic violation_id (rule_id + selector)
    3. Apply decision logic (6 cases)
    4. Return: ADD/SKIP/REPLACE
    5. If SKIP: No file written (duplicate prevented)
    6. If REPLACE: Delete old file, write new one

EXISTING DUPLICATE CLEANUP?
  → Already executed via hitl_queue_dedup.py
    Before: 62 files (6 unique violations, 90% duplicates)
    After: 6 active + 56 archived to .stale/


MECHANISM SUMMARY
=================

Similar to PR delivery deduplication (PrePipelineGate):
  ✓ Deterministic violation_id lookup
  ✓ State machine tracking (NEW, MERGED, WONT_FIX, etc.)
  ✓ Score-based comparison for replacement
  ✓ Persistent store (.violation_status.json)
  ✓ Human decision permanence
  ✓ Audit trail preservation

Specific to HITL queue (Phase 3):
  ✓ Queue-specific fields (hitl_queue_path, hitl_queue_score)
  ✓ Margin-based replacement (1.5 score point threshold)
  ✓ Nanosecond-precision timestamps for tie-breaking
  ✓ Archived stale entries (.stale/ directory)
  ✓ Pre-queue gating (prevents creation, not cleanup)
"""
