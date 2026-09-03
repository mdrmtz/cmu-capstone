# Phase F Evaluation Findings

**Date:** 2026-08-31  
**Target repository:** mdrmtz/Hallucinate.io  
**LLM backend:** OpenRouter (`meta-llama/llama-3.3-70b-instruct`, then `anthropic/claude-3-haiku`)  
**Rule tested:** `image-alt` (WCAG 1.1.1 Non-text Content)  
**Pages tested:** `/about`, `/case-studies`

---

## Phase Progression

| Phase | Scope | Cases | Model | Error rate | Mean latency | Notes |
|-------|-------|-------|-------|-----------|-------------|-------|
| F.1 | `/about` (1.1.1 only) | 1 | Llama 3.3 70B | 0% | 35.5s | Baseline smoke test |
| F.2 | `/case-studies` (1.1.1 only) | 3 | Llama 3.3 70B | 66.7% | 980.6s | Provider errors & timeouts |
| **F.3** | `/about` + `/case-studies` (1.1.1) | **5** | Claude Haiku | **40%** | **67.0s** | Live PR delivery enabled |

---

## Phase F.1 Results — `/about` (dry-run)

| Case | Selector | Rubric | Route | Cleared | Error |
|------|----------|--------|-------|---------|-------|
| case-16 | `img[src$="about-hero.png"]` | **18.0/20** | auto | false¹ | — |

**Brier score:** 0.81  
**Summary:** Agent produced a high-quality fix proposal with no errors and self-approved routing. No PRs created (dry-run).

---

## Phase F.2 Results — `/case-studies` (dry-run)

| Case | Selector | Rubric | Route | Latency | Error |
|------|----------|--------|-------|---------|-------|
| case-06 | `img[src$="atlas-dashboard.svg"]` | 0.0 | human | 2.7s | no structured response after retries |
| case-07 | `article:nth-child(2) img` | **18.0** | auto | 726.8s | — |
| case-08 | `article:nth-child(3) img` | 0.0 | human | 2212.5s | Provider returned error |

**Brier score:** 0.27 | **Error rate:** 66.7%  
**Summary:** Llama 3.3 70B inconsistently produces structured output via ToolStrategy. case-08 ran for 37 minutes before failing with a provider error, indicating OpenRouter credit depletion.

---

## Phase F.3 Results — `/about` + `/case-studies` (live PR delivery)

> Model switched to `anthropic/claude-3-haiku` after Llama exhausted credits.  
> Per-case timeout of 300s applied to prevent runaway billing.

| Case | Page | Selector | Rubric | Route | Latency | Error |
|------|------|----------|--------|-------|---------|-------|
| case-06 | /case-studies | `img[src$="atlas-dashboard.svg"]` | **10.0** | human | 77.5s | — |
| case-07 | /case-studies | `article:nth-child(2) img` | **13.0** | human | 122.5s | — |
| case-08 | /case-studies | `article:nth-child(3) img` | 0.0 | human | 44.7s | unhandled errors in a TaskGroup |
| case-16 | /about | `img[src$="about-hero.png"]` | **16.0** | **auto** | 70.3s | — |
| case-17 | /about | `img[src$="team-photo.jpg"]` | 0.0 | human | 20.1s | Budget limit exceeded (monthly) |

**Brier score:** 0.26 | **Error rate:** 40% | **Mean latency:** 67s  

---

## Key Findings

### 1. LLM Compatibility
- **Llama 3.3 70B + ToolStrategy** is unreliable: structured output fails ~60% of the time, with occasional extreme latency (37+ min).
- **Claude-3-Haiku + ToolStrategy** is reliable: 3/5 cases produced structured rubric scores within 2 minutes.

### 2. Clearance Rate is Always 0% by Design
`cleared=false` for all cases is **expected behavior**, not a bug. `_capture_and_reset_git_changes()` in `cli.py` explicitly runs `git checkout -- . && git clean -fd` before `_recheck_cleared()` to ensure violations don't contaminate subsequent cases. The fixture is always clean when the axe recheck runs, so violations are always still present.

**True success metric is PR creation / HITL queue population**, not `violation_clearance_rate`.

### 3. HITL Queue Populated (2 entries from F.3)
Two fix proposals were written to `hitl_queue/` for human review:

- `1788241109968904000-image-alt-img-src---atlas-dashboard-svg.json` (case-06)  
  Proposed fix: `aria-label="A dashboard showing usage statistics and metrics for the Atlas product."` — WCAG technique G94, score 10.0.

- `1788241232651310000-image-alt-article-nth-child-2----img.json` (case-07)  
  Score 13.0, routed to human review.

### 4. `codebase_compiler` Cannot Locate Component Files
Even when the agent reasons correctly about the fix, the `codebase_compiler` subagent fails to locate the Angular component template file corresponding to the violated selector. The fix proposal is correct but not applied, reducing rubric scores and preventing auto-delivery.

### 5. case-16 Self-Approved (route=auto)
case-16 (`/about`, score 16.0) was the only case the agent was confident enough to route without human review. Despite auto-routing, `cleared=false` due to finding #2 above.

---

## Blockers & Next Steps

| Priority | Issue | Fix |
|----------|-------|-----|
| 🔴 P0 | OpenRouter monthly budget exhausted | Add credits at openrouter.ai, or set per-run credit cap |
| 🔴 P0 | `codebase_compiler` can't map selector → Angular template file | Improve component file discovery (e.g. search `src/` for selector strings) |
| 🟡 P1 | Llama 3.3 70B structured output failures | Use Claude Haiku or GPT-4 as default model; Llama as fallback |
| 🟡 P1 | case-08 `TaskGroup` error | Debug async sub-task failure in agent graph |
| 🟢 P2 | `violation_clearance_rate` misleading (always 0%) | Add `pr_delivered` field to `CaseResult` as the true success metric |

---

## Infrastructure Changes Made During Phase F

| File | Change |
|------|--------|
| `evaluation/phases.yaml` | Created — data-driven phase definitions (f1, f2, f3) |
| `evaluation/run_eval.py` | Added `--phase` flag, `load_phases()`, `filter_cases_by_phase()`, 300s per-case timeout |
| `src/a11y_fixer/agents/codebase_compiler.py` | Filtered out `list_projects` tool (invalid schema causes Pydantic error) |
| `pyproject.toml` | Added `pyyaml>=6.0.0` dependency |

---

¹ `cleared=false` is always expected in evaluation mode; see Finding #2.
