# PR Merge Flow and GitHub Sync

## Current Flow (What Happens Now)

### Scenario 1: User approves via `queue-sync --auto-approve` (High Score ≥ 18/20)

```
QUEUE ITEM (score 20/20)
    ↓
User runs: queue-sync --auto-approve --live
    ↓
ReviewQueue.review() called with decision="approve"
    ↓
PR created in GitHub via pr_delivery.deliver()
    ↓
PR number stored in violation store
    ↓
GitHubPRManager.auto_merge_pr() called (score >= 18.0)
    ↓
✅ GitHub API: PUT /repos/owner/repo/pulls/{pr}/merge
    ↓
GitHub merges the PR
    ↓
Violation store updated: state = MERGED
    ↓
.decision.json created: { decision: "approve", delivered: True, pr_number: 123, merged: True }
    ↓
Queue item removed from pending list
    ↓
❌ NO LESSON CREATED (only created on REJECT)
```

**Current State Tracking:**
```json
{
  "violation_id": "7fa3c2b8d1e9",
  "rule_id": "html-has-lang",
  "selector": "html",
  "state": "MERGED",           // Set AFTER auto-merge succeeds
  "current_pr_number": 123,
  "current_score": 20.0,
  "created_at": "2026-09-02T...",
  "updated_at": "2026-09-02T..."
}
```

---

### Scenario 2: User manually approves via `review --approve` (Medium Score 15-18/20)

```
QUEUE ITEM (score 17/20)
    ↓
User runs: review FILENAME --approve --live
    ↓
ReviewQueue.review() called
    ↓
PR created in GitHub
    ↓
GitHubPRManager.auto_merge_pr() called (but score < 18.0)
    ↓
❌ Auto-merge is SKIPPED (score below threshold)
    ↓
.decision.json created: { decision: "approve", delivered: True, pr_number: 124, merged: False }
    ↓
Violation store updated: state = PR_OPEN (not MERGED)
    ↓
Queue item removed
    ↓
PR waits for manual merge in GitHub
    ↓
⚠️  SYSTEM DOESN'T KNOW IF USER MANUALLY MERGES IT IN GITHUB
```

**State in store:**
```json
{
  "state": "PR_OPEN",           // Stays here forever (no tracking of GitHub merge)
  "current_pr_number": 124,
  "current_score": 17.0
}
```

---

### Scenario 3: User rejects via `review --reject` (Any Score)

```
QUEUE ITEM (score 8/10)
    ↓
User runs: review FILENAME --reject --notes "Selector was wrong"
    ↓
ReviewQueue.review() called with decision="reject"
    ↓
🎓 LESSON CREATED in wiki/lessons/
    {
      "id": "1788332367022509000-color-contrast",
      "rule": "color-contrast",
      "file_path": "src/app.component.html",
      "rejection_reason": "Selector was wrong",
      "constraint": "Selector was wrong",
      "created_at": "2026-09-02T..."
    }
    ↓
wiki/AGENTS.md is rebuilt (appends the lesson)
    ↓
.decision.json created: { decision: "reject", lesson_id: "1788332367022509000-..." }
    ↓
Violation store updated: state = WONT_FIX
    ↓
Queue item removed
```

**State in store:**
```json
{
  "state": "WONT_FIX",
  "current_pr_number": null,
  "current_score": 8.0
}
```

---

## The Problem: Missing GitHub Sync

### ❌ Gap 1: Manual GitHub Merge Not Tracked

**Scenario:**
```
User approves PR #124 (score 17/20)
    ↓
Violation store: state = PR_OPEN
    ↓
User goes to GitHub and manually merges PR #124
    ↓
✅ GitHub says merged, but...
    ↓
❌ Violation store still says PR_OPEN
    ↓
System re-runs audit, finds same violation again
    ↓
Creates DUPLICATE PR #125 for same violation
    ↓
WASTED WORK + CONFUSION
```

