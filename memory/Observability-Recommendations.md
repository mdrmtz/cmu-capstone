# Observability Recommendations for System Improvement

**Date:** 2026-09-02  
**Audience:** Phase 3 optimization planning

---

## Current State: What We Have

| Component | Status | Location | Coverage |
|-----------|--------|----------|----------|
| **Phase 2 Results** | ✅ Complete | `evaluation/results/results_phase_all.json` | 22 test cases, summary metrics |
| **LangSmith Traces** | ⚠️ Enabled (unverified) | LangSmith project "Hallucinate.io" | LLM calls, middleware, tokens (if working) |
| **Wiki/Lessons** | ✅ 8 docs + Phase 2 | `wiki/lessons/` | Architectural decisions, Phase 2 analysis |
| **Application Logs** | ❌ Minimal | `step5_output.log` (32 bytes) | No structured logging |
| **Violation Tracking** | ✅ Complete | `.violation_status.json` | Violation state, PRs, scores |

**Key Finding:** We have end-to-end results data but **no visibility into what caused low scores**.

---

## What We Need to Add: 3-Tier Stack

### Tier 1: Scoring Breakdown (CRITICAL FOR PHASE 3)

**Problem:** Scores are 0-20, but we don't know which rubric criteria failed.

**Solution:** Expand each case record with criterion-level details.

```python
# In evaluation/results/results_phase_all.json, change from:
{
  "case_id": "case-06",
  "rubric_score": 0.0,
  "latency_seconds": 109.7,
  "error": null
}

# To:
{
  "case_id": "case-06",
  "rubric_score": 0.0,
  "latency_seconds": 109.7,
  "error": null,
  "scoring_details": {  # ← NEW
    "criteria_evaluated": [
      {
        "name": "HTML Syntax Valid",
        "max_points": 5,
        "awarded": 0,
        "passed": false,
        "reason": "Generated code has unclosed div tag"
      },
      {
        "name": "Violations Fixed",
        "max_points": 10,
        "awarded": 0,
        "passed": false,
        "reason": "Fixed 1/3 missing images"
      },
      {
        "name": "No Regressions",
        "max_points": 3,
        "awarded": 0,
        "passed": false,
        "reason": "Build fails: missing dependency"
      },
      {
        "name": "Code Quality",
        "max_points": 2,
        "awarded": 0,
        "passed": false,
        "reason": "Formatting issues"
      }
    ]
  }
}
```

**Where to add this:**
- File: `src/a11y_fixer/adapters/qa_critic.py`
- Change: Return detailed breakdown from `score_solution()` instead of just a float
- Benefit: Understand whether bottleneck is code quality, violations fixed, or build issues

**Impact:** Can prioritize fixes (e.g., "focus on violations fixed" vs. "improve syntax checking")

---

### Tier 2: Latency Profiling (HIGH FOR OPTIMIZATION)

**Problem:** Cases take 60-125 seconds. Where is the time spent?

**Solution:** Instrument agent and tool execution.

```python
# In evaluation/run_eval.py, track:
timing_profile = {
    "total_time": 109.7,
    "phases": [
        {"phase": "violation_analysis", "duration": 5.2},
        {"phase": "generate_solution", "duration": 72.3},  ← LLM inference?
        {"phase": "validate_solution", "duration": 25.1},  ← Build time?
        {"phase": "score_solution", "duration": 7.1},
    ],
    "tool_calls": {
        "angular_cli_build": {"count": 3, "total_time": 20.5},
        "git_apply": {"count": 1, "total_time": 0.3},
        "llm_inference": {"count": 5, "total_time": 72.3},
    },
    "slow_operations": [
        {"tool": "llm_inference", "latency": 45.2, "attempt": 1},
        {"tool": "angular_cli_build", "latency": 8.7, "attempt": 1},
    ]
}
# Store in results_phase_all.json under timing_profile per case
```

**Where to add this:**
- File: `src/a11y_fixer/cli.py` (wrap each major step)
- Tool: Use Python's `time.perf_counter()` for precision
- Benefit: Identify if bottleneck is LLM (slow), build system (slow), or agent loop overhead

