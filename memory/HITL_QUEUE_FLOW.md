"""
HITL Queue Creation Flow: Complete Trace

┌─────────────────────────────────────────────────────────────────────────────┐
│                         ENTRY POINT: WHO?                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  Command: python -m a11y_fixer.cli run [--audit REPORT] [--repo PATH]      │
│                                                                               │
│  ↓                                                                            │
│  File: src/a11y_fixer/cli.py                                               │
│  Function: run()  [line ~190]                                               │
│                                                                               │
│    for violation in violations:                                             │
│        response = deep_agent(violation)  ← AI generates solution           │
│        result = deliver_violation(                                          │
│            violation,                                                       │
│            response,                                                        │
│            fixture,                                                         │
│            pr_config,                                                       │
│            output_dir                                                       │
│        )                                                                     │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────┐
│                    PROCESSING: WHERE AND WHEN?                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  File: src/a11y_fixer/cli.py                                               │
│  Function: deliver_violation() [line ~265]                                  │
│                                                                               │
│  INPUT:                                                                      │
│    violation = {                                                            │
│        "rule": "html-has-lang",                                            │
│        "selector": "html",                                                  │
│        "url": "https://...",                                               │
│        "html": "<html>..."                                                 │
│    }                                                                         │
│                                                                               │
│    response = {                                                             │
│        "code": "<html lang='en'>...",                                      │
│        "score": 18.0,  ← Rubric score (0-20)                              │
│        "route": "human" or "auto"                                          │
│    }                                                                         │
│                                                                               │
│  PROCESSING:                                                                │
│    1. Capture git changes from deep_agent                                   │
│    2. Validate paths (no writes outside fixture)                           │
│    3. Run risk assessments (guardrails)                                    │
│    4. Decide FINAL route: "human" or "auto"                               │
│       → "human" if: response.route="human" OR path_violation OR          │
│                     guardrail blocks OR risk assessment escalates         │
│                                                                               │
│  DECISION POINT: Is route == "human"?                                      │
│    ├─ YES → Create/Update HITL queue entry  ← YOU ARE HERE                │
│    └─ NO  → Create GitHub PR (auto route)                                │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────┐
│                   DEDUPLICATION GATE: HOW? (NEW)                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  Code Location: src/a11y_fixer/cli.py [line ~275-285]                      │
│                                                                               │
│  if route == "human":                                                       │
│                                                                               │
│      # Step 1: Instantiate gate                                            │
│      store = ViolationStore(                                               │
│          status_file=config.agent_root() / ".violation_status.json"       │
│      )                                                                       │
│      gate = HITLQueueGate(store)                                           │
│                                                                               │
│      # Step 2: CHECK if should queue (this is the dedup gate)             │
│      action, reason, old_queue_path = gate.should_queue(                   │
│          rule_id=violation["rule"],        ← "html-has-lang"             │
│          selector=violation["selector"],   ← "html"                       │
│          score=response.score,             ← 18.0                         │
│      )                                                                       │
│                                                                               │
│      # Step 3: DECIDE based on action                                      │
│      if action == "SKIP":                                                   │
│          return { "delivered": False, "reason": f"hitl_queue_dedup: ..." } │
│          # ↑ No file written! Duplicate prevented here!                   │
│                                                                               │
│      # Step 4: ADD or REPLACE - write queue file                          │
│      queue_path = _hitl_queue_path(violation)                              │
│      # → /Users/.../agent/hitl_queue/{nanosecs}-{slug}.json               │
│                                                                               │
│      queue_path.write_text(json.dumps({                                    │
│          "violation": violation,                                           │
│          "response": response,                                             │
│          "risk_assessments": assessments,                                  │
│          "epistemic_gate": gate,                                           │
│          "path_violations": path_violations,                               │
│          "changes": changes,                                               │
│      }))                                                                     │
│                                                                               │
│      # Step 5: RECORD in persistent store                                  │
│      gate.record_queue_entry(                                              │
│          rule_id=violation["rule"],                                        │
│          selector=violation["selector"],                                   │
│          queue_path=str(queue_path),                                       │
│          score=response.score,                                             │
│      )                                                                       │
│      # ↑ Updates .violation_status.json with queue tracking info          │
│                                                                               │
│      # Step 6: CLEANUP old file if REPLACING                              │
│      if action == "REPLACE" and old_queue_path:                            │
│          Path(old_queue_path).unlink()                                     │
│          # ↑ Delete the old inferior solution                             │
│                                                                               │
│      return {                                                               │
│          "delivered": False,                                               │
│          "queue_path": str(queue_path),                                    │
│          "queue_action": action,  ← "ADD" or "REPLACE"                    │
│      }                                                                       │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────┐
│              DECISION LOGIC: HITLQueueGate.should_queue()                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  File: src/a11y_fixer/adapters/violation_store.py                          │
│  Class: HITLQueueGate                                                       │
│  Method: should_queue(rule_id, selector, score) → (action, reason, path)  │
│                                                                               │
│  Decision Tree:                                                             │
│  ─────────────                                                              │
│                                                                               │
│  lookup violation_id = hash(rule_id || selector) in .violation_status.json │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Case 1: prior == None (first time seeing this violation)           │   │
│  │ ────────────────────────────────────────────────────────────────   │   │
│  │ ACTION: "ADD"                                                       │   │
│  │ REASON: "new_violation_escalating_to_human"                        │   │
│  │ OLD_PATH: None                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Case 2: prior.state == WONT_FIX (human already rejected)           │   │
│  │ ────────────────────────────────────────────────────────────────   │   │
│  │ ACTION: "SKIP"                                                      │   │
│  │ REASON: "marked_wont_fix_by_human"                                 │   │
│  │ OLD_PATH: prior.hitl_queue_path (if set)                           │   │
│  │ ⚠️  NEVER re-queue violations humans rejected                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Case 3: prior.state == MERGED (already fixed)                      │   │
│  │ ────────────────────────────────────────────────────────────────   │   │
│  │ ACTION: "SKIP"                                                      │   │
│  │ REASON: "already_merged_to_main"                                   │   │
│  │ OLD_PATH: prior.hitl_queue_path (if set)                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Case 4: prior.hitl_queue_path == None (no current queue entry)     │   │
│  │ ────────────────────────────────────────────────────────────────   │   │
│  │ ACTION: "ADD"                                                       │   │
│  │ REASON: "new_escalation_for_known_violation"                       │   │
│  │ OLD_PATH: None                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Case 5: score == prior.hitl_queue_score (IDENTICAL solution)       │   │
│  │ ────────────────────────────────────────────────────────────────   │   │
│  │ ACTION: "SKIP" ✓ DEDUP!                                             │   │
│  │ REASON: "identical_solution_queued (score=18.0)"                   │   │
│  │ OLD_PATH: prior.hitl_queue_path                                    │   │
│  │ 💡 Same score = same solution, don't re-queue                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Case 6: score > prior.hitl_queue_score + 1.5 (BETTER solution)     │   │
│  │ ────────────────────────────────────────────────────────────────   │   │
│  │ ACTION: "REPLACE" ✓ UPGRADE!                                        │   │
│  │ REASON: "better_solution_ready (new=20.0 vs old=17.0)"             │   │
│  │ OLD_PATH: prior.hitl_queue_path ← DELETE THIS FILE                 │   │
│  │ 🚀 New solution is significantly better, replace old queue entry   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Case 7: else (worse or marginally better)                          │   │
│  │ ────────────────────────────────────────────────────────────────   │   │
│  │ ACTION: "SKIP" ✓ DEDUP!                                             │   │
│  │ REASON: "existing_queue_entry_adequate (new=18.0 vs old=17.5)"     │   │
│  │ OLD_PATH: prior.hitl_queue_path                                    │   │
│  │ 💡 Existing entry good enough, avoid thrashing                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                               │
│  Margin Threshold: 1.5 points (BETTER_SOLUTION_MARGIN constant)           │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────┐
│              PERSISTENT TRACKING: .violation_status.json                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  File: .violation_status.json (project root)                                │
│                                                                               │
│  Per violation, stored as:                                                  │
│  {                                                                           │
│    "c8f6abec9eba": {                      ← violation_id = hash()          │
│      "violation_id": "c8f6abec9eba",                                       │
│      "rule_id": "html-has-lang",                                           │
│      "selector": "html",                                                    │
│      "state": "NEW",                                                        │
│                                                                               │
│      # HITL Queue tracking (Phase 3)                                        │
│      "hitl_queue_path": "/Users/.../hitl_queue/1234567890-html.json",     │
│      "hitl_queue_score": 18.0,                                             │
│                                                                               │
│      # Timestamps                                                           │
│      "created_at": "2026-09-02T14:30:45Z",                                │
│      "updated_at": "2026-09-02T14:31:10Z",                                │
│    },                                                                        │
│    "ddbd43478816": { ... },                                                │
│    ...                                                                       │
│  }                                                                           │
│                                                                               │
│  ✨ This is the SOURCE OF TRUTH for deduplication!                         │
│     - Persistent across runs                                               │
│     - Deterministic lookup by rule_id + selector                          │
│     - Tracks queue_path and score for each violation                      │
│     - Survives code changes, git resets, etc.                            │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────┐
│                  QUEUE FILE FORMAT AND LOCATION                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  Directory: hitl_queue/ (created on demand)                                 │
│  Filename: {nanosecs}-{slug}.json                                          │
│                                                                               │
│  Example path:                                                              │
│  /Users/dks0721706/dev/cmu-agentic-ai-program-2026/                       │
│    cmu-capstone/agent/                                                     │
│    hitl_queue/                                                             │
│    1788332364868594000-html-has-lang-html.json                           │
│                                                                               │
│  Timestamp format: time.time_ns() = nanoseconds since epoch (18 digits)   │
│  Slug: normalized rule + selector (lowercase, spaces→-, special→_)        │
│                                                                               │
│  File Contents:                                                             │
│  {                                                                           │
│    "violation": {                                                           │
│      "rule": "html-has-lang",                                              │
│      "selector": "html",                                                    │
│      "url": "https://...",                                                 │
│      "html": "..."                                                         │
│    },                                                                        │
│    "response": {                                                            │
│      "code": "<html lang='en'>...",                                       │
│      "score": 18.0,                                                        │
│      "route": "human",                                                     │
│      "rationale": "..."                                                    │
│    },                                                                        │
│    "risk_assessments": [ ... ],                                            │
│    "epistemic_gate": { ... },                                              │
│    "path_violations": [ ],                                                 │
│    "changes": [                                                             │
│      {                                                                       │
│        "path": "Hallucinate.io/index.html",                               │
│        "old_content": "...",                                               │
│        "new_content": "..."                                                │
│      }                                                                       │
│    ]                                                                         │
│  }                                                                           │
│                                                                               │
│  THIS FILE is awaiting human review in Phase 4!                            │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────┐
│              RETROSPECTIVE CLEANUP: hitl_queue_dedup.py                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  Purpose: Clean up EXISTING duplicates from prior runs (before gate)       │
│                                                                               │
│  Command:                                                                   │
│    python -m a11y_fixer.adapters.hitl_queue_dedup [--dry-run]             │
│                                                                               │
│  Process:                                                                   │
│    1. Scan hitl_queue/*.json                                               │
│    2. Parse each file to extract rule_id + selector                       │
│    3. Group by (rule_id, selector) key                                    │
│    4. Per group:                                                            │
│       - Keep entry with LATEST timestamp                                   │
│       - Move all older entries to hitl_queue/.stale/                      │
│    5. Preserve audit trail (files not deleted, archived)                  │
│                                                                               │
│  Before: hitl_queue/                                                       │
│    62 total .json files                                                    │
│    6 unique violations (same rule+selector pairs)                         │
│    56 duplicates across these 6 violations                                │
│                                                                               │
│  After:  hitl_queue/                                                       │
│    6 active .json files (newest per violation)                            │
│    hitl_queue/.stale/                                                      │
│    56 archived .json files (for audit trail)                              │
│                                                                               │
│  Example run output:                                                        │
│  ─────────────────────                                                      │
│  Moving: 1788318279093233000-html-has-lang-html.json → .stale/            │
│  Moving: 1788312945399456000-html-has-lang-html.json → .stale/            │
│  Moving: 1788311192492725000-html-has-lang-html.json → .stale/  (older)   │
│  ...                                                                         │
│  Removed: 56 duplicates (kept newest of each violation)                    │
│                                                                               │
│  ✅ Cleanup already executed on 2026-09-02                                 │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────┐
│                       INTEGRATION SUMMARY                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ✅ PREVENTION (Forward-Looking): HITLQueueGate in deliver_violation()     │
│  ✅ CLEANUP (Retrospective): hitl_queue_dedup.py removes existing dups     │
│  ✅ PERSISTENCE: .violation_status.json tracks all violations              │
│  ✅ TESTS: 9 comprehensive tests all passing                               │
│                                                                               │
│  Integration Points:                                                        │
│    [1] deliver_violation() uses HITLQueueGate.should_queue() to gate      │
│    [2] gate.record_queue_entry() updates .violation_status.json           │
│    [3] gate.mark_reviewed() integrates with Phase 4 human review          │
│    [4] Cleanup utility processes existing backlog                         │
│                                                                               │
│  Test Coverage:                                                             │
│    ✓ New violation → ADD                                                    │
│    ✓ Identical score → SKIP                                                │
│    ✓ Better score → REPLACE                                                │
│    ✓ Marginal score → SKIP                                                 │
│    ✓ Human WONT_FIX → SKIP                                                 │
│    ✓ Multiple independent violations tracked                               │
│                                                                               │
│  Files Modified:                                                            │
│    src/a11y_fixer/cli.py [deliver_violation]                              │
│    src/a11y_fixer/adapters/violation_store.py [HITLQueueGate]            │
│    src/a11y_fixer/domain/violations.py [ViolationStatus fields]          │
│    src/a11y_fixer/adapters/hitl_queue_dedup.py [NEW cleanup utility]     │
│    tests/adapters/test_hitl_queue_gate.py [NEW comprehensive tests]      │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
"""
