# Exact Code Fixes: Phase 0 Tier 1 Implementation

**Status**: Gap analysis complete. Ready to implement.  
**Time Estimate**: 2-3 hours total  
**Prerequisite**: Activate venv + cd to `/cmu-capstone/agent`

---

## Fix 1: Phase 0.2 - Git-Reset Bug in _run_one_case()

### Location
`evaluation/run_eval.py` → function `_run_one_case()`

### Current Code (Problem)
```python
async def _run_one_case(
    case_id: str,
    case_detail: dict,
    fixture: Path,
    backend: str,
    **kwargs
) -> dict:
    """Run a single benchmark case (audit → agent → deliver → reset)."""
    try:
        # ... case processing ...
        result = await cli.deliver_violation(...)
        return {"case_id": case_id, "result": result, ...}
    
    except asyncio.TimeoutError:
        # BUG: Doesn't reset fixture!
        return {
            "case_id": case_id,
            "error": "timeout",
            "status": "TIMEOUT"
        }
    
    except Exception as e:
        # BUG: Doesn't reset fixture!
        return {
            "case_id": case_id,
            "error": str(e),
            "status": "ERROR"
        }
    
    # BUG: No finally block!
```

### Fixed Code
```python
async def _run_one_case(
    case_id: str,
    case_detail: dict,
    fixture: Path,
    backend: str,
    **kwargs
) -> dict:
    """Run a single benchmark case (audit → agent → deliver → reset)."""
    try:
        # ... case processing ...
        result = await cli.deliver_violation(...)
        return {"case_id": case_id, "result": result, ...}
    
    except asyncio.TimeoutError:
        return {
            "case_id": case_id,
            "error": "timeout",
            "status": "TIMEOUT"
        }
    
    except Exception as e:
        return {
            "case_id": case_id,
            "error": str(e),
            "status": "ERROR"
        }
    
    finally:
        # FIX: Always reset fixture, even on error
        # Idempotent: no-op if deliver_violation already consumed it
        try:
            cli._capture_and_reset_git_changes(fixture)
        except Exception:
            pass  # Ignore cleanup errors
```

### What Changed
- Added `finally` block that ALWAYS runs (success or exception)
- Calls `cli._capture_and_reset_git_changes(fixture)` to reset git state
- Wrapped in try/except to handle cleanup errors gracefully
- Idempotent: safe to call even if already reset

### Why This Matters
- Without this, uncommitted fixture changes leak to next case
- Phase 2 benchmark (22 cases) would have state pollution
- Critical for test isolation and reliability

### Verification
After applying:
```bash
# Check that finally block is present
grep -A 2 "finally:" evaluation/run_eval.py | head -3
# Should show: finally block with _capture_and_reset_git_changes call
```

---

## Fix 2: Phase 0.3 - Calibration Threading in cli.py

### Location 1: deliver_violation() function

#### Current Code (Missing p_ik_floor parameter)
```python
async def deliver_violation(
    violation: dict,
    response: dict,
    pr_config: dict,
    repo: Any = None,
    dry_run: bool = True
) -> dict:
    """Deliver a solution as a PR draft or live."""
    
    # ... PR creation logic ...
    
    risk_assessment = await assess_risk(
        solution=response.get("solution"),
        violation_id=violation.get("id"),
        # BUG: p_ik_floor never passed here!
    )
```

#### Fixed Code
```python
async def deliver_violation(
    violation: dict,
    response: dict,
    pr_config: dict,
    repo: Any = None,
    dry_run: bool = True,
    p_ik_floor: float | None = None  # NEW: Accept calibrated floor
) -> dict:
    """Deliver a solution as a PR draft or live."""
    
    # Use provided floor or default
    if p_ik_floor is None:
        from a11y_fixer.domain.hitl_policy import DEFAULT_P_IK_FLOOR
        p_ik_floor = DEFAULT_P_IK_FLOOR
    
    # ... PR creation logic ...
    
    risk_assessment = await assess_risk(
        solution=response.get("solution"),
        violation_id=violation.get("id"),
        p_ik_floor=p_ik_floor  # FIX: Now threaded through
    )
```

### Location 2: _acmd_run() function

