# GitHub Merge Detection & Sync Implementation Summary

## What Was Built

Implemented a missing feature: **GitHub Merge Detection and State Sync**.

When a PR is created by the system (or merged manually in GitHub), the violation store wasn't tracking whether it was actually merged. This caused:
- ❌ Duplicate PR creation on next audit
- ❌ Dashboard showing stale "queue items" for PRs already merged
- ❌ No way to sync local state with GitHub reality

Now the system can detect and sync merged PRs back to the violation store.

---

## The Complete PR Lifecycle (Now Implemented)

```
┌─────────────────────────────────────────────────────────────────┐
│ VIOLATION DETECTED (audit phase)                                │
└──────────────────────────┬──────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ AGENT GENERATES FIX (score assigned)                            │
│  - score ≥ 18/20: AUTO ROUTE (will auto-merge)                 │
│  - score 15-18/20: HUMAN ROUTE (needs review)                  │
│  - score < 15/20: HUMAN ROUTE (needs review)                   │
└──────────────────────────┬──────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ SYSTEM CREATES QUEUE ENTRY in hitl_queue/                      │
│  - File stored locally with violation + fix + score             │
│  - NOT yet delivered to GitHub                                  │
└──────────────────────────┬──────────────────────────────────────┘
                           ↓
         ┌─────────────────┴──────────────────┐
         │                                    │
         ▼                                    ▼
    AUTO (≥18)                          HUMAN (15-18, <15)
         │                                    │
         ├─ User runs:                       ├─ User reviews:
         │  queue-sync --auto-approve        │  queue-sync
         │  --live                            │  review FILENAME --approve
         │                                   │
         ↓                                    ↓
    ✅ PR CREATED                        ✅ PR CREATED
       in GitHub                            in GitHub
       state: PR_OPEN                       state: PR_OPEN
         │                                    │
         ├─ If score ≥ 18:                  ├─ User merges manually
         │  Auto-merge immediately           │  in GitHub UI
         │  state → MERGED                   │
         │                                    │
         └─ If merged, state → MERGED        │
                                             ↓
                                          ⏳ PR stays OPEN
                                             in GitHub
                                             state: PR_OPEN
                                             (system doesn't know yet)
                                             │
                                             ├─ User manually merges
                                             │  in GitHub
                                             │
                                             └─→ NEW: User runs:
                                                queue-sync --check-merged --live
                                                   ↓
                                                Sync state to MERGED
                                                Prevent duplicate PRs

         ↓
    ✅ VIOLATION STORED
       state: MERGED (verified!)
       PR#: 123
       score: 20/20
         │
         └─ Next audit:
            ✅ Skips this violation
            ✅ No duplicate PR created
```

---

## Usage Guide

### 1. View Pending Queue Items

```bash
cd cmu-capstone/agent
python -m a11y_fixer.cli queue-sync
```

**Output:**
```
📊 HITL Queue Status
   Pending: 3 | Reviewed: 2 | Total: 5

📋 Pending Queue Items (sorted by score):
   1. [🟢 20/20] html-has-lang       | html
      📄 1788332364868594000-html-has-lang-html.json
   2. [🟡 17/20] color-contrast      | p > span
      📄 1788332364868594000-color-contrast-p.json
   3. [🔴 12/20] image-alt            | img.hero
      📄 1788332364868594000-image-alt-img.json
```

### 2. Auto-Approve High-Scoring Items (Dry-Run)

```bash
python -m a11y_fixer.cli queue-sync --auto-approve --no-live
```

**Output:**
```
📊 HITL Queue Status
   ...
✅ Auto-approving 1 high-scoring item(s):
   ✓ html-has-lang           → PR #123
```

### 3. Auto-Approve and Create Real PRs

```bash
python -m a11y_fixer.cli queue-sync --auto-approve --live
```

This creates real PRs in GitHub and auto-merges them if score ≥ 18.

### 4. Check for Manually Merged PRs (NEW FEATURE)

Check which PRs have been merged in GitHub:

