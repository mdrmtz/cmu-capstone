"""
HITL Queue Deduplication: Source Trace and Prevention Mechanism

This document traces WHERE, WHO, WHEN HITL queue files are created,
and HOW to prevent duplicates at the source.
"""

# ============================================================================
# WHO CREATES HITL QUEUE FILES?
# ============================================================================
# Function: deliver_violation() in src/a11y_fixer/cli.py (line ~265)
# Called from: run() -> process violations loop
# Entry point: python -m a11y_fixer.cli run [--audit REPORT] [--repo PATH]

# ============================================================================
# WHEN ARE THEY CREATED?
# ============================================================================
# Condition: After violation is processed, BEFORE routing decision
# Timing: In deliver_violation() after _capture_and_reset_git_changes()
# Trigger: When route == "human" (escalation needed)
#
# Flow:
# 1. deep_agent processes violation → generates solution
# 2. deliver_violation() evaluates risk/guardrails
# 3. Decision: route = "human" or "auto"
# 4. If route == "human": Write to hitl_queue/
# 5. If route == "auto": Deliver as PR

# ============================================================================
# WHERE ARE THEY STORED?
# ============================================================================
# Directory: hitl_queue/ (project root)
# Filename format: {timestamp}-{slug}.json
#   - timestamp: int(time.time_ns()) = 18-digit nanosecond timestamp
#   - slug: normalized rule_id + selector
#   Example: 1788332364868594000-html-has-lang-html.json

# File structure:
# {
#   "violation": { "rule", "selector", "url", "html" },
#   "response": { "code", "score", "route", "rationale" },
#   "risk_assessments": [ ... ],
#   "epistemic_gate": { "verdict", ... },
#   "path_violations": [ ... ],
#   "changes": [ { "path", "old_content", "new_content" } ]
# }

# ============================================================================
# WHY WERE DUPLICATES CREATED?
# ============================================================================
# Root cause: deliver_violation() had NO deduplication logic
# Symptom: Re-running violations multiple times created 62 files for only 6 violations
# 
# Multiple calls to deliver_violation() with:
#   - Same violation (rule_id + selector)
#   - Different scores or timestamps
#   - No check if already queued
# → Each call unconditionally created a NEW timestamped file
# 
# Example:
#   Run 1: Create 1788311192492725000-html-has-lang-html.json (score 18)
#   Run 2: Create 1788312945399456000-html-has-lang-html.json (score 19)  ← DUPLICATE
#   Run 3: Create 1788318279093233000-html-has-lang-html.json (score 17)  ← DUPLICATE
#   ... (repeat 13x more times)

# ============================================================================
# SOLUTION: HITLQueueGate Deduplication at SOURCE
# ============================================================================
# Location: src/a11y_fixer/adapters/violation_store.py
# Class: HITLQueueGate
#
# Implements SAME logic as PrePipelineGate for PRs, but for HITL queue:
#
# Decision Matrix:
#   1. NEW violation → ADD to queue
#   2. IDENTICAL score → SKIP (already queued with same solution)
#   3. BETTER score → REPLACE old queue entry (delete old, write new)
#   4. MARGINALLY BETTER → SKIP (existing entry good enough)
#   5. MARKED WONT_FIX by human → SKIP (no retry)
#   6. ALREADY MERGED → SKIP (already fixed)
#
# Integration point in deliver_violation() [cli.py line ~265]:
#   if route == "human":
#       store = ViolationStore(...)
#       gate = HITLQueueGate(store)
#       
#       # Check if should queue
#       action, reason, old_path = gate.should_queue(
#           rule_id=violation["rule"],
#           selector=violation["selector"],
#           score=response.score,
#       )
#       
#       # Skip if duplicate/inferior solution
#       if action == "SKIP":
#           return { "delivered": False, "reason": f"hitl_queue_dedup: {reason}" }
#       
#       # Add or replace queue entry
#       queue_path = _hitl_queue_path(violation)
#       queue_path.write_text(json.dumps({...}))
#       
#       # Record in violation store
#       gate.record_queue_entry(
#           rule_id=violation["rule"],
#           selector=violation["selector"],
#           queue_path=str(queue_path),
#           score=response.score,
#       )
#       
#       # Clean up old entry if replacing
#       if action == "REPLACE" and old_path:
#           Path(old_path).unlink()