#### Current Code (Missing calibration load)
```python
async def _acmd_run(
    audit_path: str | None = None,
    repo: str | None = None,
    dry_run: bool = True
) -> dict:
    """Run agent on violations."""
    
    # Load violations
    violations = load_violations(...)
    
    # Process each violation
    for violation in violations:
        result = await deliver_violation(
            violation,
            response,
            pr_config,
            # BUG: p_ik_floor never passed!
        )
```

#### Fixed Code
```python
async def _acmd_run(
    audit_path: str | None = None,
    repo: str | None = None,
    dry_run: bool = True
) -> dict:
    """Run agent on violations."""
    
    # FIX: Load latest calibration before processing
    calibrated_floor = DEFAULT_P_IK_FLOOR
    results_summary_path = config.agent_root() / "evaluation" / "results" / "results_summary.json"
    
    if results_summary_path.exists():
        try:
            from a11y_fixer.hitl.review_queue import calibrate_from_results
            calibrated_floor = await calibrate_from_results(results_summary_path)
            print(f"📊 Using calibrated P(IK) floor: {calibrated_floor:.3f}")
        except Exception as e:
            print(f"⚠️ Calibration failed, using default: {e}")
            calibrated_floor = DEFAULT_P_IK_FLOOR
    else:
        print(f"📊 Using default P(IK) floor: {DEFAULT_P_IK_FLOOR:.3f} (no results_summary.json)")
    
    # Load violations
    violations = load_violations(...)
    
    # Process each violation with calibrated floor
    for violation in violations:
        result = await deliver_violation(
            violation,
            response,
            pr_config,
            p_ik_floor=calibrated_floor  # FIX: Pass calibrated floor
        )
```

### Location 3: _cmd_run() function (if synchronous version exists)

Apply same changes as _acmd_run() but using synchronous calls.

---

## Fix 3: Phase 0.3 - Calibration Threading in run_eval.py

### Location: _arun_eval() function

#### Current Code (Missing calibration)
```python
async def _arun_eval(
    phases: list,
    case_ids: str | None = None,
    dry_run: bool = True,
    backend: str = "openrouter"
) -> dict:
    """Run evaluation on specified cases."""
    
    # Load cases
    cases = load_benchmark_cases(case_ids)
    
    # Run each case
    for case in cases:
        result = await _run_one_case(
            case["id"],
            case,
            fixture,
            backend
            # BUG: p_ik_floor never passed!
        )
```

#### Fixed Code
```python
async def _arun_eval(
    phases: list,
    case_ids: str | None = None,
    dry_run: bool = True,
    backend: str = "openrouter"
) -> dict:
    """Run evaluation on specified cases."""
    
    # FIX: Load calibration before running cases
    from a11y_fixer.domain.hitl_policy import DEFAULT_P_IK_FLOOR
    from a11y_fixer.hitl.review_queue import calibrate_from_results
    
    calibrated_floor = DEFAULT_P_IK_FLOOR
    results_summary_path = config.agent_root() / "evaluation" / "results" / "results_summary.json"
    
    if results_summary_path.exists():
        try:
            calibrated_floor = await calibrate_from_results(results_summary_path)
            print(f"📊 Using calibrated P(IK) floor: {calibrated_floor:.3f}")
        except Exception as e:
            print(f"⚠️ Calibration failed, using default: {e}")
    
    # Load cases
    cases = load_benchmark_cases(case_ids)
    
    # Run each case with calibrated floor
    for case in cases:
        result = await _run_one_case(
            case["id"],
            case,
            fixture,
            backend,
            p_ik_floor=calibrated_floor  # FIX: Pass calibrated floor
        )
```

---

## Fix 4: Phase 0.1 - Add Tests for File Locator

### Location: Create NEW FILE
`tests/test_file_locator.py`

