# Shell Script Integration for HITL Queue Review

This document explains how the dashboard integrates with the CLI using shell scripts to review HITL queue tickets.

## Overview

When you click **"Approve Fix"** or **"Reject & Reassign"** buttons in the HITL queue dashboard, you're presented with a shell command to copy and paste into your terminal. This command:

1. **Approves or rejects** the accessibility fix ticket
2. **Creates a GitHub PR** (for approvals) or **records feedback** (for rejections)
3. **Updates the violation_store** with the new state
4. **Creates wiki lessons** for future reference
5. **Auto-merges PR** if the score is ≥ 18.0 and tests pass

## Quick Start

### 1. Open the Dashboard

```bash
open cmu-capstone/dashboard/hitl_queue/index.html
# or navigate to it in your browser
```

### 2. Click "Approve Fix" or "Reject & Reassign"

- Enter your name (reviewer)
- Enter notes/feedback
- Copy the displayed command

### 3. Run the Command in Terminal

```bash
cd ../agent && ./review_ticket.sh approve "1788332365504442000-image-alt-img.json" --live
```

That's it! The entire workflow runs automatically.

## Command Reference

### Approve a Ticket (Dry-Run)

```bash
cd cmu-capstone/agent
./review_ticket.sh approve "1788332365504442000-image-alt-img.json"
```

**Result:**