**Impact:** Know where to optimize (e.g., cache builds, faster model, batch LLM calls)

---

### Tier 3: Audit Trail (IMPORTANT FOR PHASE 4)

**Problem:** Can't track lifecycle of violations or human decisions.

**Solution:** Add structured logging to violation tracking.

```python
# In .violation_status.json, expand:
{
  "889e3288588d": {
    "violation_id": "889e3288588d",
    "rule_id": "image-alt",
    "selector": "img.product-image",
    "state": "PR_OPEN",
    "current_pr_number": 11,
    "current_score": 12.5,
    
    "events": [  # ← NEW
      {
        "timestamp": "2026-09-02T08:00:00Z",
        "event": "generated",
        "score": 12.5,
        "reason": "Route: auto (score passed margin threshold)"
      },
      {
        "timestamp": "2026-09-02T08:10:00Z",
        "event": "pr_created",
        "pr_number": 11,
        "commit": "abc123def456"
      },
      {
        "timestamp": "2026-09-02T09:00:00Z",
        "event": "human_review",
        "decision": "needs_revision",
        "feedback": "Need to add aria-label on hover state"
      },
      {
        "timestamp": "2026-09-02T10:00:00Z",
        "event": "regenerated",
        "new_score": 18.2,
        "reason": "Human feedback incorporated"
      }
    ]
  }
}
```

**Where to add this:**
- File: `src/a11y_fixer/domain/violations.py` (add `events` field to ViolationStatus)
- File: `src/a11y_fixer/cli.py` (log each state change)
- Benefit: Full audit trail for compliance and debugging

**Impact:** Trace why decisions were made, measure human turnaround time, track improvement iterations

---

## Quick Implementation Checklist

### Before Phase 3 Runs
- [ ] Add `scoring_details` to qa_critic.py
- [ ] Update results_phase_all.json schema
- [ ] Add timing instrumentation to cli.py
- [ ] Verify LangSmith is capturing traces (manual check)

### During Phase 3
- [ ] Run with new instrumentation enabled
- [ ] Collect timing data for bottleneck analysis
- [ ] Compare rubric breakdown across iterations

### Before Phase 4
- [ ] Add events log to ViolationStatus dataclass
- [ ] Implement state change logging in cli.py
- [ ] Create audit dashboard query

---

## Why Each Layer Matters

| Layer | Answers | Use Case |
|-------|---------|----------|
| **Scoring Breakdown** | "Why did this case score 0?" | Optimize rubric criteria, debug qa_critic |
| **Latency Profiling** | "Where are we spending time?" | Reduce processing latency, improve UX |
| **Audit Trail** | "What happened to this violation?" | Track decisions, measure progress, support humans |

---

## Connection to Phase 2 Root Causes

**Phase 2 had 0% clearance. Which observability would have helped?**

| Finding | Root Cause | Observability Needed |
|---------|-----------|----------------------|
| 9/22 LLM timeouts | OpenRouter API slow | ✅ Per-call latency from LangSmith |
| 5/22 Partial solutions (score 1-15) | Incomplete rubric criteria | ✅ Scoring breakdown (which criteria failed?) |
| 4/22 Invalid solutions (syntax errors) | Code quality issues | ✅ Scoring breakdown (error details) |

**With Tier 1 & 2 in place, Phase 3 can:**
1. Know exactly which rubric criteria are the bottleneck
2. Profile latency to decide between faster model, better prompts, or architectural changes
3. Measure impact of each optimization systematically

---

## Recommendation: Start with Tier 1

**Do this first:** Add `scoring_details` to qa_critic.py

Why?
- Takes ~2 hours to implement
- Immediately explains why Phase 2 scored 0 on 14 cases
- Unblocks decision on what to optimize next

**Then add Tier 2** as you iterate on solutions (to measure latency impact)

**Then add Tier 3** when Phase 4 human review begins (to track decisions)

---

**Next action:** Start Phase 3 optimization with Tier 1 instrumentation enabled.