```bash
python -m a11y_fixer.cli queue-sync --check-merged --no-live
```

**Output:**
```
🔄 Checking GitHub for merged PRs...
   Total open PRs to check: 3
   ✅ PR #110 [html-has-lang] is MERGED (score: 20/20)
   ⏳ PR #111 [image-alt] is OPEN (not merged)
   ⏳ PR #112 [color-contrast] is OPEN (not merged)

📋 DRY-RUN: Would update 1 PR(s) to MERGED state
   Run with --live to persist changes
```

### 5. Sync Merged PRs Back to Violation Store

```bash
python -m a11y_fixer.cli queue-sync --check-merged --live
```

This:
1. Queries GitHub for each open PR
2. Detects which ones have been merged
3. Updates violation_store state to MERGED
4. Prevents duplicate PR creation on next audit

---

## How It Works Internally

### The Flow (Data Perspective)

```
┌─────────────────────────────────────────────────────────────────┐
│ violation_store (.violation_status.json)                        │
│                                                                 │
│ {                                                               │
│   "7fa3c2b8d1e9": {                                             │
│     "violation_id": "7fa3c2b8d1e9",                             │
│     "rule_id": "html-has-lang",                                │
│     "selector": "html",                                         │
│     "state": "PR_OPEN",  ← System sees this                    │
│     "current_pr_number": 110,                                   │
│     "current_score": 20.0,                                      │
│     "created_at": "2026-09-02T12:34:56+00:00",                 │
│     "updated_at": "2026-09-02T12:34:56+00:00"                  │
│   }                                                             │
│ }                                                               │
│                                                                 │
│ ↓ queue-sync --check-merged --live                            │
│ ↓ Queries GitHub API: GET /repos/owner/repo/pulls/110          │
│ ↓ Response: "merged": true, "merged_at": "2026-09-02T12:45..."│
│ ↓ Updates state: "state": "MERGED"                            │
│                                                                 │
│ After sync:                                                     │
│   "state": "MERGED" ← Now matches GitHub reality               │
│ }                                                               │
└─────────────────────────────────────────────────────────────────┘
```

### Code Changes

**File: [src/a11y_fixer/cli.py](src/a11y_fixer/cli.py)**

- **New function:** `_check_merged_prs(pr_config, live)`
  - Reads violation_store
  - Filters to PR_OPEN states only
  - Queries GitHub API for each PR#
  - Detects merged_at timestamp
  - Updates state to MERGED if merged
  - Shows summary and dry-run preview
  - Saves to disk if `live=True`

- **New CLI flag:** `--check-merged`
  - Added to queue-sync subcommand parser
  - Mutually exclusive with `--auto-approve` (can use both independently)
  - Works with `--live` / `--no-live` flags

**File: [src/a11y_fixer/domain/violations.py](src/a11y_fixer/domain/violations.py)**

- **Bug fix:** `ViolationStatus.from_dict()`
  - Now handles null datetime fields gracefully
  - Provides UTC now() as default if missing
  - Prevents crash when loading corrupted store data

---

## Key Design Decisions

### 1. Polling, Not Webhooks
- ✅ No webhook infrastructure needed (complex to test/deploy)
- ✅ User runs CLI command when they want to check
- ✅ Works in isolated test environments
- ⚠️ Not real-time (but sufficient for current workflow)

### 2. Escalate-Only State Updates
- Can only change PR_OPEN → MERGED
- Can never change MERGED → PR_OPEN (safety)
- Can never skip a merged PR again

### 3. Fallback to Current Behavior
- If `.violation_status.json` doesn't exist: start fresh
- If GitHub API fails: user can retry later
- No automatic retries on network errors (explicit is better)

---

## Error Handling

### What Happens If...

**GitHub API is down?**
```
   ⚠️  PR #110: API error 500
   ⚠️  PR #111: API error 500
   No merged PRs found
```
User can retry later.

**GITHUB_TOKEN is not set?**
```
❌ GitHub token not configured (set GITHUB_TOKEN env var)
Exit code: 1
```