**Why it happens:**
- No webhook from GitHub to notify the system
- No polling mechanism to check PR status
- No "check-in" command to sync PR state

---

### ❌ Gap 2: No Merge Lesson (Only Reject Lesson)

**Current behavior:**
- REJECT → Creates a lesson in `wiki/lessons/`
- APPROVE + MERGE → Creates NOTHING in wiki

**Why this is bad:**
- System only learns from failures
- No institutional memory of SUCCESSES
- Can't identify patterns in high-scoring fixes
- Future runs can't reuse successful patterns

---

### ❌ Gap 3: Dashboard Shows Zero Real-Time Info

**Current state:**
- Dashboard loads from `localStorage` (browser memory)
- No connection to `.violation_status.json` (backend truth)
- No display of PR numbers or merge status
- Can't tell which items are actually merged in GitHub

---

## Ideal Flow: What SHOULD Happen

```
┌─────────────────────────────────────────────────────────────┐
│                        VIOLATION FLOW                        │
└─────────────────────────────────────────────────────────────┘

AUDIT PHASE
    ↓
Find violation: "image-alt missing on <img>"
    ↓
Compute violation_id = hash(rule + selector)
    ↓
Check violation_store.get(violation_id)
    ├─ MERGED:    Skip (already fixed, re-audit confirms)
    ├─ PR_OPEN:   Check if GitHub PR still open
    ├─ WONT_FIX:  Skip (reject lesson exists, don't retry)
    └─ NEW:       Create fix attempt

GENERATION PHASE
    ↓
Agent generates fix (score: 20/20)
    ↓
DELIVERY PHASE (AUTO ROUTE)
    ↓
Create PR in GitHub
    ↓
Store in violation_store: state = MERGED (if score ≥ 18)
    ↓
Auto-merge immediately
    ↓
✅ CREATE SUCCESS LESSON: "Fixed image-alt with selector..."
    ↓
HITL QUEUE: 
    Record in wiki/lessons/ and AGENTS.md
    ├─ What worked: selector and fix pattern
    ├─ Score achieved: 20/20
    ├─ Timestamp and context
    └─ Can be queried by future agent for similar cases

DELIVERY PHASE (HUMAN ROUTE)
    ↓
Queue item created: "Needs human review"
    ↓
Human approves (via queue-sync or review CLI)
    ↓
PR created in GitHub
    ↓
Store in violation_store: state = PR_OPEN (if score < 18)
    ↓
    ├─ Scenario A: User manually merges in GitHub
    │     ↓
    │     NEW: queue-sync --check-merged --live
    │     ↓
    │     Polls GitHub for merge status
    │     ↓
    │     Updates violation_store: state = MERGED
    │     ↓
    │     CREATE SUCCESS LESSON (new feature)
    │
    ├─ Scenario B: GitHub CI/Tests fail
    │     ↓
    │     User fixes issues and re-pushes
    │     ↓
    │     Eventually merges
    │     ↓
    │     queue-sync --check-merged detects it
    │     ↓
    │     Creates lesson with retry context
    │
    └─ Scenario C: User rejects in HITL queue
          ↓
          CREATE REJECTION LESSON (existing feature)
          ↓
          Updates violation_store: state = WONT_FIX

    ↓
RE-AUDIT PHASE (Next Run)
    ↓
Run `audit` again on same repo
    ↓
Find same violation: "image-alt missing"
    ↓
Check violation_store
    ├─ If state = MERGED: Agent can query wiki_lessons
    │                      "This was fixed before with pattern X,
    │                       score was 20/20, try similar approach"
    │
    ├─ If state = WONT_FIX: Skip (lesson says why it failed)
    │
    └─ If state = PR_OPEN: Check GitHub status (if no webhook)
```

---

## Implementation Roadmap

### Phase 1: Sync PR State (Missing Piece)
**Goal:** Make system aware when PRs are merged in GitHub (manually or via CI)

