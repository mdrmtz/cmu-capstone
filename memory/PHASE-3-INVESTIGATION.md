# Phase 3 Investigation Guide: Zero Clearance Root Cause Analysis

**Context:** Phase 3 added code validation infrastructure, expected ≥40% clearance, achieved 0%.  
**Goal:** Identify and fix the root cause of validation failures.  
**Effort:** 4-7 hours to diagnosis + fix  

---

## 🔍 Investigation Approach

### Phase 3A: Validator Impact Isolation (60-90 min)

**Goal:** Quantify whether the validator is helping or hurting.

**Hypothesis:** Maybe the validator is too strict and prevents valid fixes.

#### Step 1: Disable Validator (10 min)

Edit `src/a11y_fixer/agents/codebase_compiler/compiler.py`:

```python
# Around line ~90 in the codebase_compiler agent builder
# COMMENT OUT the validate_code tool registration:

# tools = [
#     ToolSchema(name="validate_code", ...),  # ← DISABLE TEMPORARILY
#     ToolSchema(name="check_build", ...),
# ]

# Keep only:
tools = [
    ToolSchema(name="check_build", ...),
    ToolSchema(name="run_tests", ...),
    ToolSchema(name="examine_file", ...),
]
```

#### Step 2: Run Subset Test (30-45 min)

```bash
cd cmu-capstone/agent
python -m evaluation.run_eval --phase f1 --no-live
```

**Capture metrics:**
- Clearance rate (0% or higher?)
- Error rate (40.9% or different?)
- Mean latency
- Which cases cleared vs didn't

#### Step 3: Compare Results (15-30 min)

Create comparison script:

```bash
python3 << 'EOF'
import json
from pathlib import Path

# Load Phase 3.1a results (validator ON)
with open("evaluation/results/results_phase_f1.json") as f:
    with_validator = json.load(f)

# If you just ran without validator, it would have created a new file
# For now, conceptually show what comparison looks like:

print("VALIDATOR IMPACT COMPARISON")
print(f"With validator:    {with_validator['summary']['violation_clearance_rate']:.1%} cleared")
print(f"Expected without:  Should be ≥10% if validator is hurting")
EOF
```

**Decision logic:**
- If clearance ↑ without validator → **Validator is too strict** (Phase 3A diagnosis: LOOSEN)
- If clearance ↓ or same → **Validator not the problem** (proceed to 3B)
- If clearance ↑↑ significantly → **Validator blocking valid fixes** (Phase 3A diagnosis: REVISE)

---

### Phase 3B: Agent Response Quality (120-180 min)

**Goal:** Understand what agent is actually doing when validator runs.

**Hypothesis:** Agent sees validator feedback but can't generate working fixes.

#### Step 1: Pick One Failing Case (15 min)

From Phase 3.1a results, pick a case that:
- Has error status OR cleared=false
- Validator likely ran (not timeout)
- Specific rule (e.g., image-alt, not generic html-has-lang)

Example: **case-16-image-alt-button-aria-label** 

Get the case details:
```python
import json
with open("evaluation/results/results_phase_f1.json") as f:
    cases = json.load(f)["cases"]
    target = [c for c in cases if c["case_id"] == "case-16"][0]
    print(json.dumps(target, indent=2))
```

#### Step 2: Enable Debug Logging (30 min)

Edit `src/a11y_fixer/agents/codebase_compiler/compiler.py`:

Add logging to capture every step:

```python
import logging
logger = logging.getLogger("codebase_compiler.debug")
handler = logging.FileHandler("/tmp/phase3_debug.log")
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)

# In the tool definitions, wrap validate_code:
async def validate_code_with_debug(file_path: str):
    logger.debug(f"[VALIDATE] Input: {file_path}")
    result = validate_code(file_path)  # Original function
    logger.debug(f"[VALIDATE] Output: {result}")
    return result
```

#### Step 3: Run Single Case (45-60 min)

```bash
cd cmu-capstone/agent

# Create a minimal run for just case-16:
python3 << 'EOF'
import json
from pathlib import Path
from a11y_fixer.adapters.audit_runner import AxeAuditRunner
from a11y_fixer.adapters.repo_source import resolve_repo_source

# Load case-16 from fixture
config = {
    "case_id": "case-16-image-alt-button-aria-label",
    "rule": "image-alt",
    "selector": "button.sign-in",
    "violation": "...",
}

# This would run the agent on just this case with debug enabled
# (Detailed implementation depends on evaluation harness structure)
EOF
```

#### Step 4: Analyze Debug Log (30 min)

Look for:

1. **Did validator run?**
   ```log
   [VALIDATE] Input: src/app/components/button.component.ts
   [VALIDATE] Output: {"has_errors": true, "errors": [...]}
   ```

2. **What errors did it find?**
   ```log
   - Missing import: @angular/core.OnInit
   - Undefined variable: signInHandler
   ```

3. **Did agent respond to feedback?**
   ```log
   [AGENT] Suggested fix: import { OnInit } from '@angular/core';
   [BUILD] Output: Build succeeded!
   ```

4. **Did qa_critic score the fix?**
   ```log
   [QA_CRITIC] Original violation: image alt missing
   [QA_CRITIC] After fix: image still has no alt
   [QA_CRITIC] Score: 5/20 (fix didn't address violation)
   ```

---

### Phase 3C: Specific Issue Diagnosis (Varies)

Once you find the issue in the debug log, use the appropriate deep-dive:

#### If Issue: Validator Too Strict

**Symptom:** Validator rejects valid fixes; agent gives up

**Investigation:**
```python
# In CodeValidator class, check detection rules:
# - Is it matching false positives?
# - Are suggestions actually correct?

# Test validator in isolation:
from a11y_fixer.adapters.code_validator import CodeValidator

v = CodeValidator()
result = v.validate_typescript_file("src/app/components/button.component.ts")
print(f"Errors: {result.errors}")
print(f"Suggestions: {result.suggestions}")

# Are the suggestions actually needed?
# Is the file actually building without these fixes?
```

**Fix strategy:**
- Add exception cases to validator
- Reduce strictness threshold
- Whitelist certain patterns

#### If Issue: Agent Ignores Validator Feedback

**Symptom:** Validator finds errors, agent doesn't fix them, claims success

**Investigation:**
```python
# Check system prompt in codebase_compiler:
# Does it mention validator feedback?

# Check agent's response format:
# Is it acknowledging the validator errors?

# Check retry logic:
# Does agent get a second attempt after validator fails?
```

**Fix strategy:**
- Update system prompt: "If validation fails, fix the errors before proceeding"
- Add validation to pre-build checks
- Implement feedback loop: validator → agent → rebuild → validator

#### If Issue: Build Timeout (40.9% Error Rate)

**Symptom:** 40.9% error rate suggests timeouts during build/test

**Investigation:**
```bash
# Check timeout settings:
grep -r "timeout" src/a11y_fixer/adapters/codebase_compiler/
grep -r "TIMEOUT" src/a11y_fixer/

# Check build command complexity:
# Is it running too many tests?
# Is fixture setup slow?

# Check resource usage during build:
# Memory? CPU? Network?
```

**Fix strategy:**
- Increase timeout for build step (if time permits)
- Reduce test scope (run only affected component tests)
- Parallelize build tasks
- Check for infinite loops in validator

#### If Issue: qa_critic Not Validating Original Violation

**Symptom:** Score is always 5-10/20 despite agent claiming success

**Investigation:**
```python
# Check score_rubric tool:
# Does it re-run the original audit?
# Or does it just check for syntax errors?

# The scoring should be:
# 1. Get original violation (e.g., "button has no aria-label")
# 2. Apply agent's fix
# 3. Re-audit the fixed code
# 4. Check if violation gone

# If it's just checking syntax, that's the problem
```

**Fix strategy:**
- Ensure qa_critic re-audits after fix
- Compare violation count before/after
- Score based on violations cleared, not just syntax

---

## 🎯 Phase 3 Iteration Success Criteria

### Minimum Success (Proceed to Phase 4 Re-run)
- **Clearance rate:** ≥20% (improvement from 0%)
- **Error rate:** <30% (improvement from 40.9%)
- **Root cause:** Identified and fixed

### Acceptable Success (Proceed to Phase 5)
- **Clearance rate:** ≥40% (original Phase 3 target)
- **Error rate:** <20%
- **All sub-phases:** f1, f2, f3 ≥30% clearance each

### Full Success (Ready for Production)
- **Clearance rate:** ≥60%
- **Error rate:** <10%
- **HITL escalation rate:** <30% (only high-risk violations)

---

## 🔧 Quick Reference: Common Fixes

### Fix 1: Validator Too Strict (Estimated: 30-60 min)

```python
# In src/a11y_fixer/adapters/code_validator.py

class CodeValidator:
    def validate_typescript_file(self, path: Path):
        # ← Add exception for specific patterns:
        
        # BEFORE: Reject all missing imports
        errors.append("Missing import: X")
        
        # AFTER: Only reject if unused elsewhere
        if is_import_used_elsewhere(import_name):
            errors.append("Missing import: X")
```