# ============================================================================
# DATA STRUCTURE: violation_status.json
# ============================================================================
# Persistent store: .violation_status.json
# Tracks every violation across runs
#
# Schema (per violation):
# {
#   "violation_id": "c8f6abec9eba",  ← deterministic hash(rule_id || selector)
#   "rule_id": "html-has-lang",
#   "selector": "html",
#   "state": "NEW" | "PR_OPEN" | "MERGED" | "WONT_FIX" | ...
#   
#   # PR tracking (for auto route)
#   "current_pr_number": 42,
#   "current_score": 18.0,
#   "best_score": 20.0,
#   
#   # HITL QUEUE TRACKING (NEW - Phase 3 feature)
#   "hitl_queue_path": "/hitl_queue/1234567890-html-has-lang-html.json",
#   "hitl_queue_score": 18.0,
#   
#   # Timeline
#   "created_at": "2026-09-02T...",
#   "updated_at": "2026-09-02T...",
#   "closed_at": null,
#   "close_reason": null
# }

# ============================================================================
# CLEANUP OF EXISTING DUPLICATES
# ============================================================================
# Tool: hitl_queue_dedup.py
# Purpose: Retroactively clean up existing duplicates
# 
# Usage:
#   python -m a11y_fixer.adapters.hitl_queue_dedup [--dry-run]
#
# Process:
#   1. Scan hitl_queue/ for all .json files
#   2. Group by (rule_id, selector) combination
#   3. Per group: Keep newest, move rest to .stale/ subdirectory
#   4. Preserve audit trail (stale files archived, not deleted)
#
# Results (from actual run):
#   Before: 62 total files
#   After: 6 active files (unique violations)
#   Moved: 56 duplicate files to .stale/

# ============================================================================
# TEST COVERAGE
# ============================================================================
# File: tests/adapters/test_hitl_queue_gate.py
# Tests: 9 scenarios
#   ✓ New violation → ADD
#   ✓ Identical solution → SKIP
#   ✓ Better solution → REPLACE
#   ✓ Marginally better → SKIP
#   ✓ Record queue entry
#   ✓ Mark approved
#   ✓ Mark rejected
#   ✓ Skip WONT_FIX
#   ✓ Multiple independent violations
# Status: ✅ All passing

# ============================================================================
# WORKFLOW SUMMARY
# ============================================================================
#
# PHASE 1: Source Prevention (Going Forward)
# ───────────────────────────────────────────
# deliver_violation()
#   ↓
# [Gate Check] should_queue(rule, selector, score)
#   ↓ (ADD/SKIP/REPLACE)
# ├─ ADD: Write new queue file
# ├─ SKIP: Return early (no file written)
# └─ REPLACE: Delete old, write new
#   ↓
# record_queue_entry(rule, selector, path, score)
# (Updates violation_status.json)
#
# PHASE 2: Retrospective Cleanup (Already Done)
# ──────────────────────────────────────────────
# hitl_queue_dedup.py --dry-run  (inspect)
#   → Shows 56 duplicates to remove
#   ↓
# hitl_queue_dedup.py  (execute)
#   → Moves 56 files to .stale/
#   → Active queue: 62 → 6 files
#
# PHASE 3: Human Review Integration (Phase 3-4)
# ───────────────────────────────────────────────
# review_queue.review(queue_path, decision="approve"|"reject")
#   ↓
# gate.mark_reviewed(rule, selector, decision)
#   → Updates violation_status.json
#   → Sets state → MERGED (approve) | WONT_FIX (reject)
#   → Clears hitl_queue_path
#
# Next run:
# gate.should_queue(...) → SKIP (already decided by human)

# ============================================================================
# INTEGRATION CHECKLIST
# ============================================================================
# [x] Add hitl_queue_path and hitl_queue_score to ViolationStatus
# [x] Implement HITLQueueGate class
# [x] Update deliver_violation() to use gate
# [x] Update deliver_violation() to record queue path
# [x] Update deliver_violation() to clean up old entries on REPLACE
# [x] Implement hitl_queue_dedup.py cleanup utility
# [x] Clean up existing 56 duplicate entries
# [x] Write comprehensive tests
# [x] Integrate with ReviewQueue.review() for human decisions
# [ ] Update Phase 3-4 plan to reference this deduplication
# [ ] Document in agent-plan.md

# ============================================================================
# KEY INSIGHTS
# ============================================================================
# 1. Deduplication happens at TWO levels:
#    - SOURCE: HITLQueueGate gates entry to prevent creation
#    - CLEANUP: hitl_queue_dedup retroactively tidies existing files
#
# 2. Deterministic violation_id (hash of rule+selector):
#    - Independent of scores, runs, or timestamps
#    - Enables cross-run tracking
#    - Same design used for PR delivery deduplication
#
# 3. Score-based replacement decision:
#    - Only replace if NEW score > OLD score + 1.5 margin
#    - Prevents thrashing when scores are similar
#    - Human decisions (WONT_FIX, MERGED) are permanent
#
# 4. Audit trail preservation:
#    - Stale files archived, not deleted
#    - Can reconstruct history of attempts
#    - Supports post-hoc analysis of why decisions were made