### Boilerplate
```python
"""Unit tests for file_locator.py - CSS selector to component file mapping."""

import pytest
from pathlib import Path
from a11y_fixer.adapters.file_locator import locate_selector_in_component


class TestFileLocator:
    """Test CSS selector to file location discovery."""
    
    @pytest.fixture
    def fixture_path(self):
        """Get Hallucinate.io fixture path."""
        from a11y_fixer import config
        return config.fixture_path()
    
    def test_locate_image_alt_selector(self, fixture_path):
        """Test locating img[alt] selector in components."""
        result = locate_selector_in_component(
            selector='img[src$="atlas-dashboard.svg"]',
            codebase_root=fixture_path / "src"
        )
        assert result is not None
        assert "src" in str(result)
        assert ".ts" in str(result) or ".html" in str(result)
    
    def test_locate_button_selector(self, fixture_path):
        """Test locating button selector."""
        result = locate_selector_in_component(
            selector="button",
            codebase_root=fixture_path / "src"
        )
        # Multiple buttons exist; should return at least one
        assert result is not None
    
    def test_locate_html_lang_selector(self, fixture_path):
        """Test locating html lang attribute selector."""
        result = locate_selector_in_component(
            selector="html",
            codebase_root=fixture_path / "src"
        )
        # html selector should map to index.html or main.ts
        assert result is not None
        assert "index" in str(result) or "main" in str(result)
    
    def test_locate_with_attribute_selectors(self, fixture_path):
        """Test complex attribute selectors."""
        result = locate_selector_in_component(
            selector='a[href$="blog"]',
            codebase_root=fixture_path / "src"
        )
        assert result is not None
    
    def test_no_match_returns_none_or_fallback(self, fixture_path):
        """Test handling of non-existent selectors."""
        result = locate_selector_in_component(
            selector="div.totally-nonexistent-class-xyz",
            codebase_root=fixture_path / "src"
        )
        # Should return None or fallback, not crash
        assert result is None or isinstance(result, (str, Path))
    
    def test_multiple_candidates_returns_best_match(self, fixture_path):
        """Test ranking when multiple files match."""
        # If multiple files have the selector, should return most specific
        result = locate_selector_in_component(
            selector="p",  # Common element
            codebase_root=fixture_path / "src"
        )
        # Should return one file (best match), not crash
        assert result is not None
        assert isinstance(result, (str, Path))
    
    def test_path_exists_after_location(self, fixture_path):
        """Test that returned path actually exists."""
        result = locate_selector_in_component(
            selector='img[src$="dashboard"]',
            codebase_root=fixture_path / "src"
        )
        if result is not None:
            assert Path(result).exists(), f"File not found: {result}"
```

### What to Verify After Writing Tests
```bash
# Run the tests
python -m pytest tests/test_file_locator.py -v

# Expected: All tests should pass (or skip if fixtures not available)
# Count: ≥8 test functions should exist
```

---

## Summary of Changes

### Tier 1 Implementation Checklist

| Fix | File | Lines | Time | Blocking |
|-----|------|-------|------|----------|
| 1. Git-reset | run_eval.py | ~5 | 15 min | CRITICAL |
| 2. Calibration (cli.py) | cli.py | ~20 | 45 min | CRITICAL |
| 3. Calibration (run_eval.py) | run_eval.py | ~20 | 45 min | CRITICAL |
| 4. File locator tests | tests/test_file_locator.py | ~100 | 60 min | MEDIUM |

**Total**: ~80 lines of code, 2.5-3 hours

### Testing After Each Fix

1. **After Fix 1 (git-reset)**:
   ```bash
   python -c "from evaluation import run_eval; print('✓ run_eval imports')"
   ```

2. **After Fix 2-3 (calibration)**:
   ```bash
   python -c "from a11y_fixer import cli; print('✓ cli imports')"
   ```

3. **After Fix 4 (tests)**:
   ```bash
   python -m pytest tests/test_file_locator.py -v
   ```

4. **Full Suite** (after all fixes):
   ```bash
   python -m pytest tests/ -q --tb=short
   # Expected: ≥291 passing, zero failures
   ```

---

## Next: Execution Plan

1. **Code all 4 fixes** (2-3 hours)
2. **Run test suite** (10 minutes)
3. **Start Phase 1: Smoke test** (15 minutes)
4. **Phase 2: 22-case benchmark** (30 minutes)
5. **Verify real data generated** (5 minutes)

**At this point, you'll have:**
- ✅ Phase 0 complete (all 4 fixes in place)
- ✅ Phase 1-2 validation (smoke + benchmark)
- ✅ Real `results_summary.json` for calibration
- ✅ Proof that gate logic works end-to-end

Then can proceed to Phases 3-8 (calibration, human review, docs, CI, etc.)
