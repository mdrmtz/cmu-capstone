# HITL Queue Integration: Complete System Overview

## Status Summary

✅ **FULLY IMPLEMENTED** — Shell Script Integration for Dashboard → CLI

This document provides a comprehensive overview of how the dashboard integrates with the accessibility fixer CLI using shell scripts.

## System Architecture

```
┌─────────────────────────────────────┐
│  HITL Queue Dashboard (HTML/JS)     │
│  cmu-capstone/dashboard/hitl_queue/ │
│  - Lists pending queue items        │
│  - Shows violation details & scores │
│  - "Approve Fix" / "Reject" buttons │
└──────────────────┬──────────────────┘
                   │
                   │ User clicks button
                   │ Prompts for name & notes
                   │ Generates shell command
                   │
                   ↓
┌─────────────────────────────────────┐
│  Shell Script Wrapper               │
│  cmu-capstone/agent/review_ticket.sh│
│  - Parses arguments                 │
│  - Calls Python CLI with params     │
│  - Shows colored output with status │
└──────────────────┬──────────────────┘
                   │
                   ↓
┌─────────────────────────────────────┐
│  Python CLI (a11y_fixer.cli)        │
│  cmu-capstone/agent/src/a11y_fixer/ │
│  - review subcommand                │
│  - queue-sync subcommand            │
└──────────────────┬──────────────────┘
                   │
                   ↓
┌─────────────────────────────────────┐
│  Core Business Logic                │
│  - ReviewQueue (approve/reject)     │
│  - GitHubPRManager (create PRs)     │
│  - WikiPipeline (create lessons)    │
│  - ViolationStore (persist state)   │
└──────────────────┬──────────────────┘
                   │
                   ↓
┌──────────────────────────────────────┐
│  External Systems (persisted)       │
│  - GitHub API (create/merge PRs)    │
│  - .violation_status.json           │
│  - wiki/lessons/ directory          │
│  - evaluation/results/prs/ diffs    │
└──────────────────────────────────────┘
```

## File Components

### 1. Dashboard HTML
**File**: [cmu-capstone/dashboard/hitl_queue/index.html](cmu-capstone/dashboard/hitl_queue/index.html)

**JavaScript Functions**:

#### `approveTicket(filename)`
- Prompts user for reviewer name and optional notes
- Extracts queue filename (strips path if present)
- Generates shell command:
  ```bash
  cd ../agent && ./review_ticket.sh approve "FILENAME" --reviewer "NAME" --notes "NOTES" --live
  ```
- Copies command to clipboard
- Shows workflow summary:
  1. Create GitHub PR with the fix
  2. Run CI/tests automatically
  3. Auto-merge if tests pass (score ≥ 18.0)
  4. Create wiki lesson for future reference
  5. Update violation_store to MERGED
  6. Remove ticket from queue

#### `rejectTicket(filename)`
- Prompts user for reviewer name and feedback (required)
- Generates shell command:
  ```bash
  cd ../agent && ./review_ticket.sh reject "FILENAME" --reviewer "NAME" --notes "FEEDBACK" --live
  ```
- Copies command to clipboard
- Shows workflow summary:
  1. Agent receives your feedback
  2. Ticket moves to revision queue
  3. Lesson created in wiki/lessons/
  4. Agent retries with improved fix
  5. Ticket removed from queue

### 2. Shell Script Wrapper
**File**: [cmu-capstone/agent/review_ticket.sh](cmu-capstone/agent/review_ticket.sh)

**Commands Supported**:

```bash
# Approve a ticket
./review_ticket.sh approve <filename> [--reviewer NAME] [--notes TEXT] [--live]

# Reject a ticket
./review_ticket.sh reject <filename> [--reviewer NAME] [--notes TEXT] [--live]

# Check for merged PRs
./review_ticket.sh check-merged [--live]
```

**Key Features**:
- Colored emoji output for better UX
- Automatic Python CLI invocation with proper arguments
- Dry-run by default (no --live flag)
- Live mode with --live flag to persist changes
- Shows the actual Python command being executed
- Displays results in formatted JSON

### 3. Python CLI (Review Subcommand)
**File**: [cmu-capstone/agent/src/a11y_fixer/cli.py](cmu-capstone/agent/src/a11y_fixer/cli.py)

**Key Functions**:
- `_cmd_review(args)`: Main review handler
- `ReviewQueue.review()`: Processes approve/reject decisions
- Returns JSON with decision details, PR paths, and lesson IDs

