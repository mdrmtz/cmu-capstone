# CLS Fix-3 Verification Checklist (Technical)

## Quick Verification (5 minutes)

Run these commands in `Hallucinate.io/` to verify if Fix-3 is actually relevant:

```bash
# 1. Does HOMR API even exist in the codebase?
grep -r "HOMR" src/ --include="*.ts" --include="*.js" --include="*.html" || echo "❌ HOMR not found"

# 2. Are there any ad-slot or banner references?
grep -r "top_narrow_banner\|GAM\|ad.slot\|fluid=height" src/ --include="*.ts" --include="*.html" || echo "❌ No ad references"

# 3. Is Angular transfer state being used?
grep -r "TransferState\|ngState\|transferState" src/ --include="*.ts" || echo "❌ No transfer state"

# 4. Any CDN/cache configuration?
grep -r "Cache-Control\|cache.control\|ETag\|max-age" src/ --include="*.ts" --include="*.json" || echo "❌ No cache config"
```

## Interpretation Guide

### If HOMR not found + ad references exist + no transfer state:
**Verdict:** ❌ **Fix-3 is likely INVALID**  
**Reason:** Recommendation targets an API that doesn't exist or isn't used on CLS-sensitive pages

### If HOMR found + ad references exist + transfer state missing:
**Verdict:** ⚠️ **Fix-3 may be SECONDARY**  
**Action:** Verify HOMR is the critical path for ad-slot timing

### If All references exist:
**Verdict:** ✅ **Fix-3 needs MEASUREMENT**  
**Action:** Measure before/after: `ng serve` → run Lighthouse/WebVitals → capture CLS with/without CDN cache headers

---

## What to Report Back to Browse Team

**Template Response:**

```
We've reviewed Fix-3's applicability by:

✅ Code audit (grep for HOMR, ad-slots, transfer state)
   Result: [Insert findings]

✅ Dependency analysis (does HOMR affect ad-slot timing?)
   Result: [Insert finding]

✅ Root cause mapping (which RCA issue does Fix-3 fix?)
   Result: Tangential / Primary / Secondary

📊 Recommendation: [ACCEPT / REVISE / REJECT]

If REJECT: Suggest prioritizing these instead:
   1. Angular transfer state restoration (0.574 CLS confirmed)
   2. Ad-slot state synchronization
   3. [etc]
```

---

## Feedback Loop Setup (for Tooling Team)

### File This Issue

**Title:** `[RCA Feedback] Fix-3 CDN-Cache Recommendation Validity`

**Body:**
```
Recommendation: Fix-3 — Align CDN cache for HOMR API
Status: QUESTIONABLE (Browse team asked for validation)

Code Review Result:
[Paste command output from above]

Verdict: [ACCEPT/REJECT/REVISE]

Suggested Tooling Improvement:
- Ground all external-service recommendations in actual codebase usage (grep confirm)
- Validate against root causes (not just hypothesis)
- For ads/performance: require supporting metric (CLS measurement before/after)

Related PR: [Link to RCA PR]
```

---

## If You Need Deeper Investigation

### Measure CLS Impact (Optional, if Fix-3 seems plausible)

```bash
# Start dev server
npm start &
DEV_PID=$!

# Wait for server
sleep 5

# Run Lighthouse audit
npx lighthouse http://localhost:4200 --chrome-flags="--headless" --output=json --output-path=/tmp/baseline.json

# Note baseline CLS score
jq '.categories.performance.score' /tmp/baseline.json

# [Now apply Fix-3 manually: add cache headers to HOMR responses]

# Re-run audit after fix
npx lighthouse http://localhost:4200 --chrome-flags="--headless" --output=json --output-path=/tmp/after-fix.json

# Compare
echo "Before: $(jq '.audits.cumulative-layout-shift.displayValue' /tmp/baseline.json)"
echo "After:  $(jq '.audits.cumulative-layout-shift.displayValue' /tmp/after-fix.json)"

kill $DEV_PID
```

**Result Interpretation:**
- If CLS improves > 0.05: Fix-3 is valid
- If CLS unchanged: Fix-3 is not the critical path
- If CLS worsens: Fix-3 may cause regression

---

## Keep It Simple

**When in doubt, respond with:**

> "We've reviewed Fix-3 against the confirmed root causes in the RCA. Our code analysis shows [FINDING]. We recommend [ACTION] and would appreciate guidance from your measurement team on the actual impact of CDN cache alignment on ad-slot timing."

This shows:
✅ You did the work  
✅ You're grounding feedback in evidence  
✅ You're open to their expertise  
✅ You care about measurement, not guessing
