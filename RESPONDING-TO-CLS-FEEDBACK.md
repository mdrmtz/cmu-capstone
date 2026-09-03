# Response Framework: CLS Recommendation Feedback (Fix-3 — CDN Cache HOMR API)

## Context
The browse team raised questions about **Fix-3's validity**: "Is there a good way to provide that feedback so that the tooling can be updated?"

This document provides a step-by-step response strategy and feedback collection mechanism.

---

## Step 1: Verify the Recommendation Scope

### Questions to Ask Before Responding

1. **Does Fix-3 target the ROOT CAUSE or a SYMPTOM?**
   - **Root causes identified in the RCA:**
     - Missing Angular transfer state (`ngState` absent)
     - Transient jitter pattern (16px shifts)
     - Persistent expansion pattern (145px+ banner expansion)
   - **Fix-3 claim:** Aligning CDN cache for HOMR API
   - **Gap to validate:** Does HOMR API caching directly address any of the three root causes above?

2. **Is the recommendation DEPENDENT on the actual root cause being CONFIRMED?**
   - If yes, cite the exact RCA finding(s) it depends on
   - If no, it may be a **false positive** or **low-confidence suggestion**

3. **What is the impact scope?**
   - Does it affect ALL pages (`/f/sale`, `/f/big-boys-clothes`, `/f/hybrid-golf-clubs`)?
   - Or only specific ones (e.g., desktop-only due to ad slot behavior)?

---

## Step 2: Code-Based Verification (Before Responding)

### Review Current Implementation

Check these files to understand the actual state:

```bash
# 1. Search for HOMR API references
grep -r "HOMR" Hallucinate.io/src/ --include="*.ts" --include="*.html"

# 2. Check ad-slot initialization
grep -r "top_narrow_banner\|GAM\|ad-slot" Hallucinate.io/src/ --include="*.ts" --include="*.html"

# 3. Verify Angular transfer state setup
grep -r "ngState\|TransferState\|transferState" Hallucinate.io/src/ --include="*.ts"

# 4. Check CDN cache headers (if applicable to API responses)
grep -r "Cache-Control\|cache-control\|ETag" Hallucinate.io/src/ --include="*.ts"
```

### Expected Findings to Report Back

| Finding | Severity | Response |
|---------|----------|----------|
| HOMR API calls are unrelated to the three root causes | **HIGH** | Fix-3 is likely a false positive; recommend dismissing |
| HOMR API responses lack cache headers | **MEDIUM** | Fix-3 may help but isn't the PRIMARY fix; secondary recommendation |
| CDN caching affects ad-slot timing indirectly | **LOW** | Context-dependent; depends on actual latency measurements |
| HOMR API is not called on any test page | **CRITICAL** | Fix-3 targets an unrelated system; should be removed |

---

## Step 3: Structured Response to the Browse Team

### Response Template

**Subject:** Re: CLS Recommendations — Fix-3 Validity Check

Dear [Browse Team],

Thank you for reviewing Fix-3. We've investigated the recommendation and here's what we found:

#### Fix-3 Analysis: "Align CDN cache for HOMR API"

**RCA Root Causes (confirmed via live Playwright sampling):**
- Root cause #1: Missing Angular transfer state (0.574 CLS on `/f/hybrid-golf-clubs`)
- Root cause #2: Ad-slot transient jitter (+16px / −16px, desktop only)
- Root cause #3: Banner persistent expansion (+145px mobile, +134px desktop)

**Fix-3 Mapping to Root Causes:**
- ✅ **Related to:** Root cause #3 (if HOMR API latency affects banner timing)
- ❌ **Related to:** Root causes #1, #2 (no direct connection)

**Code-based Verification:**
[Insert findings from Step 2 above]

#### Our Recommendation:

**Option A** (if HOMR is not the primary path): 
> Fix-3 should be reprioritized or removed. The primary fixes should target Angular transfer state and ad-slot state synchronization instead.

**Option B** (if HOMR caching is a real lever):
> Fix-3 is valid but secondary. Recommend: (1) add cache headers to HOMR responses, (2) measure before/after CLS impact independently.

---

## Step 4: Feedback Channel for Tooling Updates

### How to Report Feedback So Tooling Can Improve

**Option 1: Direct Integration (Recommended)**

Create a feedback issue with **structured metadata** for the recommendation engine:

```json
{
  "feedback_type": "invalid_recommendation",
  "recommendation_id": "Fix-3",
  "recommendation_text": "Align CDN cache for HOMR API",
  "root_cause_addressed": "persistence_expansion",
  "evidence": {
    "root_cause_confirmed": false,
    "code_review_results": "No HOMR API calls detected on test pages",
    "metric_impact": "No measured CLS improvement from CDN cache alignment",
    "confidence_score": 0.15
  },
  "action_requested": "remove_recommendation",
  "context": {
    "page": "/f/hybrid-golf-clubs",
    "rule": "CLS",
    "team": "Browse Team"
  }
}
```

**Option 2: Logging Mechanism (For ML Feedback)**

If the RCA tooling uses LLM-generated recommendations, log the mismatch:

```python
# Example: Log to a feedback file for fine-tuning
feedback_log = {
    "timestamp": "2026-09-02",
    "recommendation_id": "Fix-3",
    "human_verdict": "INVALID",
    "human_rationale": "HOMR API caching unrelated to confirmed root causes",
    "should_retrain": True,
    "suggested_system_prompt_update": "Always ground recommendations in confirmed root causes; validate via code review before suggesting external service changes"
}
```

**Option 3: Public Issue (GitHub/Jira)**

Post a structured issue with:

1. **Title:** `[RCA-Feedback] Fix-3 CLS Recommendation Validity Question`
2. **Accepted/Rejected:** Rejected
3. **Reason:** [Specific reason from Step 2 above]
4. **Supporting Evidence:** [Code snippets, metrics, queries]
5. **Suggested Change:** [How the tooling should be updated]

---

## Step 5: Iterate on Feedback with Tooling Team

### Key Questions to Discuss

1. **Measurement Gap:** Were the recommendations derived from:
   - ✅ Actual performance metrics (resource timing, CLS snapshots)?
   - ❌ Hypothetical analysis or log inspection?
   
2. **Validation Gap:** Should Fix-3 have included:
   - ✅ Code review confirming HOMR API is actually called?
   - ✅ Measurement showing CDN cache misses for HOMR?
   
3. **Confidence Gap:** What confidence threshold should trigger:
   - Removal of the recommendation entirely?
   - Downgrade to "consider if..." (low confidence)?

### Proposed Feedback Loop for Tooling

```
RCA Detection (automated)
    ↓
Recommendation Generation (LLM or rule-based)
    ↓
Human Review & Code Verification (this step)
    ↓
Feedback Logged: ACCEPT / REJECT / REVISE
    ↓
Tooling Updated:
    - False positives reduced
    - Grounding in code review added
    - Confidence scoring improved
```

---

## Step 6: One-Pager for Team Communication

### Quick Summary (If Time-Constrained)

| Aspect | Status | Action |
|--------|--------|--------|
| **Fix-3 Validity** | ❌ **QUESTIONABLE** | Recommend rejection or significant revision |
| **Root Cause Link** | Weak (tangential to actual causes) | Review code to confirm HOMR role |
| **Confidence** | Low (hypothesis, not measured) | Request metrics/evidence before implementation |
| **Feedback Path** | GitHub Issue + Structured Log | File issue + update tooling logic |

---

## Appendix: Email Template for Browse Team

---

**Subject:** CLS RCA Fix-3 — Feedback & Next Steps

Hi Browse Team,

Thanks for the careful review. You're right to question Fix-3.

**TL;DR:** We're **revising Fix-3** to either (a) remove it as unrelated, or (b) reframe it as a secondary optimization dependent on measuring actual HOMR API latency impact.

**What We Did:**
1. Reviewed the three confirmed CLS root causes from the RCA
2. Traced Fix-3 (CDN cache for HOMR API) against each root cause
3. Found: HOMR is tangential, not the primary lever
4. **Conclusion:** Fix-3 should NOT be a top-3 priority recommendation

**Next Steps:**
- We're logging this as "recommendation rejected" in our feedback system
- The recommendation engine will be updated to (1) validate external service recommendations against actual code usage, and (2) ground suggestions in measured metrics, not hypothetical analysis
- Would you like us to propose an alternative Fix-3 that IS evidence-based?

Looking forward to your thoughts.

---

## Recommended Actions (Priority Order)

1. ✅ **Verify** (Step 2): Run grep searches to confirm/refute HOMR API usage
2. ✅ **Respond** (Step 3): Reply to the browse team with findings + Option A or B
3. ✅ **Log** (Step 4): File feedback in your tooling's feedback channel
4. ✅ **Iterate** (Step 5): Discuss threshold updates with the RCA/tooling team
5. ✅ **Update** (Step 6): Ensure tooling learns from this false positive
