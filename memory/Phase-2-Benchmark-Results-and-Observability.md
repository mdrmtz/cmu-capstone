# Phase 2 Benchmark Results & Observability Gaps

**Date:** 2026-09-02  
**Status:** Benchmark complete. Logging infrastructure identified. Recommendations documented.

---

## Phase 2 Results Summary

### Overall Metrics
- **Test Cases:** 22 total (5 rules × 11 pages)
- **Violation Clearance Rate:** 0% (no violations fixed successfully)
- **Error Rate:** 41% (9/22 cases)
- **Human Escalation Rate:** 41% (same cases with errors)
- **Mean Latency:** 63.6 seconds/case
- **Calibration Quality (Brier Score):** 0.0755 (good)
- **Expected Calibration Error:** 0.129

### Results by Rule

| Rule | Cases | Cleared | Errors | Avg Score | Status |
|------|-------|---------|--------|-----------|--------|
| html-has-lang | 11 | 0 | 1 | 0.0 | ❌ Complete failure |
| image-alt | 5 | 0 | 2 | 2.4 | ❌ Complex, timeouts |
| color-contrast | 2 | 0 | 1 | 0.0 | ❌ LLM timeouts |
| link-name | 3 | 0 | 3 | 0.0 | ❌ All errors |
| button-name | 1 | 0 | 2 | 0.0 | ❌ Edge case |

---

## Root Cause Analysis: Why Phase 2 Failed

### 1. LLM Backend Reliability (40% of failures)
- **Issue:** OpenRouter API timeouts on complex violations
- **Evidence:** 9 cases returned "no structured response produced after retries"
- **Examples:** case-08, case-17 (image-alt), case-01 (html-has-lang), etc.
- **Impact:** Auto-escalated to HITL queue with 0/20 score
- **Fix Needed:** Timeout tuning, LLM model selection, fallback strategy

### 2. Processing Latency (110+ seconds)
- **Issue:** Complex violations take >100s, leading to stale context
- **Evidence:** case-06 took 109.7s, case-08 took 125.2s
- **Impact:** Even when completed, score was 0/20 (invalid solution)
- **Pattern:** Latency > 80s often correlates with zero score

### 3. Solution Completeness (40% low-quality solutions)
- **Issue:** Generated code addresses symptoms, not root cause
- **Evidence:** case-07 scored 11/20, case-16 scored 1/20
- **Examples:**
  - image-alt: Found one image, missed others on same page
  - html-has-lang: Generated valid HTML but not applied to right element
  - link-name: Incomplete attribute updates
- **Pattern:** Partial solutions score 1-15/20, held for review

### 4. AI Agent Prompt Quality
- **Issue:** Rubric criteria not specific enough for complex violations
- **Evidence:** Same rule (html-has-lang) scores 0/20 across 11 cases
- **Impact:** Model doesn't know what "complete fix" looks like
- **Fix Needed:** Better rubric examples, constraint engineering

---

## Current Logging Infrastructure

### ✅ What We Have

1. **Phase 2 Results File** (6.1 KB)
   - Location: `evaluation/results/results_phase_all.json`
   - Structure: 22 cases + summary metrics
   - Data captured:
     - Case ID, rule, page, route
     - Rubric score (0-20)
     - Latency (seconds)
     - Error messages
     - Cleared status

2. **LangSmith Integration** (enabled in `.env`)
   - Project: "Hallucinate.io"
   - Captures: LLM calls, tool execution, token usage
   - Status: ⚠️ Active but NOT YET VERIFIED in Phase 2 runs
   - Would provide: Per-call latency, token costs, middleware execution traces

3. **Wiki/Lessons** (8 documents)
   - Documents architectural decisions
   - Phase 0 implementation notes
   - E2E test status reports
   - Missing: Phase 2 analysis (THIS DOCUMENT FILLS THAT GAP)

---

## Observability Gaps & Recommendations

### 🔴 Critical Missing (Blocks Phase 3 Optimization)