**Invalid PR number in store?**
```
   ⚠️  PR #999: API error 404
   ⏳ PR #999 [image-alt] is unknown
```
System reports it but continues.

**No PR_OPEN violations to check?**
```
✅ No open PRs to check
Exit code: 0
```

---

## Testing the Feature

### Scenario 1: Auto-Merge (Score ≥ 18)

```bash
# 1. Run audit to generate violations
python -m a11y_fixer.cli audit --repo <path> --live

# 2. Auto-approve high-scoring items
python -m a11y_fixer.cli queue-sync --auto-approve --live
# → Creates PR #100, auto-merges it

# 3. Check state
cat .violation_status.json | jq '.[] | select(.state == "MERGED")'
# → Shows PR #100 with state: "MERGED"
```

### Scenario 2: Manual Review (Score 15-18)

```bash
# 1. Queue item created (score 17/20)
python -m a11y_fixer.cli queue-sync
# → Shows: 🟡 17/20 color-contrast

# 2. User manually merges PR #101 in GitHub

# 3. Check if merged
python -m a11y_fixer.cli queue-sync --check-merged --no-live
# → Shows: ✅ PR #101 [color-contrast] is MERGED

# 4. Sync state
python -m a11y_fixer.cli queue-sync --check-merged --live
# → Updates violation_store

# 5. Verify
python -m a11y_fixer.cli queue-sync
# → Queue is now empty (no more pending items)
```

---

## Future Enhancements

### Phase 2: Success Lessons (Not Yet Implemented)

Create wiki lessons for successful merges, not just rejections:

```
wiki/lessons/
├── color-contrast-P34FX7.json (rejection lesson)
└── html-has-lang-SUCCESS.json (NEW: success lesson)
```

### Phase 3: Dashboard Backend

Connect dashboard buttons to real CLI commands:

```javascript
// Dashboard approve button
fetch('/api/queue/review', {
  method: 'POST',
  body: JSON.stringify({
    filename: '...json',
    decision: 'approve'
  })
})
// → Calls: python -m a11y_fixer.cli review FILE --approve
```

### Phase 4: Webhook Support

GitHub webhook → System notification → Auto-sync (real-time):

```
GitHub merge event → POST /webhook/merge → Auto-sync state
```

---

## Troubleshooting

### "GitHub token not configured"
```bash
# Set in .env:
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
GITHUB_REPO=mdrmtz/Hallucinate.io

# Or export:
export GITHUB_TOKEN=...
export GITHUB_REPO=...
```

### "No open PRs to check" (but I have queue items)
This means all queue items have state: NEW (not yet delivered to GitHub).
Run `queue-sync --auto-approve --live` first to create PRs.

### "PR is OPEN but I merged it in GitHub"
GitHub has a slight delay (~30s) before the API reflects the merge.
Wait a moment and retry: `queue-sync --check-merged --live`

---

## Files Modified

1. **[src/a11y_fixer/cli.py](src/a11y_fixer/cli.py)**
   - Added `_check_merged_prs()` function
   - Added `--check-merged` flag to parser
   - ~90 lines new code

2. **[src/a11y_fixer/domain/violations.py](src/a11y_fixer/domain/violations.py)**
   - Fixed `from_dict()` datetime handling
   - ~5 lines modified

3. **[MERGE-AND-SYNC-FLOW.md](MERGE-AND-SYNC-FLOW.md)** (NEW)
   - Comprehensive 400-line flow diagram
   - Current state analysis
   - Gap identification
   - Implementation roadmap

---

## Related Documentation

- [MERGE-AND-SYNC-FLOW.md](MERGE-AND-SYNC-FLOW.md) — Complete flow diagrams and design
- [agent-plan.md](agent-plan.md#phase-e2-hitl-capture-surface) — Phase E.2 tracking
- [tests/hitl/test_review_queue.py](tests/hitl/test_review_queue.py) — Review queue tests
- [tests/test_cli.py](tests/test_cli.py#test_cmd_queue_sync*) — CLI tests

