# Axe-Core 300-Second Timeout Blocker — Root Cause & Fix

**Date:** 2026-09-02  
**Last corrected:** 2026-09-02 (root-cause comment revised after live run confirmed behaviour)  
**Severity:** CRITICAL — blocked 100% of benchmark runs (Phase 2, Phase 3, all future phases)  
**Status:** ✅ FIXED in `src/a11y_fixer/adapters/audit_runner.py`

---

## Symptom

Every benchmark case (both the single-case `case-09` test and the full 22-case run)
failed with the same error after exactly 300 seconds:

```
Command ['/Users/dks0721706/.nvm/versions/node/v24.19.0/bin/npx',
         '@axe-core/cli', 'http://127.0.0.1:4200/', '--tags',
         'wcag2a,wcag2aa', '--stdout']
timed out after 300.0 seconds
```

Result: 0% clearance, 100% error rate, zero useful data.

---

## Root Cause (corrected — confirmed by live run)

`@axe-core/cli` v4.13.0 uses **Selenium WebDriver + ChromeDriver** (NOT Puppeteer).

### What `parseBrowser()` actually does

`@axe-core/cli`'s internal `parseBrowser()` function (in
`node_modules/@axe-core/cli/dist/src/lib/utils.js`) accepts only specific string
prefixes: `chrome`, `firefox`, `ie`, `safari`, `edge`.  When `--browser` is omitted,
the internal default resolves to the `chrome-headless` sentinel that selects the
dedicated `ServiceBuilder` + headless `ChromeOptions` code path.

> ⚠️ **Correction to initial analysis:** Passing `--browser chrome-headless`
> explicitly is **rejected** by the switch-case parser with `"Unknown browser
> chrome-headless"`.  The initial fix comment that said this flag was required was
> wrong on this detail.  Omitting `--browser` is the correct invocation and takes the
> headless Chrome path by default.

### The actual hang: missing `--chromedriver-path`

Without `--chromedriver-path`, `@axe-core/cli` lets the `chromedriver` npm package
auto-detect the ChromeDriver binary.  If the **system Chrome major version doesn't
exactly match the bundled ChromeDriver version**, the WebDriver session creation call
stalls indefinitely — ChromeDriver launches but never completes the handshake, so the
subprocess neither exits nor writes to stdout.  Python's `subprocess.run(timeout=300)`
kills it after 300 seconds.

The fix: pass `--chromedriver-path` pointing at the **bundled binary inside
`Hallucinate.io/node_modules/chromedriver/bin/chromedriver`** — this pin is
version-matched to the installed `chromedriver` npm package and avoids the
auto-detection mismatch.

---

## What Was NOT the Problem

- ❌ `ng serve` startup — port-open check passed; ng serve was running normally
- ❌ Node.js / npx path — resolved correctly via nvm
- ❌ `@axe-core/cli` installation — present in `Hallucinate.io/node_modules/`
- ❌ Chrome/Chromium absence — Chrome was findable; ChromeDriver v152 was installed
- ❌ Missing `--browser` flag — omitting it is correct; the default is headless Chrome
- ❌ Passing `--browser chrome-headless` — this would be rejected ("Unknown browser")

---

## The Fix

**File:** `src/a11y_fixer/adapters/audit_runner.py` — `audit_urls()` method

```python
# BEFORE (broken) — no --chromedriver-path, ChromeDriver version mismatch hangs session
cmd = [npx, "@axe-core/cli", *urls, "--tags", ",".join(self.tags), "--stdout"]

# AFTER (fixed)
chromedriver_bin = self.fixture_path / "node_modules" / "chromedriver" / "bin" / "chromedriver"
cmd = [
    npx, "@axe-core/cli",
    # No --browser flag: omitting it is correct — parseBrowser() defaults to the
    # 'chrome-headless' sentinel internally, selecting the dedicated ServiceBuilder
    # + headless ChromeOptions code path. Passing "--browser chrome-headless"
    # explicitly is REJECTED with "Unknown browser chrome-headless".
    "--timeout", "60",  # per-page axe timeout (seconds); default is 90
    *([f"--chromedriver-path={chromedriver_bin}"] if chromedriver_bin.exists() else []),
    # ↑ THE ACTUAL FIX: pin to the npm-bundled chromedriver binary that is
    # version-matched to the installed chromedriver package. Without this,
    # @axe-core/cli auto-detects the system ChromeDriver, which may be a different
    # major version than the installed Chrome, causing the WebDriver session to
    # stall indefinitely (producing the 300 s timeout).
    *urls,
    "--tags", ",".join(self.tags),
    "--stdout",
]
per_url_budget = 90
dynamic_timeout = min(DEFAULT_AUDIT_TIMEOUT_SECONDS, len(urls) * per_url_budget + 30)
result = subprocess.run(
    cmd, cwd=self.fixture_path, capture_output=True, text=True,
    timeout=dynamic_timeout, check=False,
)
```

### Changes summary

| Change | Why |
|--------|-----|
| Added `--chromedriver-path` (conditional) | **The actual fix** — pins the version-matched bundled binary; graceful fallback if absent |
| Removed `--browser chrome-headless` | Would be rejected; `parseBrowser()` doesn't accept this string |
| Added `--timeout 60` | Per-page axe timeout; surfaces page-load errors faster |
| Dynamic subprocess timeout | 90 s × num_urls + 30 s overhead |
| Improved error message | Includes `stderr_tail` so ChromeDriver errors become visible |

---

## How to Verify the Fix

Run a single benchmark case:

```bash
cd /Users/dks0721706/dev/cmu-agentic-ai-program-2026/cmu-capstone/agent
source /Users/dks0721706/dev/cmu-agentic-ai-program-2026/CMU/bin/activate
python -m evaluation.run_eval --case-ids case-09 --no-live
```

Expected: completes in < 3 minutes, NOT 300 s timeout.

Sanity-check axe-core standalone (no Python):

```bash
cd /Users/dks0721706/dev/cmu-agentic-ai-program-2026/Hallucinate.io
npx @axe-core/cli \
  --timeout 60 \
  --chromedriver-path node_modules/chromedriver/bin/chromedriver \
  http://127.0.0.1:4200/ \
  --tags wcag2a,wcag2aa \
  --stdout | python3 -m json.tool | head -20
```

Expected: JSON output in < 60 s.

---

## Impact on the Plan

| Phase | Previous status | Corrected status |
|-------|----------------|------------------|
| Phase 2 (22-case benchmark) | 🟡 READY | ✅ NOW ACTUALLY READY |
| Phase 3.1a–c | ⏳ PLANNED | ✅ UNBLOCKED |
| Phases 4–8 | 🔴 BLOCKED | ✅ UNBLOCKED |

---

## What to Do Next

```bash
# 1. Single-case smoke test
python -m evaluation.run_eval --case-ids case-09 --no-live

# 2. If smoke test passes — full 22-case run, split into 7 bundles
#    (no wrapper script; run_eval.py's --case-ids already handles this —
#    see memory/plans/bundle-eval-agent-prompt.md for the exact commands
#    and the merge step)
python -m evaluation.run_eval --case-ids case-01,case-02,case-03,case-04 \
  --output evaluation/results/bundles/bundle_1_summary.json --no-live
# ... repeat for bundles 2-7, then merge per the runbook
```

**Confirmed working (2026-09-02):** a real run of bundle 1 (case-01 to case-04)
completed with latencies of 68–217 seconds per case — no 300 s timeouts. One
unrelated `Connection closed` error occurred on case-03 (a different failure mode,
not the axe-core hang this fix addresses).
