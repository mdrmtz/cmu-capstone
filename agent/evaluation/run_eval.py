"""Evaluation harness: runs every benchmark case through the deep agent and
computes real HELM-aligned metrics (replacing Module-07's fabricated
compendium numbers per the plan's Phase F reconciliation goal).

Driving the agent needs a configured LLM backend (`config.
selected_llm_backend()`); `compute_metrics()` itself is pure aggregation
over `CaseResult`s and is unit-tested against synthetic results, independent
of any live LLM call. Defaults to dry-run PR delivery (`live=False`) -
a benchmark run must never open a live PR as a side effect.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from a11y_fixer import cli, config
from a11y_fixer.adapters.audit_runner import AxeAuditRunner
from a11y_fixer.domain.guardrail_rules import brier_score, expected_calibration_error

BENCHMARK_CASES_PATH = Path(__file__).resolve().parent / "benchmark_cases.json"
PHASES_PATH = Path(__file__).resolve().parent / "phases.yaml"
DEFAULT_RESULTS_PATH = Path(__file__).resolve().parent / "results" / "results_summary.json"


@dataclass
class CaseResult:
    case_id: str
    rule: str
    page: str
    route: str
    rubric_score: float
    cleared: bool
    latency_seconds: float
    error: str | None = None


def load_benchmark_cases(path: Path = BENCHMARK_CASES_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_phases(path: Path = PHASES_PATH) -> dict[str, dict]:
    """Load phase definitions from phases.yaml."""
    if not path.exists():
        raise FileNotFoundError(f"phases.yaml not found at {path}")
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("phases", {})


def filter_cases_by_phase(cases: list[dict], phase_name: str) -> tuple[list[dict], dict]:
    """Filter benchmark cases by phase definition.
    
    Returns: (filtered_cases, phase_definition)
    """
    phases = load_phases()
    if phase_name not in phases:
        available = ", ".join(sorted(phases.keys()))
        raise ValueError(f"Phase '{phase_name}' not found. Available: {available}")
    
    phase_def = phases[phase_name]
    filters = phase_def.get("filters", [])
    
    # Apply all filters (OR logic — case matches if it satisfies ANY filter)
    filtered = []
    for case in cases:
        for filter_spec in filters:
            page_match = case.get("page") == filter_spec.get("page")
            wcag_match = case.get("wcag") == filter_spec.get("wcag")
            if page_match and wcag_match:
                filtered.append(case)
                break  # Don't add duplicates
    
    return filtered, phase_def



def _confidence(result: CaseResult) -> float:
    """Normalize a case's 0-20 rubric score to a [0, 1] confidence for calibration math."""
    return max(0.0, min(1.0, result.rubric_score / 20.0))


def _group_clearance_by_rule(results: list[CaseResult]) -> dict[str, dict]:
    by_rule: dict[str, list[CaseResult]] = {}
    for result in results:
        by_rule.setdefault(result.rule, []).append(result)
    return {rule: {"total": len(rs), "cleared": sum(1 for r in rs if r.cleared)} for rule, rs in by_rule.items()}


def compute_metrics(results: list[CaseResult]) -> dict[str, Any]:
    """Pure aggregation over per-case results - no I/O, directly unit-testable."""
    total = len(results)
    if total == 0:
        return {"total_cases": 0}

    cleared = sum(1 for r in results if r.cleared)
    human_escalations = sum(1 for r in results if r.route == "human")
    errored = sum(1 for r in results if r.error is not None)
    latencies = [r.latency_seconds for r in results]
    predictions = [_confidence(r) for r in results]
    outcomes = [1 if r.cleared else 0 for r in results]

    return {
        "total_cases": total,
        "violation_clearance_rate": cleared / total,
        "human_escalation_rate": human_escalations / total,
        "error_rate": errored / total,
        "mean_latency_seconds": sum(latencies) / total,
        "brier_score": brier_score(predictions, outcomes),
        "expected_calibration_error": expected_calibration_error(predictions, outcomes),
        "by_rule": _group_clearance_by_rule(results),
    }