**Approval Flow** (`--approve`):
```
ReviewQueue.review()
  ├─ Reconstructs PullRequestPlan from queue item
  ├─ Calls pr_delivery.deliver() → Creates GitHub PR
  ├─ Auto-merges if score ≥ 18.0 and tests pass
  ├─ Calls wiki_pipeline.ingest_lesson() → Creates success lesson
  ├─ Updates .violation_status.json → state = MERGED
  └─ Creates .decision.json recording the approval
```

**Rejection Flow** (`--reject`):
```
ReviewQueue.review()
  ├─ Calls wiki_pipeline.ingest_lesson() → Creates feedback lesson
  ├─ Marks queue item for agent revision
  └─ Creates .decision.json recording the rejection
```

## Usage Workflow

### Step 1: Open Dashboard
```bash
open cmu-capstone/dashboard/hitl_queue/index.html
```

### Step 2: Review Pending Items
- Dashboard loads queue items from `hitl_queue/` directory
- Shows rule name, violation details, and score
- Displays "✓ Approve Fix" and "✗ Reject & Reassign" buttons

### Step 3: Click Button

**For Approval**:
1. Click "✓ Approve Fix"
2. Prompted: "Enter your name (or leave blank for "cli"):"
3. Prompted: "Add optional notes:"
4. Command is generated and copied to clipboard
5. Alert shows the workflow and command

**For Rejection**:
1. Click "✗ Reject & Reassign"
2. Prompted: "Enter your name:"
3. Prompted: "Provide feedback for the agent to improve:" (required)
4. Command is generated and copied to clipboard
5. Alert shows the workflow and feedback

### Step 4: Run Command
```bash
# Navigate to agent directory
cd cmu-capstone/agent

# Paste the copied command
./review_ticket.sh approve "1788332365504442000-image-alt-img.json" --reviewer "john.doe" --notes "Good fix" --live
```

### Step 5: Results
- Shell script shows colored output with status
- Python CLI is invoked with all parameters
- Changes are persisted to GitHub, wiki, and violation_store
- Queue item is removed from HITL queue

## Example Session

### Scenario: Approve a Fix

```bash
# 1. Dashboard shows: "image-alt (img)" with score 22.5

# 2. Click "✓ Approve Fix"
#    Name: john.doe
#    Notes: Perfect fix, matches our standards

# 3. Dashboard shows:
#    ✅ APPROVAL WORKFLOW
#    Ticket: 1788332365504442000-image-alt-img.json
#    Rule: image-alt
#    Score: 22.5
#    WHAT HAPPENS:
#    1. ✅ GitHub PR created with the fix
#    2. 🧪 CI/tests run automatically
#    3. 🔀 Auto-merge if tests pass (score ≥ 18.0)
#    4. 📖 Wiki lesson created for future
#    5. 📝 violation_store updated to MERGED
#    6. 🗑️  Ticket removed from queue
#    COPY & PASTE THIS INTO TERMINAL:
#    cd ../agent && ./review_ticket.sh approve "1788332365504442000-image-alt-img.json" --reviewer "john.doe" --notes "Perfect fix, matches our standards" --live

# 4. Copy command and run in terminal
$ cd ../agent && ./review_ticket.sh approve "1788332365504442000-image-alt-img.json" --reviewer "john.doe" --notes "Perfect fix, matches our standards" --live

# 5. Script output:
#    📋 Processing approve for: 1788332365504442000-image-alt-img.json
#       Reviewer: john.doe
#       Feedback: Perfect fix, matches our standards
#       Mode: --live
#
#    ▶ Running: python -m a11y_fixer.cli review "1788332365504442000-image-alt-img.json" --approve --notes "Perfect fix, matches our standards" --reviewer "john.doe" --live
#
#    {
#      "decision": "approve",
#      "reviewer": "john.doe",
#      "delivered": true,
#      "result": {
#        "diff_path": "evaluation/results/prs/20260902T094659Z-a11y-fixer-test-1788342419.diff",
#        "description_path": "evaluation/results/prs/20260902T094659Z-a11y-fixer-test-1788342419.md",
#        "unified_diff": "--- a/file.txt\n+++ b/file.txt\n@@ -1 +1 @@\n-initial+modified"
#      }
#    }
#
#    ✅ Ticket approved and processed
#       PR created and will be auto-merged if tests pass
#       Lesson will be stored in wiki/lessons/

# 6. Results:
#    ✅ GitHub PR #11 created in [a11y-fixer](https://github.com/mdrmtz/a11y-fixer)
#    ✅ CI tests running...
#    ✅ Auto-merged (score 22.5 ≥ 18.0)
#    ✅ Wiki lesson created: wiki/lessons/20260902T094659Z-image-alt-success.md
#    ✅ .violation_status.json updated with state=MERGED
#    ✅ Queue item removed from hitl_queue/
```