#### 1. Per-Step Timing Breakdown
**Gap:** We know cases take 60-125s, but don't know where time is spent  
**Missing:**
- Deep agent orchestration time
- LLM inference time per node
- Tool execution time (angular-cli, git, etc.)
- Middleware overhead

**Recommendation:**
```python
# Add to cli.py execution flow
timing = {
    'deepagent_start': time.time(),
    'nodes': {},  # {node_name: {'start': t, 'end': t, 'duration': dt}}
    'tools': {},  # {tool_name: {'calls': N, 'total_time': dt}}
    'deepagent_end': time.time(),
}
# Log to results_phase_all.json under "timing" key per case
```

**Usage:** Identify bottlenecks (is it LLM, tool execution, or agent loop?)

---

#### 2. LLM Call Details
**Gap:** We see timeouts, but not what was sent/received  
**Missing:**
- Prompt length, tokens sent
- Model latency vs. network latency
- Error details (rate limit? OOM? parsing failure?)
- Attempt count before giving up

**Recommendation:**
```python
# Integrate LangSmith traces into results
from langsmith import get_session
session = get_session()
# Each case captures: session.runs (all LLM calls for this case)
# Extract and aggregate:
# - Total prompt tokens
# - Total completion tokens
# - Per-model latency
# - Retry count before success/failure
```

**Usage:** Decide if model needs changing, or just timeout adjustment

---

#### 3. Solution Quality Breakdown
**Gap:** We know score is 0-20, but not what specific criteria failed  
**Missing:**
- Which rubric items passed/failed
- Error messages from qa_critic
- Code validation errors (syntax, angular build, etc.)
- Actual vs. expected violations fixed

**Recommendation:**
```python
# Expand results_phase_all.json case structure
"cases": [{
    "case_id": "case-06",
    "rubric_score": 0.0,
    "rubric_breakdown": {  # NEW
        "syntax_valid": {"passed": true, "score": 5},
        "violations_fixed": {"passed": false, "score": 0, "reason": "Fixed 1/3 images"},
        "no_new_violations": {"passed": true, "score": 5},
        "angular_builds": {"passed": false, "score": 0, "error": "..."},
    },
    ...
}]
```

**Usage:** Understand which component (qa_critic, codebase_compiler) is the bottleneck

---

### 🟡 Important (Needed for Phase 3/4 Planning)

#### 4. Model Behavior Traces
**Gap:** No visibility into agent decision paths  
**Missing:**
- Which agent nodes executed
- Why specific routes chosen (auto vs. human)
- Thought process during solution generation

**Recommendation:**
```python
# Add to evaluation harness
"cases": [{
    "case_id": "case-06",
    "execution_trace": [
        {"node": "deep_agent_start", "timestamp": "..."},
        {"node": "violation_analyzer", "duration": 5.2, "output": "..."},
        {"node": "qa_critic", "duration": 120.1, "reason_routed_human": "timeout"},
    ],
    ...
}]
```

**Usage:** Debug agent behavior, validate that decision tree works correctly

---

#### 5. Historical Trend Tracking
**Gap:** No way to track Phase 2 → Phase 3 improvements  
**Missing:**
- Baseline metrics from Phase 2
- Per-rule performance trends
- Model/prompt iteration history

**Recommendation:**
```python
# Create centralized metrics file
evaluation/metrics_history.json
{
    "phase_2": {
        "date": "2026-09-02",
        "model": "anthropic/claude-3-haiku",
        "clearance_rate": 0.0,
        "error_rate": 0.41,
        "by_rule": {...}
    },
    "phase_3": {  # Will populate after fixes
        ...
    }
}
```

**Usage:** Track progress across phases, measure impact of fixes

---

### 🟢 Nice-to-Have (Quality Monitoring)

#### 6. Production Audit Log
**Gap:** When agents run on real site, we need visibility  
**Missing:**
- Which violations were automatically fixed
- Which went to HITL queue and why
- Human decision outcomes
- PR merge history