def _recheck_cleared(runner: AxeAuditRunner, case: dict) -> bool:
    """Re-run a scoped axe-core audit against just this case's page and check the rule cleared.

    Uses a pre-started AxeAuditRunner to avoid restarting `ng serve` for each case.
    Reuses the same server instance across all cases in a test phase.
    """
    report = runner.audit_pages(pages=(case["page"],))
    page_report = report["pages"][0] if report["pages"] else {"violation_rules": []}
    return case["rule"] not in page_report["violation_rules"]


async def _run_one_case(
    graph: Any,
    case: dict,
    *,
    pr_config: config.PRDeliveryConfig,
    fixture: Path,
    output_dir: Path,
    runner: AxeAuditRunner,
) -> CaseResult:
    start = time.monotonic()
    message = (
        "Resolve this axe-core violation:\n"
        f"rule: {case['rule']}\n"
        f"page: {case['page']}\n"
        f"selector: {case['selector']}\n"
        f"wcag: {case['wcag']}\n"
        f"ground truth hint: {case['ground_truth_fix']}\n"
    )

    # Retry up to 3 times for non-deterministic empty responses
    MAX_ATTEMPTS = 3
    CASE_TIMEOUT_SECONDS = 120  # 5-minute hard cap per case to prevent credit runaway
    for attempt in range(MAX_ATTEMPTS):
        thread_config = {"configurable": {"thread_id": f"{case['id']}-attempt{attempt + 1}", "recursion_limit": 50}}
        try:
            result = await asyncio.wait_for(
                graph.ainvoke({"messages": [{"role": "user", "content": message}]}, config=thread_config),
                timeout=CASE_TIMEOUT_SECONDS,
            )
            result = await cli.resolve_interrupts(graph, thread_config, result, auto_approve=True)
            response = result.get("structured_response")

            # Only retry if structured_response is None; other errors don't retry
            if response is None:
                if attempt < MAX_ATTEMPTS - 1:
                    continue  # Try again with fresh thread_id
                # All retries exhausted
                return CaseResult(
                    case_id=case["id"], rule=case["rule"], page=case["page"], route="human",
                    rubric_score=0.0, cleared=False, latency_seconds=time.monotonic() - start,
                    error="no structured response produced after retries",
                )

            # Successfully got a response
            cli.deliver_violation(case, response, fixture=fixture, pr_config=pr_config, output_dir=output_dir)
            cleared = _recheck_cleared(runner, case)
            return CaseResult(
                case_id=case["id"], rule=case["rule"], page=case["page"], route=response.route,
                rubric_score=response.score, cleared=cleared, latency_seconds=time.monotonic() - start,
            )
        except asyncio.TimeoutError:
            return CaseResult(
                case_id=case["id"], rule=case["rule"], page=case["page"], route="human",
                rubric_score=0.0, cleared=False, latency_seconds=time.monotonic() - start,
                error=f"case timed out after {CASE_TIMEOUT_SECONDS}s",
            )
        except Exception as exc:  # noqa: BLE001 - one case's failure must not abort the whole benchmark run
            return CaseResult(
                case_id=case["id"], rule=case["rule"], page=case["page"], route="human",
                rubric_score=0.0, cleared=False, latency_seconds=time.monotonic() - start, error=str(exc),
            )


async def _arun_eval(
    *,
    cases_path: Path = BENCHMARK_CASES_PATH,
    output_path: Path = DEFAULT_RESULTS_PATH,
    live: bool | None = False,
) -> dict[str, Any]:
    from a11y_fixer.deep_agent import abuild_agent  # noqa: PLC0415 - deferred: keeps compute_metrics importable with no MCP/network cost

    cases = load_benchmark_cases(cases_path)
    pr_config = config.resolve_pr_delivery(live)
    fixture = config.fixture_path()
    output_dir = config.agent_root() / "evaluation" / "results" / "prs"

    graph = await abuild_agent()

    # Start server once for all cases to reuse browser session across cases
    runner = AxeAuditRunner(fixture_path=fixture)
    runner.start_server()
    try:
        results = [
            await _run_one_case(graph, case, pr_config=pr_config, fixture=fixture, output_dir=output_dir, runner=runner) for case in cases
        ]
    finally:
        runner.stop_server()

    summary = compute_metrics(results)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps({"summary": summary, "cases": [vars(r) for r in results]}, indent=2), encoding="utf-8"
    )
    return summary


