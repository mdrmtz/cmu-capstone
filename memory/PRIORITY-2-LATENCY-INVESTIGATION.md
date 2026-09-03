# Priority 2: Latency Optimization & case-16 Investigation

## Problem Statement

1. **Latency Surge**: 223.3s average (+160s vs Phase 2 baseline)
   - case-16: 120.8s (hit timeout)
   - case-17: 325.7s (5.4 minutes)
   
2. **case-16 Timeout Error**: "unhandled errors in a TaskGroup (1 sub-exception)"
   - Hit timeout at 120.8s
   - Escalated to manual review
   - Likely infinite loop or tool failure

## Root Cause Analysis

### Latency Increase Breakdown

1. **RubricMiddleware Iterations** (Primary Culprit)
   - Currently: `max_iterations=3`
   - Each iteration: 30-60s LLM call + tool execution
   - 3 iterations = 90-180s just for middleware
   - **Fix**: Reduce to `max_iterations=2` or `1`

2. **Validation Tool Overhead**
   - Added `validate_code()` tool
   - Calls CodeValidator methods
   - Adds regex scanning overhead
   - **Fix**: Cache validation results, optimize regex patterns

3. **ng build Execution**
   - Takes 20-30s per case
   - Called every iteration
   - No caching between attempts
   - **Fix**: Cache build artifacts between iterations

4. **LLM API Latency**
   - OpenRouter Claude Haiku roundtrip: 15-30s per call
   - 3 iterations = 3× LLM calls
   - Network + processing adds up
   - **Fix**: Reduce iterations, better prompts

### case-16 Timeout Root Cause

Hypotheses:
1. **Infinite loop** in agent retry logic
   - RubricMiddleware keeps retrying
   - Rubric never satisfied (too strict)
   - Hits 120s timeout cap

2. **Failed tool call** that doesn't fail gracefully
   - locate_selector_in_component error
   - File I/O error
   - ng build hangs

3. **Slow LLM response**
   - OpenRouter experiencing latency
   - Claude Haiku taking longer than normal
   - Multiple retries triggered

4. **Bad interaction with validate_code()**
   - Validation tool returning confusing results
   - Agent confused about build status
   - Tries to fix non-existent problems

## Solution Strategy

### Priority 2.1: Quick Wins (5-10% latency reduction)

**Reduce RubricMiddleware iterations** from 3 to 2:
- Saves ~30-60s per case
- Trade-off: slightly lower scoring precision
- Mitigating: Better prompts can compensate

**Optimize validation tool**:
- Pre-compile regex patterns
- Cache validation results per file
- Skip validation on unchanged files
- Expected gain: 5-10s per case

### Priority 2.2: Medium Fixes (20-30% latency reduction)

**Improve system prompts**:
- Make instructions more concise
- Remove redundant examples
- Focus on essentials
- Expected gain: 10-20s per LLM call

**Add timeout handling**:
- Wrap tool calls with timeouts
- Fail gracefully instead of hanging
- Return partial results
- Fixes case-16 hangs

**Cache ng build artifacts**:
- Don't rebuild from scratch each iteration
- Reuse build cache between attempts
- Expected gain: 5-10s per iteration

### Priority 2.3: Deeper Fixes (40-50% latency reduction)

**Simplify rubric**:
- Current: 3 criteria (wcag_lexical, build_passes, axe_clear)
- Proposal: Focus on build_passes + WCAG lexical only
- Defer visual stability checks to Priority 3
- Expected gain: Fewer iterations needed

**Single-shot completion strategy**:
- Better initial fix generation
- Reduce need for iterations
- Target: 90%+ first-attempt success
- Expected gain: 50-80s per case

## Implementation Plan

### Phase 1: Immediate Fixes (30 mins)
1. Reduce RubricMiddleware iterations to 2
2. Add timeout guards around tool calls
3. Simplify system prompt (remove redundancy)

### Phase 2: Validation Optimization (1 hour)
1. Pre-compile regex patterns in CodeValidator
2. Add file-level caching
3. Skip validation for unchanged files
4. Benchmark: measure per-case latency improvement

### Phase 3: Better Prompts (1-2 hours)
1. Analyze case-17's successful strategy
2. Extract pattern and codify in prompt
3. Test on f2 phase (3 cases)
4. Measure clearance rate + latency

### Phase 4: Rubric Simplification (2-3 hours)
1. Identify which rubric criteria matter most
2. Remove or relax non-critical criteria
3. Test on extended subset
4. Trade-off analysis: quality vs speed

## Expected Impact

| Metric | Before | After P2 | Gain |
|--------|--------|----------|------|
| Mean Latency | 223.3s | ~90s | 60% reduction |
| case-16 Timeout | Yes | No | Eliminated |
| F1 Phase Time | 446s | 180s | 60% faster |
| Full 22 Cases | ~4 hours | ~1.5 hours | 62% faster |
| Build Success | 50% | 60%+ | Better |
| Clearance Rate | 0% | 10-20%+ | Better |

## Files to Modify

1. `src/a11y_fixer/agents/codebase_compiler.py`
   - Reduce `max_iterations` from 3 to 2
   - Simplify SYSTEM_PROMPT
   - Add timeout guards

2. `src/a11y_fixer/adapters/code_validator.py`
   - Pre-compile regex patterns
   - Add @functools.lru_cache for file validation
   - Add timeout parameter

3. `src/a11y_fixer/domain/compliance_planner.py` (if applicable)
   - Simplify fix generation prompts
   - Add timeout guards

## Testing Strategy

1. **Quick test**: f1 phase (2 cases)
   - Baseline: 446s
   - Target: <200s
   - Success: Both cases improve

2. **Extended test**: f2 phase (3 cases)
   - Baseline: ~550s estimated
   - Target: <250s
   - Success: Latency improves without losing quality

3. **Full test**: --phase all (22 cases)
   - Baseline: ~240 minutes (4 hours)
   - Target: <90 minutes (1.5 hours)
   - Success: 40%+ clearance maintained or improved

## Success Criteria

✅ **Priority 2 Complete When**:
1. case-16 timeout eliminated (no more TaskGroup errors)
2. Mean latency reduced to <100s per case
3. F1 phase completes in <200s total
4. Clearance rate maintained or improved (≥0% baseline)
5. No regressions in scoring

## Open Questions

1. What specifically is causing case-16 timeout?
   - Agent loop issue?
   - Tool failure?
   - Rubric too strict?

2. Why does case-17 take 325s when case-16 only 120s?
   - Different problem complexity?
   - Different agent pathways?
   - Network variance?

3. Is RubricMiddleware the bottleneck?
   - Profile actual time breakdown
   - Measure LLM vs tool vs middleware time

## Next Steps

1. **Implement Priority 2.1** (quick wins) → measure improvement
2. **Run f1 test** with changes → validate fixes
3. **Investigate case-16** error specifically
4. **Profile** latency breakdown with instrumentation
5. **Iterate** based on data from tests