#### Add new CLI command: `queue-sync --check-merged`

```bash
# Dry-run: See which PRs have been merged in GitHub
python -m a11y_fixer.cli queue-sync --check-merged --no-live

# Live: Update violation store to reflect GitHub reality
python -m a11y_fixer.cli queue-sync --check-merged --live
```

**What it does:**
1. Reads `.violation_status.json`
2. For each violation with `state = PR_OPEN`:
   - Query GitHub API: `GET /repos/owner/repo/pulls/{pr_number}`
   - Check if `state = "closed"` AND `merged_at` is not null
3. If merged:
   - Update violation store: `state = MERGED`
   - Create SUCCESS LESSON (new feature)
   - Remove from pending queue

**Implementation steps:**
```python
def _cmd_queue_sync(args):
    # Existing code for --auto-approve
    if args.check_merged:
        store = ViolationStore(...)
        
        # Get all PR_OPEN violations
        for violation_id, status in store._cache.items():
            if status.state != ViolationState.PR_OPEN:
                continue
            
            # Query GitHub
            pr_number = status.current_pr_number
            merged = check_github_pr_merged(
                github_token=...,
                github_repo=...,
                pr_number=pr_number
            )
            
            if merged:
                # Update store
                status.state = ViolationState.MERGED
                
                # Create success lesson
                create_success_lesson(
                    wiki_dir=...,
                    rule=status.rule_id,
                    selector=status.selector,
                    score=status.current_score,
                    pr_number=pr_number,
                    merged_at=merged["merged_at"]
                )
                
                # Save
                store.upsert(status)
```

---

### Phase 2: Create Success Lessons (New Feature)

**Goal:** Record what worked, not just what failed

#### Create `ingest_success_lesson()` in wiki_pipeline

```python
def ingest_success_lesson(
    wiki_dir: Path,
    *,
    rule: str,
    file_path: str,
    selector: str,
    score: float,
    fix_pattern: str,  # e.g., "Add attr-role='img' to <img>"
    pr_number: int,
    merged_at: str
) -> Lesson:
    """Record what worked for future agent learning."""
    lesson = Lesson(
        id=f"{time.time_ns()}-{_slugify(rule)}-success",
        rule=rule,
        file_path=file_path,
        rejection_reason="",  # Empty for success
        constraint=f"SUCCESS: {fix_pattern} (PR#{pr_number}, score {score}/20)",
        created_at=merged_at,
    )
    # ... persist like rejection lessons
```

#### Update dashboard to show this in wiki

The wiki will grow with:
```
# Institutional Memory

## SUCCESS: html-has-lang - hallucinate.io/src/app.component.html
- Pattern: Add lang="en" to <html> tag
- Score: 20/20 (Perfect)
- PR: #123
- Merged: 2026-09-02

## REJECT: image-alt - hallucinate.io/src/dashboard.component.html
- Reason: Selector was incorrect for this context
- Score: 10/20
```

---

### Phase 3: Dashboard Integration

**Goal:** Show real PR status, not just localStorage

#### Add backend API endpoint (minimal)

```
GET /api/queue/status
  Returns: {
    "pending": 3,
    "merged": 5,
    "rejected": 2,
    "items": [
      {
        "filename": "1788332364868594000-html-has-lang-html.json",
        "rule": "html-has-lang",
        "score": 20,
        "pr_number": 123,
        "state": "MERGED",  // From violation_store
        "merged_at": "2026-09-02T12:34:56Z"
      }
    ]
  }
```

#### Update dashboard HTML

```html
<!-- Instead of localStorage only -->
<td id="pr-status-{filename}">
  <span class="status-merged">✅ Merged PR #123</span>
</td>

<!-- Update via fetch -->
<script>
fetch('/api/queue/status')
  .then(r => r.json())
  .then(data => {
    data.items.forEach(item => {
      const el = document.getElementById(`pr-status-${item.filename}`);
      if (item.state === 'MERGED') {
        el.innerHTML = `✅ Merged PR #${item.pr_number} (${item.score}/20)`;
      } else if (item.state === 'PR_OPEN') {
        el.innerHTML = `⏳ Open PR #${item.pr_number} (${item.score}/20)`;
      }
    });
  });