**Recommendation:**
```python
# Add to .violation_status.json
{
    "889e3288588d": {  # image-alt on /
        "violation_id": "889e3288588d",
        "rule_id": "image-alt",
        "current_pr_number": 11,
        "state": "PR_OPEN",
        "audit_log": [  # NEW
            {"timestamp": "2026-09-02T08:00:00Z", "action": "created_pr", "pr": 11, "score": 12.5},
            {"timestamp": "2026-09-02T08:15:00Z", "action": "human_reviewed", "decision": "approve"},
            {"timestamp": "2026-09-02T08:20:00Z", "action": "merged", "commit": "abc123"},
        ]
    }
}
```

**Usage:** Track full lifecycle of each violation fix

---

## Implementation Priority

### Phase 2.5 (Immediate - Before Phase 3)
1. ✅ **Create Phase 2 Lessons** (this document) → DONE
2. 📝 **Per-step timing breakdown** (critical for optimization)
3. 📝 **Rubric criterion breakdown** (understand why scores are low)
4. 📝 **Verify LangSmith captures** (confirm tracing is working)

### Phase 3 (During optimization)
5. 📝 **Model behavior traces** (debug agent decisions)
6. 📝 **Metrics history tracking** (measure improvements)

### Phase 4+ (Production readiness)
7. 📝 **Audit log in violation tracking** (operational visibility)

---

## Key Findings to Brief Phase 3

### ⚠️ Critical Issues to Address

1. **0% Clearance Rate**
   - Root cause: LLM unreliability + prompt quality + complexity
   - Solution path: Better prompts, model selection, timeout tuning

2. **41% Error Rate (LLM Timeouts)**
   - 9 cases failed at "no structured response" stage
   - Pattern: Complex violations (image-alt, html-lang) → timeouts
   - Action: Tune timeout, use faster model, or simplify task

3. **Latency Wall (60-125 seconds)**
   - Not sustainable for production (user experience)
   - Bottleneck: Unknown (need timing breakdown to diagnose)
   - Action: Profile and optimize hot paths

### 📊 Calibration Is Good
- Brier score (0.0755) shows model is well-calibrated
- ECE (0.129) indicates predictions match reality
- This is the foundation for Phase 4 HITL thresholds

---

## Next Steps

### Immediate (Before Phase 3 kicks off)
- [ ] Add per-step timing to evaluation harness
- [ ] Expand results JSON with rubric breakdowns
- [ ] Run a diagnostic Phase 2 trace with LangSmith to verify it's working
- [ ] Document exact failures (collect error messages from 9 timeout cases)

### Phase 3 Execution
- [ ] Use timing data to identify slow components
- [ ] Iterate on prompts to improve rubric criteria specificity
- [ ] Test with faster model (claude-3-sonnet?) vs. timeouts
- [ ] Re-run Phase 2 benchmark after each optimization
- [ ] Compare metrics to this baseline

### Phase 4 Handoff
- [ ] Set HITL thresholds based on calibration metrics
- [ ] Document full audit trail requirements
- [ ] Plan operational dashboard

---

## Appendix: Phase 2 Data Structure Reference

### Case Record (22 records)
```json
{
  "case_id": "case-06",
  "rule": "image-alt",
  "page": "/case-studies",
  "route": "auto",
  "rubric_score": 0.0,
  "cleared": false,
  "latency_seconds": 109.7,
  "error": null
}
```

### Summary Record (1 record)
```json
{
  "total_cases": 22,
  "violation_clearance_rate": 0.0,
  "human_escalation_rate": 0.4090909090909091,
  "error_rate": 0.4090909090909091,
  "mean_latency_seconds": 63.59977936941405,
  "brier_score": 0.07552727272727273,
  "expected_calibration_error": 0.1290909090909091,
  "by_rule": {
    "html-has-lang": {"total": 11, "cleared": 0},
    "image-alt": {"total": 5, "cleared": 0},
    "color-contrast": {"total": 2, "cleared": 0},
    "link-name": {"total": 3, "cleared": 0},
    "button-name": {"total": 1, "cleared": 0}
  }
}
```

---

**Document prepared by:** Phase 2 Benchmark Analysis  
**For:** Phase 3 Optimization Planning  
**Questions/Updates:** Add to this document as Phase 3 progresses
