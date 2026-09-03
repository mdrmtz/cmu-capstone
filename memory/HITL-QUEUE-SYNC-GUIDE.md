# HITL Queue Sync Guide

## The Problem

When you run the agent with `run_eval` or `cli run`, high-scoring fixes get queued in `hitl_queue/` for human review (`route == "human"`), but:

1. **Local vs Remote Mismatch**: Dashboard shows 6 local queue files, but only 1 actual GitHub PR exists
2. **No Automatic Sync**: Queue files don't automatically become PRs - they wait for human approval
3. **Dashboard Limitation**: The dashboard only stores decisions in browser `localStorage`, not in any backend
4. **Lost High-Scores**: Items with score ≥ 18 should auto-merge, but they're stuck in the queue

## Queue File Lifecycle

```
TEST RUN
   ↓
Fix generates (score 18+/20)
   ↓
route="human" decision
   ↓
Queue file created: hitl_queue/TIMESTAMP-RULE-SELECTOR.json
   ↓
Dashboard shows ticket (localStorage only)
   ↓
❌ No PR created until human clicks "Approve"
```

## Solution: Use `queue-sync` Command

### 1. **See All Pending Items with Scores**

```bash
cd cmu-capstone/agent
python -m a11y_fixer.cli queue-sync
```

**Output:**
```
📊 HITL Queue Status
   Pending: 6 | Reviewed: 0 | Total: 6

📋 Pending Queue Items (sorted by score):
   1. [🟢 20.0/20] html-has-lang        | html
      📄 1788332364868594000-html-has-lang-html.json
   2. [🟢 18/20] image-alt-missing    | ?
      📄 1788241109968904000-image-alt-img-src---atlas-dashboard-svg.json
   3. [🟡 17/20] color-contrast       | ?
      📄 1788241232651310000-image-alt-article-nth-child-2----img.json
   ...
```

**Key indicators:**
- 🟢 **Green** (≥18/20): High quality, safe to auto-approve and auto-merge
- 🟡 **Yellow** (15-17/20): Good quality, worth reviewing
- 🔴 **Red** (<15/20): Lower confidence, manual review recommended

### 2. **Auto-Approve & Deliver High-Scoring Items**

```bash
# Dry-run: see what would happen without creating real PRs
python -m a11y_fixer.cli queue-sync --auto-approve --no-live

# Live: actually create PRs for high-scoring items
python -m a11y_fixer.cli queue-sync --auto-approve --live
```

This will:
- ✅ Find all items with score ≥ 18.0
- ✅ Create a real PR for each in GitHub
- ✅ Auto-merge PRs (our code supports merge-when-ready on high scores)
- ✅ Record the approval decision (.decision.json)
- ✅ Remove from the pending queue

### 3. **Manually Review Specific Items**

```bash
# List pending items
python -m a11y_fixer.cli review --list

# Approve a specific item (creates PR and merges if score ≥ 18)
python -m a11y_fixer.cli review 1788241109968904000-image-alt-img-src---atlas-dashboard-svg.json --approve --live

# Reject a specific item (records lesson for future learning)
python -m a11y_fixer.cli review 1788332365504442000-image-alt-img.json --reject --notes "Selector was incorrect, needs human fix"
```

### 4. **Clean Up Stale Test Files**

During development/testing, old queue files accumulate. Clean them up:

```bash
# Archive old test files (don't delete in case you need them)
mkdir -p hitl_queue/.stale
mv hitl_queue/*test*.json hitl_queue/.stale/

# Or delete them if you're sure
rm hitl_queue/*test*.json
```

Then re-run:
```bash
python -m a11y_fixer.cli queue-sync
```

## Best Practices for Testing

### ✅ To NOT Lose High-Scoring PRs:

1. **After a test run**, check the queue immediately:
   ```bash
   python -m a11y_fixer.cli queue-sync
   ```

2. **Auto-approve high-scoring items** (dry-run first):
   ```bash
   python -m a11y_fixer.cli queue-sync --auto-approve --no-live
   # Review the output, then run with --live to create real PRs
   ```

3. **Optional: Manually review medium-scoring items** (15-17):
   ```bash
   python -m a11y_fixer.cli review FILENAME --approve --live
   ```

4. **Clean up rejected/test items** to keep the queue lean:
   ```bash
   rm hitl_queue/*test*.json
   ```

### ❌ What NOT to Do:

- ❌ Don't delete queue files directly - they contain important violation history
- ❌ Don't rely on browser "Approve" buttons - they only write to `localStorage`, not the backend
- ❌ Don't assume a high-scoring item is merged just because it's in the queue - check GitHub

## Syncing with GitHub

### Understanding the Current State

The Phase 0.2 implementation added:
- **ViolationStore** (`.violation_status.json`): Tracks violation state across runs
- **Pre-pipeline deduplication**: Avoids creating duplicate PRs for the same selector
- **Auto-merge logic**: PRs with score ≥ 18.0 auto-merge (when delivered)

### The Disconnect

The HITL queue and auto-merge only work when you **actively approve** items:

```
HIGH-SCORE FIX IN QUEUE
   ↓
User runs: queue-sync --auto-approve --live
   ↓
PR created in GitHub + auto-merge triggered
   ↓
PR merges if tests pass ✅
```

**Without `queue-sync --auto-approve`, the PR is never created.**

### Future: Dashboard Backend Integration

The current dashboard is **frontend-only** (uses `localStorage`). To make it fully integrated:

1. Add a backend API endpoint:
   ```
   POST /api/queue/approve/{filename}
   POST /api/queue/reject/{filename}
   GET  /api/queue/status
   ```

2. Connect dashboard buttons to the API (instead of `localStorage`)

3. Sync can happen in real-time

**For now**: Use the CLI commands above. They're production-ready and reliable.

## Quick Reference

```bash
# Check queue status
python -m a11y_fixer.cli queue-sync

# Auto-approve high-scoring items (dry-run)
python -m a11y_fixer.cli queue-sync --auto-approve --no-live

# Auto-approve high-scoring items (live PR creation)
python -m a11y_fixer.cli queue-sync --auto-approve --live

# List pending items
python -m a11y_fixer.cli review --list

# Approve a single item
python -m a11y_fixer.cli review FILENAME --approve --live

# Reject a single item
python -m a11y_fixer.cli review FILENAME --reject --notes "reason"
```

## Troubleshooting

### "hitl queue is empty" but I just ran a test

- Check that your test run actually created violations
- Check `observability/log/scores-breakdown-*.json` to see if cases passed
- Verify you have `--no-live` set (dry-run mode queues items instead of trying to PR)

### "Error: not found in the hitl queue"

- The file may have already been reviewed (check for `.decision.json` file)
- Use `review --list` to see current pending items

### PR was created but not merged

- Check GitHub PR page for why tests failed
- If score < 18.0, it won't auto-merge (manual merge or fix the score)
- Verify `--live` flag was used (not `--no-live`)

### I accidentally deleted a queue file

- It's backed up in the `.violation_status.json` file (ViolationStore)
- Recovery: contact the author or re-run the agent to regenerate