</script>
```

---

## Implementation Order

### ✅ Done
- [x] CLI queue-sync --auto-approve (high-scoring items auto-merge)
- [x] Rejection lessons in wiki_pipeline
- [x] ViolationStore with state tracking
- [x] Auto-merge logic in GitHubPRManager

### 🔄 In Progress
- [ ] `queue-sync --check-merged` (detect manual GitHub merges)
- [ ] Create success lessons after PR merged
- [ ] Update `.violation_status.json` state to MERGED

### 📋 Future
- [ ] GitHub webhook support (real-time updates)
- [ ] Dashboard backend API
- [ ] Dashboard display of PR status
- [ ] Agent query success lessons during generation
- [ ] Re-audit: skip fixed violations

---

## FAQ

### Q: Why doesn't the system automatically know when a PR is merged?

**A:** No webhook. GitHub can't contact the system to notify of merge. Options:
1. **User runs CLI** (current): `queue-sync --check-merged` polls GitHub
2. **Webhook** (future): GitHub sends event to system immediately
3. **Polling service** (future): Background job checks status periodically

### Q: What happens if I merge a PR in GitHub and then re-run the audit?

**A:** Current behavior (❌ BUG):
- Violation store still says `state = PR_OPEN`
- Audit finds same violation again
- Creates duplicate PR #2 for same violation
- Wasted effort

**After Phase 1 (✅ FIXED):**
- Run: `queue-sync --check-merged --live`
- System detects PR was merged
- Updates store to `state = MERGED`
- Next audit skips it (already fixed)

### Q: How do I know which queue items are already merged?

**Current way (limited):**
```bash
# Check if .decision.json exists
ls hitl_queue/*RULE*.decision.json

# Check violation store
cat .violation_status.json | jq '.[] | select(.state == "MERGED")'
```

**Better way (Phase 1):**
```bash
# Shows which items have merged PRs in GitHub
python -m a11y_fixer.cli queue-sync --check-merged --no-live
```

### Q: Why don't rejected items create PRs?

**By design:** Reject = "Don't attempt this again, here's why"
- Lesson is stored: e.g., "Selector was incorrect"
- Agent learns from rejection
- Won't make same mistake next time

### Q: What if I want to manually merge a PR?

**Current flow:**
1. Queue item approved → PR created → left open (score < 18)
2. Go to GitHub, review & merge manually
3. (System doesn't know yet)
4. Run: `queue-sync --check-merged --live`
5. System detects merge, updates store

**Future (with webhook):**
1-2. Same
3. GitHub webhook notifies system immediately
4. No manual check needed

---

## Files to Check

- Violation tracking: [cmu-capstone/agent/src/a11y_fixer/domain/violations.py](src/a11y_fixer/domain/violations.py)
- Violation store: [cmu-capstone/agent/src/a11y_fixer/adapters/violation_store.py](src/a11y_fixer/adapters/violation_store.py)
- Wiki lessons: [cmu-capstone/agent/src/a11y_fixer/adapters/retrieval/wiki_pipeline.py](src/a11y_fixer/adapters/retrieval/wiki_pipeline.py)
- PR delivery: [cmu-capstone/agent/src/a11y_fixer/adapters/pr/delivery.py](src/a11y_fixer/adapters/pr/delivery.py)
- GitHub management: [cmu-capstone/agent/src/a11y_fixer/adapters/pr/github_pr_manager.py](src/a11y_fixer/adapters/pr/github_pr_manager.py)
- CLI: [cmu-capstone/agent/src/a11y_fixer/cli.py](src/a11y_fixer/cli.py)