### Fix 2: Agent Ignores Feedback (Estimated: 45-90 min)

```python
# In agents/codebase_compiler/compiler.py

SYSTEM_PROMPT = """
...existing prompt...

CRITICAL: When the validate_code tool returns errors:
1. Read all error messages carefully
2. DO NOT claim the build succeeds if validation failed
3. MUST fix all validation errors before returning
4. After fixing, call check_build again to verify

If you cannot fix a validation error, return an error response:
{"success": false, "error": "Validation error: X"}
"""
```

### Fix 3: Build Timeout (Estimated: 15-30 min)

```python
# In adapters/codebase_compiler.py

# Increase timeout:
COMPILE_TIMEOUT_SECONDS = 120  # was 60
TEST_TIMEOUT_SECONDS = 90      # was 60

# Or reduce scope:
def run_tests(component_under_test: str):
    # Only run tests for affected component:
    test_path = f"src/app/**/{component_under_test}/**/*.spec.ts"
    # Not all tests
```

### Fix 4: Re-audit in qa_critic (Estimated: 60-90 min)

```python
# In qa_critic, must re-audit after fix:

# Current behavior (likely): Just check syntax
def score_rubric(response: ViolationResponse) -> float:
    return 20.0 if response.success else 0.0

# Correct behavior: Re-audit
async def score_rubric(response: ViolationResponse) -> float:
    if not response.success:
        return 0.0
    
    # Apply the fix to fixture
    apply_changes_to_fixture(response.changes)
    
    # Re-run Axe audit on fixed code
    audit_after = await run_axe_audit(fixture)
    
    # Check if original violation still exists
    original_rule = violation["rule"]
    original_selector = violation["selector"]
    
    violations_after = [
        v for v in audit_after
        if v["rule"] == original_rule and v["selector"] == original_selector
    ]
    
    if violations_after:
        return 5.0  # Violation still exists
    else:
        return 20.0  # Violation fixed!
```

---

## 🎬 How to Execute This Guide

### Option A: Systematic Debugging (Recommended)

1. **Run Phase 3A** (60-90 min): Test without validator
2. **Analyze results:**
   - If validator bad → Phase 3C.1 (loosen validator)
   - If validator OK → Phase 3B (debug agent)
3. **Run Phase 3B** (2-3 hours): Single case debug
4. **Find root cause** and apply appropriate Phase 3C fix
5. **Re-test:** `python -m evaluation.run_eval --phase f1`
6. **If ≥20% clearance:** Success! Proceed to Phase 4 re-run

### Option B: Hypothesis-Driven (If Tight on Time)

Rank likely causes by probability:

1. **Most likely (40%):** Build timeout → Fix Phase 3C.3 → Re-test
2. **Second (35%):** qa_critic not re-auditing → Fix Phase 3C.4 → Re-test
3. **Third (20%):** Validator too strict → Fix Phase 3C.1 → Re-test
4. **Least (5%):** Agent ignores feedback → Fix Phase 3C.2 → Re-test

---

## 📝 Documentation to Update

After Phase 3 iteration succeeds:

1. **PHASE-3-COMPLETION.md**: Document what was fixed
2. **PHASE-4-COMPLETION.md**: Re-run calibration script, show impact
3. **Code comments**: Add "Phase 3 iteration fix" comments at fix sites

---

## ✅ Phase 3 Iteration Checklist

Before starting:
- [ ] Backup current evaluation/results directory
- [ ] Commit current code state to git
- [ ] Note baseline metrics (0% clearance, 40.9% error)

During investigation:
- [ ] Enable debug logging in codebase_compiler
- [ ] Test without validator first (Phase 3A)
- [ ] Document findings in /tmp/phase3_analysis.txt
- [ ] Create hypothesis with evidence

After fix:
- [ ] Re-run Phase 3.1a: `python -m evaluation.run_eval --phase f1`
- [ ] Verify clearance ≥20%
- [ ] Verify error rate <30%
- [ ] Commit fix with clear message
- [ ] Update documentation

Next phase:
- [ ] Run Phase 4 re-calibration
- [ ] If calibration shows impact: proceed to Phase 5
- [ ] If not: iterate hypothesis 2 or 3

---

## 🚨 Critical Path Assumptions

This guide assumes:
- ✅ Phase 2 data (results_summary.json) exists and is readable
- ✅ Phase 3 evaluation ran to completion (22 cases processed)
- ✅ Fixture (Hallucinate.io) builds successfully in baseline state
- ✅ Axe audit runs correctly on fixture

If any assumption fails, check PRIORITY-1-BUILD-VALIDATION.md for setup steps.