## State Persistence

After running `./review_ticket.sh approve`:

### Files Created/Modified:

1. **GitHub PR** (external system)
   - PR created in mdrmtz/a11y-fixer repository
   - Auto-merged if score ≥ 18.0 and tests pass

2. **Wiki Lesson**
   - File: `wiki/lessons/20260902T094659Z-image-alt-success.md`
   - Contains the fix details for future reference

3. **Violation Status**
   - File: `.violation_status.json`
   - Violation state changed: `NEW` → `PR_OPEN` → `MERGED`
   - Added fields: `pr_id`, `merged_at`, `merged_by`

4. **Approval Decision Record**
   - File: `hitl_queue/1788332365504442000-image-alt-img.decision.json`
   - Records: reviewer name, timestamp, notes, decision

5. **Queue Item Removal**
   - File: `hitl_queue/1788332365504442000-image-alt-img.json`
   - Removed from dashboard after decision is processed

## Testing

### Test 1: Approve Workflow (Dry-Run)
```bash
cd cmu-capstone/agent
./review_ticket.sh approve 1788332367022509000-test--x.json
```

**Expected Output**:
- ✅ Processing message
- ✅ Python CLI command shown
- ✅ Decision JSON returned
- ✅ Success message
- ℹ️ Note: No files changed (dry-run mode)

### Test 2: Approve Workflow (Live)
```bash
cd cmu-capstone/agent
./review_ticket.sh approve 1788332367022509000-test--x.json --reviewer "test_user" --notes "Looks good" --live
```

**Expected Output**:
- ✅ Same as above, but files are actually created
- ✅ PR created in GitHub
- ✅ Wiki lesson created
- ✅ Violation_store updated
- ✅ Queue item removed

### Test 3: Reject Workflow
```bash
cd cmu-capstone/agent
./review_ticket.sh reject 1788241232651310000-image-alt-article-nth-child-2----img.json --reviewer "reviewer_bob" --notes "Does not match codebase style" --live
```

**Expected Output**:
- ✅ Processing message
- ✅ Decision recorded
- ✅ Lesson created with feedback
- ✅ Queue item moved to revision queue

### Test 4: Check Merged
```bash
cd cmu-capstone/agent
./review_ticket.sh check-merged --live
```

**Expected Output**:
- ✅ Queries GitHub for all open PRs
- ✅ Checks merge status
- ✅ Updates violation_store for merged PRs

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Command not found | Script not executable | `chmod +x review_ticket.sh` |
| "ticket file not found" | Wrong filename | Run `python -m a11y_fixer.cli review --list` to see available tickets |
| "was already reviewed" | Ticket already has a decision | Choose a different ticket |
| PR not created | Missing `--live` flag | Run with `--live` to persist changes |
| Changes don't show in GitHub | Missing authentication | Check GitHub token in `GITHUB_TOKEN` env var |

## Integration Points

### Dashboard → Shell Script
- Dashboard generates shell command when user clicks button
- Command is copied to clipboard
- User runs command in terminal

### Shell Script → Python CLI
- Shell script parses arguments
- Invokes: `python -m a11y_fixer.cli review <ticket> [--approve|--reject] [--notes TEXT] [--reviewer NAME] [--live]`
- Shell script displays CLI output with colors and emojis

### Python CLI → Business Logic
- CLI invokes ReviewQueue.review()
- ReviewQueue routes to approve or reject handler
- Handlers call GitHubPRManager, WikiPipeline, ViolationStore

### Business Logic → External Systems
- GitHub PR API: Create, update, auto-merge PRs
- File system: Store lessons in wiki/lessons/
- Violation store: Persist state in .violation_status.json

## Next Steps (Future Enhancements)

1. **Web API Endpoint** — Create Flask backend to handle approvals directly from dashboard
2. **Webhook Support** — Real-time PR merge detection via GitHub webhooks
3. **Automatic Routing** — Auto-approve high-score items without human review
4. **Batch Processing** — Approve/reject multiple tickets at once
5. **Notification System** — Email/Slack notifications on approvals/rejections

## Documentation

- [SHELL_SCRIPT_INTEGRATION.md](SHELL_SCRIPT_INTEGRATION.md) — Complete shell script reference
- [hitl/review_queue.py](src/a11y_fixer/hitl/review_queue.py) — ReviewQueue implementation
- [cli.py](src/a11y_fixer/cli.py) — CLI entrypoint and command handlers