def run_eval(
    *,
    cases_path: Path = BENCHMARK_CASES_PATH,
    output_path: Path = DEFAULT_RESULTS_PATH,
    live: bool | None = False,
) -> dict[str, Any]:
    return asyncio.run(_arun_eval(cases_path=cases_path, output_path=output_path, live=live))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_eval",
        description="Run Phase F evaluation: data-driven test scenarios",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run Phase F.1: /about (1.1.1) — dry-run
  python -m evaluation.run_eval --phase f1

  # Run Phase F.3: /about and /case-studies (1.1.1) — LIVE PR creation
  python -m evaluation.run_eval --phase f3

  # Override live default: force dry-run for phase f3
  python -m evaluation.run_eval --phase f3 --no-live
        """,
    )

    # Mutually exclusive group for phase vs. direct cases path
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--phase",
        help="Phase name (f1, f2, f3, ...) — reads filters from phases.yaml",
    )
    group.add_argument(
        "--cases",
        default=str(BENCHMARK_CASES_PATH),
        help="Path to benchmark_cases.json (default: %(default)s)",
    )

    parser.add_argument("--output", default=str(DEFAULT_RESULTS_PATH))

    # Live mode override
    live_group = parser.add_mutually_exclusive_group()
    live_group.add_argument(
        "--live",
        action="store_true",
        help="Force live PR delivery (overrides phase default)",
    )
    live_group.add_argument(
        "--no-live",
        action="store_true",
        help="Force dry-run (overrides phase default)",
    )

    args = parser.parse_args(argv)

    # Load all benchmark cases
    all_cases = load_benchmark_cases()

    # If --phase specified, filter and use phase defaults
    if args.phase:
        filtered_cases, phase_def = filter_cases_by_phase(all_cases, args.phase)
        cases_path_desc = f"Phase {args.phase}: {phase_def.get('name', args.phase)}"

        # Determine live flag
        if args.live:
            live = True
        elif args.no_live:
            live = False
        else:
            live = phase_def.get("live", False)

        # Write filtered cases to temp file
        temp_cases_path = Path(__file__).resolve().parent / f"_temp_{args.phase}_cases.json"
        temp_cases_path.write_text(json.dumps(filtered_cases, indent=2), encoding="utf-8")
        cases_path = temp_cases_path
    else:
        # Direct --cases path
        cases_path = Path(args.cases)
        cases_path_desc = str(cases_path)
        live = args.live or not args.no_live  # Default dry-run

    # Output path with phase name if available
    if args.phase:
        output_path = (
            Path(__file__).resolve().parent
            / "results"
            / f"results_phase_{args.phase}.json"
        )
    else:
        output_path = Path(args.output)

    print(f"📊 Running evaluation: {cases_path_desc}")
    print(f"💾 Results → {output_path}")
    print(f"🔴 Live PR delivery: {live}\n")

    if live:
        response = input("⚠️  WARNING: Live PR delivery is enabled! Continue? (type 'yes'): ")
        if response.strip().lower() != "yes":
            print("Cancelled.")
            return 1

    summary = run_eval(cases_path=cases_path, output_path=output_path, live=live)
    print(json.dumps(summary, indent=2))  # noqa: T201

    # Clean up temp file if created
    if args.phase and temp_cases_path.exists():
        temp_cases_path.unlink()

    return 0


if __name__ == "__main__":
    sys.exit(main())