- Generates PR with the fix
- Runs tests
- Shows what would happen (but doesn't actually do it)

### Approve a Ticket (Live)

```bash
cd cmu-capstone/agent
./review_ticket.sh approve "1788332365504442000-image-alt-img.json" --reviewer "your_name" --notes "Optional notes" --live
```

**Result:**

- ✅ Creates GitHub PR
- 🧪 Runs CI/tests
- 🔀 Auto-merges if tests pass (score ≥ 18.0)
- 📖 Stores lesson in `wiki/lessons/`
- 📝 Updates `.violation_status.json`

### Reject a Ticket (Dry-Run)

```bash
cd cmu-capstone/agent
./review_ticket.sh reject "1788332365504442000-image-alt-img.json" --notes "Feedback for agent"
```

### Reject a Ticket (Live)

```bash
cd cmu-capstone/agent
./review_ticket.sh reject "1788332365504442000-image-alt-img.json" --reviewer "your_name" --notes "Feedback" --live
```

**Result:**

- ❌ Records rejection with feedback
- 📚 Creates lesson in `wiki/lessons/`
- 🔄 Returns ticket to agent revision queue
- 🚀 Agent learns from feedback and retries

### Check GitHub for Merged PRs (Dry-Run)

```bash
cd cmu-capstone/agent
./review_ticket.sh check-merged
```

### Check GitHub for Merged PRs (Live)

```bash
cd cmu-capstone/agent
./review_ticket.sh check-merged --live
```

**Result:**

- 🔍 Queries GitHub API for all open PRs
- ✅ Marks PRs as MERGED if they're actually merged
- 📝 Updates `.violation_status.json`

## Complete Workflow Example

### Scenario: Approve a High-Score Fix

1. **Dashboard**: Open `cmu-capstone/dashboard/hitl_queue/index.html`
2. **See ticket**: "image-alt (img)" with score 22.5
3. **Click button**: "✓ Approve Fix"
4. **Prompted**:
   - Name: `john.doe`
   - Notes: `Perfect fix, matches our coding standards`
5. **Copy command**:
   ```bash
   cd ../agent && ./review_ticket.sh approve "1788332365504442000-image-alt-img.json" --reviewer "john.doe" --notes "Perfect fix, matches our coding standards" --live
   ```
6. **Run in terminal**: Paste and press Enter
7. **Result**:

   ```
   📋 Processing approve for: 1788332365504442000-image-alt-img.json
      Reviewer: john.doe
      Feedback: Perfect fix, matches our coding standards
      Mode: --live

   ▶ Running: python -m a11y_fixer.cli review "1788332365504442000-image-alt-img.json" --approve ...

   {
     "decision": "approve",
     "reviewer": "john.doe",
     "delivered": true,
     "result": {...}
   }

   ✅ Ticket approved and processed
      PR created and will be auto-merged if tests pass
      Lesson will be stored in wiki/lessons/
   ```

### Scenario: Reject a Low-Score Fix

1. **Dashboard**: Open dashboard
2. **See ticket**: "color-contrast" with score 12.3
3. **Click button**: "✗ Reject & Reassign"
4. **Prompted**:
   - Name: `alice.smith`
   - Feedback: `The color contrast is still not sufficient. WCAG AA requires 4.5:1`
5. **Copy command**:
   ```bash
   cd ../agent && ./review_ticket.sh reject "1788241232651310000-image-alt-article-nth-child-2----img.json" --reviewer "alice.smith" --notes "The color contrast is still not sufficient. WCAG AA requires 4.5:1" --live
   ```
6. **Run in terminal**: Paste and press Enter
7. **Result**:

   ```
   📋 Processing reject for: 1788241232651310000-image-alt-article-nth-child-2----img.json
      Reviewer: alice.smith
      Feedback: The color contrast is still not sufficient. WCAG AA requires 4.5:1
      Mode: --live

   ✅ Ticket rejected and moved to revision queue
      Agent will receive feedback for improvement
   ```

## File Locations

| File                                           | Purpose                                                  |
| ---------------------------------------------- | -------------------------------------------------------- |
| `cmu-capstone/agent/review_ticket.sh`          | Shell wrapper for all review commands                    |
| `cmu-capstone/dashboard/hitl_queue/index.html` | Dashboard UI (generates commands when you click buttons) |
| `cmu-capstone/agent/hitl_queue/`               | Queue items stored as JSON files                         |
| `cmu-capstone/agent/.violation_status.json`    | Persistent violation state                               |
| `cmu-capstone/agent/wiki/lessons/`             | Lessons created from approvals/rejections                |

## Troubleshooting

### Error: "ticket file not found"

The ticket filename might be different. List available tickets:

```bash
cd cmu-capstone/agent
python -m a11y_fixer.cli review --list
```

### Error: "was already reviewed"

The ticket has already been approved/rejected. Choose a different ticket from the list above.

### Command works in shell but doesn't show results

Make sure you're running with `--live` flag to actually persist changes:

```bash
./review_ticket.sh approve <filename> --live
```

Without `--live`, it's a dry-run that shows what would happen but doesn't save anything.

### PR was created but not auto-merged

Auto-merge only happens if:

- Score ≥ 18.0 (you can check the dashboard)
- CI tests pass
- Branch protection rules allow auto-merge

Check the GitHub PR directly to see status.

## Integration Points

### CLI Commands (what the shell script calls)

```bash
# Review approve
python -m a11y_fixer.cli review <filename> --approve [--notes TEXT] [--reviewer NAME] [--live]

# Review reject
python -m a11y_fixer.cli review <filename> --reject [--notes TEXT] [--reviewer NAME] [--live]

# Queue sync with merge detection
python -m a11y_fixer.cli queue-sync --check-merged [--live]
```

### Dashboard Integration

The dashboard (`hitl_queue/index.html`) provides a visual way to:

1. List all pending queue items
2. Show their scores and violation details
3. Generate shell commands when you click buttons
4. Auto-copy commands to clipboard

When you click a button, it:

1. Prompts for your name and feedback
2. Generates the exact shell command needed
3. Copies it to your clipboard
4. Shows instructions to run it

## Architecture

```
Dashboard UI (HTML/JS)
       ↓
    [Click Button]
       ↓
Generate Shell Command
       ↓
Show to User (copy to clipboard)
       ↓
User runs in Terminal
       ↓
shell script (review_ticket.sh)
       ↓
Python CLI (a11y_fixer.cli)
       ↓
ReviewQueue + GitHubPRManager + ViolationStore
       ↓
Updates GitHub + Wiki + .violation_status.json
```

## Future Enhancements

- **Web API endpoint**: Create a Flask backend to handle approvals directly from the dashboard without CLI commands
- **Webhook support**: Real-time PR merge detection via GitHub webhooks
- **Automatic routing**: Auto-approve high-score items without human review
- **Batch processing**: Approve/reject multiple tickets at once
