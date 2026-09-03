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
DEFAULT_RESULTS_PATH = (
    Path(__file__).resolve().parent / "results" / "results_summary.json"
)


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
    scoring_details: dict | None = None  # Per-criterion breakdown from qa_critic


def load_benchmark_cases(path: Path = BENCHMARK_CASES_PATH) -> list[dict]:
    """Load benchmark test cases from JSON file.
    
    On fresh systems where evaluation/benchmark_cases.json doesn't exist yet,
    returns an empty list. This allows the application and tests to work
    without requiring the file to be pre-generated or version-controlled.
    
    Args:
        path: Path to benchmark_cases.json (defaults to evaluation/benchmark_cases.json)
    
    Returns:
        List of benchmark case dictionaries, or empty list if file doesn't exist
    """
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def load_phases(path: Path = PHASES_PATH) -> dict[str, dict]:
    """Load phase definitions from phases.yaml."""
    if not path.exists():
        raise FileNotFoundError(f"phases.yaml not found at {path}")
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("phases", {})


def _case_number(case_id: str) -> int:
    """Extract the numeric suffix from a `case-NN` id, e.g. `"case-05"` -> `5`."""
    return int(case_id.rsplit("-", 1)[-1])


def _matches_filter(case: dict, filter_spec: dict) -> bool:
    """A case matches a filter by page+wcag, a case-id range, or an explicit case-id list."""
    if "case_ids" in filter_spec:
        return case["id"] in filter_spec["case_ids"]
    if "case_from" in filter_spec or "case_to" in filter_spec:
        case_from, case_to = filter_spec.get("case_from"), filter_spec.get("case_to")
        n = _case_number(case["id"])
        if case_from is not None and n < _case_number(case_from):
            return False
        return not (case_to is not None and n > _case_number(case_to))
    return case.get("page") == filter_spec.get("page") and case.get(
        "wcag"
    ) == filter_spec.get("wcag")


def filter_cases_by_phase(
    cases: list[dict], phase_name: str
) -> tuple[list[dict], dict]:
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
            if _matches_filter(case, filter_spec):
                filtered.append(case)
                break  # Don't add duplicates

    return filtered, phase_def


def filter_cases_by_range(
    cases: list[dict], case_from: str | None, case_to: str | None
) -> list[dict]:
    """Filter benchmark cases to an inclusive `case-NN` id range, for ad-hoc
    end-to-end runs (e.g. `--case-from case-01 --case-to case-05`) without
    needing a named entry in phases.yaml.
    """
    return [
        case
        for case in cases
        if _matches_filter(case, {"case_from": case_from, "case_to": case_to})
    ]


def filter_cases_by_ids(cases: list[dict], case_ids: list[str]) -> list[dict]:
    """Filter benchmark cases to an explicit, possibly non-contiguous list of
    case ids (e.g. case-01, case-04, case-15) - order follows `cases`, a
    requested id with no matching case is simply absent from the result.
    """
    return [case for case in cases if _matches_filter(case, {"case_ids": case_ids})]


def _confidence(result: CaseResult) -> float:
    """Normalize a case's 0-20 rubric score to a [0, 1] confidence for calibration math."""
    return max(0.0, min(1.0, result.rubric_score / 20.0))


def _group_clearance_by_rule(results: list[CaseResult]) -> dict[str, dict]:
    by_rule: dict[str, list[CaseResult]] = {}
    for result in results:
        by_rule.setdefault(result.rule, []).append(result)
    return {
        rule: {"total": len(rs), "cleared": sum(1 for r in rs if r.cleared)}
        for rule, rs in by_rule.items()
    }


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
    runner: AxeAuditRunner | None,
    p_ik_floor: float | None = None,
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
    CASE_TIMEOUT_SECONDS = 300  # 5-minute hard cap per case to prevent credit runaway
    try:
        for attempt in range(MAX_ATTEMPTS):
            thread_config = {
                "configurable": {
                    "thread_id": f"{case['id']}-attempt{attempt + 1}",
                    "recursion_limit": 50,
                }
            }
            try:
                result = await asyncio.wait_for(
                    graph.ainvoke(
                        {"messages": [{"role": "user", "content": message}]},
                        config=thread_config,
                    ),
                    timeout=CASE_TIMEOUT_SECONDS,
                )
                result = await cli.resolve_interrupts(
                    graph, thread_config, result, auto_approve=True
                )
                response = result.get("structured_response")

                # Only retry if structured_response is None; other errors don't retry
                if response is None:
                    if attempt < MAX_ATTEMPTS - 1:
                        continue  # Try again with fresh thread_id
                    # All retries exhausted
                    return CaseResult(
                        case_id=case["id"],
                        rule=case["rule"],
                        page=case["page"],
                        route="human",
                        rubric_score=0.0,
                        cleared=False,
                        latency_seconds=time.monotonic() - start,
                        error="no structured response produced after retries",
                    )

                # Successfully got a response
                cli.warn_on_overconfidence(case["id"], response.rationale)
                # FIX: Check clearance BEFORE fixture reset. deliver_violation() calls
                # _capture_and_reset_git_changes() which reverts all code changes, so the
                # violation recheck must happen while the fix is still applied.
                # In worktree mode runner=None: skip axe recheck (worktree is torn down after); cleared=False conservative default
                cleared = _recheck_cleared(runner, case) if runner is not None else False
                outcome = cli.deliver_violation(
                    case,
                    response,
                    fixture=fixture,
                    pr_config=pr_config,
                    output_dir=output_dir,
                    p_ik_floor=p_ik_floor,
                )
                return CaseResult(
                    case_id=case["id"],
                    rule=case["rule"],
                    page=case["page"],
                    route=outcome["route"],
                    rubric_score=response.score,
                    cleared=cleared,
                    latency_seconds=time.monotonic() - start,
                    scoring_details=response.scoring_details,
                )
            except asyncio.TimeoutError:
                return CaseResult(
                    case_id=case["id"],
                    rule=case["rule"],
                    page=case["page"],
                    route="human",
                    rubric_score=0.0,
                    cleared=False,
                    latency_seconds=time.monotonic() - start,
                    error=f"case timed out after {CASE_TIMEOUT_SECONDS}s",
                )
            except (
                Exception
            ) as exc:  # noqa: BLE001 - one case's failure must not abort the whole benchmark run
                return CaseResult(
                    case_id=case["id"],
                    rule=case["rule"],
                    page=case["page"],
                    route="human",
                    rubric_score=0.0,
                    cleared=False,
                    latency_seconds=time.monotonic() - start,
                    error=str(exc),
                )
    finally:
        # FIX: Always reset fixture state, even on error/timeout
        # Idempotent: safe to call even if already reset by deliver_violation()
        try:
            cli._capture_and_reset_git_changes(fixture)
        except Exception:
            pass  # Ignore cleanup errors


def _save_observability_logs(
    results: list[CaseResult], phase_name: str = "all"
) -> Path:
    """Save detailed observability logs to observability/log/ folder.

    Creates:
    - scores_breakdown.json: Per-criterion scoring details for analysis
    - metrics_summary.json: Phase-level metrics and calibration info
    """
    import datetime

    log_dir = config.agent_root() / "observability" / "log"
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Build detailed breakdown with all scoring info
    scores_breakdown = {
        "phase": phase_name,
        "timestamp": timestamp,
        "total_cases": len(results),
        "cases": [],
    }

    for result in results:
        case_log = {
            "case_id": result.case_id,
            "rule": result.rule,
            "page": result.page,
            "rubric_score": result.rubric_score,
            "cleared": result.cleared,
            "route": result.route,
            "latency_seconds": result.latency_seconds,
            "error": result.error,
        }

        # Include detailed scoring breakdown if available
        if result.scoring_details:
            case_log["scoring_details"] = result.scoring_details

        scores_breakdown["cases"].append(case_log)

    # Save scoring breakdown
    scores_file = log_dir / f"scores-breakdown-{phase_name}.json"
    scores_file.write_text(json.dumps(scores_breakdown, indent=2), encoding="utf-8")
    print(
        f"📊 Observability: Saved scoring breakdown to {scores_file.relative_to(config.agent_root())}"
    )  # noqa: T201

    # Save metrics summary
    metrics_summary = {
        "phase": phase_name,
        "timestamp": timestamp,
        "summary": compute_metrics(results),
        "cases_by_route": {
            "auto": len([r for r in results if r.route == "auto"]),
            "human": len([r for r in results if r.route == "human"]),
        },
        "cases_by_error": {
            "cleared": len([r for r in results if r.cleared]),
            "errored": len([r for r in results if r.error is not None]),
            "pending_review": len(
                [r for r in results if not r.cleared and r.error is None]
            ),
        },
    }

    metrics_file = log_dir / f"metrics-summary-{phase_name}.json"
    metrics_file.write_text(json.dumps(metrics_summary, indent=2), encoding="utf-8")
    print(
        f"📊 Observability: Saved metrics summary to {metrics_file.relative_to(config.agent_root())}"
    )  # noqa: T201

    return log_dir


async def _arun_eval(
    *,
    cases_path: Path = BENCHMARK_CASES_PATH,
    output_path: Path = DEFAULT_RESULTS_PATH,
    live: bool | None = False,
    use_worktree: bool = False,
) -> dict[str, Any]:
    from a11y_fixer.deep_agent import (
        abuild_agent,
        abuild_graph,
        aresolve_tools,
    )  # noqa: PLC0415 - deferred: keeps compute_metrics importable with no MCP/network cost

    cases = load_benchmark_cases(cases_path)
    pr_config = config.resolve_pr_delivery(live)
    fixture = config.fixture_path()
    output_dir = config.agent_root() / "evaluation" / "results" / "prs"

    # FIX 2: Load calibrated P(IK) floor from previous Phase 2 results (if available)
    # This threads calibration through for Phase 4 validation
    p_ik_floor = None
    if output_path.exists():
        try:
            results_data = json.loads(output_path.read_text(encoding="utf-8"))
            p_ik_floor = results_data.get("calibrated_p_ik_floor")
            if p_ik_floor is not None:
                print(
                    f"📊 Loaded calibrated P(IK) floor: {p_ik_floor:.3f} from previous Phase 2 results"
                )  # noqa: T201
        except Exception:  # noqa: BLE001
            pass  # Ignore if results file malformed

    if use_worktree:
        # Worktree mode: resolve MCP tools once, then per-case isolated worktree
        # prevents fixture bleed between cases. Axe re-audit skipped (runner=None)
        # because each worktree is torn down after its case finishes.
        from a11y_fixer.adapters.sandbox.git_worktree import (  # noqa: PLC0415
            create_worktree,
            remove_worktree,
        )

        print("🌲 Worktree mode: one isolated git worktree per benchmark case")  # noqa: T201
        resolved = await aresolve_tools()
        results = []
        for case in cases:
            branch_name = f"a11y-fixer/{case['id']}"
            worktree = create_worktree(
                config.repo_root(),
                base_dir=config.repo_root(),
                branch_name=branch_name,
                link_dirs=("Hallucinate.io/node_modules",),
            )
            try:
                wt_fixture = worktree.path / "Hallucinate.io"
                graph = abuild_graph(resolved, fixture_path=wt_fixture)
                result = await _run_one_case(
                    graph,
                    case,
                    pr_config=pr_config,
                    fixture=wt_fixture,
                    output_dir=output_dir,
                    runner=None,  # No axe recheck in worktree mode
                    p_ik_floor=p_ik_floor,
                )
            finally:
                remove_worktree(worktree)
            results.append(result)
    else:
        graph = await abuild_agent()

        # Start server once for all cases to reuse browser session across cases
        runner = AxeAuditRunner(fixture_path=fixture)
        runner.start_server()
        try:
            results = [
                await _run_one_case(
                    graph,
                    case,
                    pr_config=pr_config,
                    fixture=fixture,
                    output_dir=output_dir,
                    runner=runner,
                    p_ik_floor=p_ik_floor,
                )
                for case in cases
            ]
        finally:
            runner.stop_server()

    summary = compute_metrics(results)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps({"summary": summary, "cases": [vars(r) for r in results]}, indent=2),
        encoding="utf-8",
    )

    # Save detailed observability logs
    phase_name = output_path.stem.replace("results_", "").replace("_summary", "")
    _save_observability_logs(results, phase_name=phase_name)

    return summary


def run_eval(
    *,
    cases_path: Path = BENCHMARK_CASES_PATH,
    output_path: Path = DEFAULT_RESULTS_PATH,
    live: bool | None = False,
    use_worktree: bool = False,
) -> dict[str, Any]:
    return asyncio.run(
        _arun_eval(
            cases_path=cases_path,
            output_path=output_path,
            live=live,
            use_worktree=use_worktree,
        )
    )


def _resolve_phase(
    args: argparse.Namespace, all_cases: list[dict]
) -> tuple[Path, str, bool] | None:
    """Resolve `--phase` into `(cases_path, description, live)`.

    Returns `None` if the phase matched zero cases - the caller should print
    an error and exit rather than build the whole agent for nothing.
    """
    filtered_cases, phase_def = filter_cases_by_phase(all_cases, args.phase)
    if not filtered_cases:
        print(f"phase '{args.phase}' matched 0 cases - nothing to run")  # noqa: T201
        return None

    expected_count = phase_def.get("cases_count")
    if expected_count is not None and len(filtered_cases) != expected_count:
        print(  # noqa: T201
            f"warning: phase '{args.phase}' expected {expected_count} cases but filters "
            f"matched {len(filtered_cases)} - benchmark_cases.json may have changed"
        )

    # live:true in phases.yaml is only a default, not sufficient on its own - --live must be explicit.
    if args.live:
        live = True
    elif args.no_live:
        live = False
    elif phase_def.get("live", False):
        print(  # noqa: T201
            f"phase '{args.phase}' is configured for live delivery - defaulting "
            f"to dry-run anyway; pass --live to confirm"
        )
        live = False
    else:
        live = False

    temp_cases_path = Path(__file__).resolve().parent / f"_temp_{args.phase}_cases.json"
    temp_cases_path.write_text(json.dumps(filtered_cases, indent=2), encoding="utf-8")
    cases_path_desc = f"Phase {args.phase}: {phase_def.get('name', args.phase)}"
    return temp_cases_path, cases_path_desc, live


def _resolve_case_range(
    args: argparse.Namespace, all_cases: list[dict]
) -> tuple[Path, str, bool] | None:
    """Resolve `--case-from`/`--case-to` into `(cases_path, description, live)`,
    for an ad-hoc end-to-end range that has no named entry in phases.yaml.

    Returns `None` if the range matched zero cases.
    """
    filtered_cases = filter_cases_by_range(all_cases, args.case_from, args.case_to)
    if not filtered_cases:
        print(
            f"case range {args.case_from!r} to {args.case_to!r} matched 0 cases"
        )  # noqa: T201
        return None

    label = f"{args.case_from or 'case-01'} to {args.case_to or 'case-22'}"
    temp_cases_path = Path(__file__).resolve().parent / "_temp_case_range_cases.json"
    temp_cases_path.write_text(json.dumps(filtered_cases, indent=2), encoding="utf-8")
    return temp_cases_path, f"Cases {label}", args.live


def _resolve_case_ids(
    args: argparse.Namespace, all_cases: list[dict]
) -> tuple[Path, str, bool] | None:
    """Resolve `--case-ids` into `(cases_path, description, live)`, for an
    explicit, possibly non-contiguous list (e.g. case-01,case-04,case-15).

    Returns `None` if none of the requested ids matched a real case.
    """
    requested = [
        case_id.strip() for case_id in args.case_ids.split(",") if case_id.strip()
    ]
    filtered_cases = filter_cases_by_ids(all_cases, requested)

    found_ids = {case["id"] for case in filtered_cases}
    missing = [case_id for case_id in requested if case_id not in found_ids]
    if missing:
        print(
            f"warning: requested case id(s) not found, skipping: {', '.join(missing)}"
        )  # noqa: T201

    if not filtered_cases:
        print(
            f"none of the requested case ids matched a real case: {args.case_ids}"
        )  # noqa: T201
        return None

    temp_cases_path = Path(__file__).resolve().parent / "_temp_case_ids_cases.json"
    temp_cases_path.write_text(json.dumps(filtered_cases, indent=2), encoding="utf-8")
    return temp_cases_path, f"Cases {', '.join(sorted(found_ids))}", args.live


def _resolve_run_target(
    args: argparse.Namespace, all_cases: list[dict]
) -> tuple[Path, str, bool, bool] | None:
    """Resolve which cases to run: `--case-ids`, `--case-from`/`--case-to`, `--phase`, or `--cases`.

    Returns `(cases_path, description, live, uses_temp_file)`, or `None` if
    the caller should print an error and exit (conflicting flags, or a
    filter matched 0 cases).
    """
    ad_hoc_modes = [
        bool(args.case_ids),
        bool(args.case_from or args.case_to),
        bool(args.phase),
    ]
    if sum(ad_hoc_modes) > 1:
        print(
            "--case-ids, --case-from/--case-to, and --phase are mutually exclusive"
        )  # noqa: T201
        return None

    if args.case_ids:
        resolved = _resolve_case_ids(args, all_cases)
        return (*resolved, True) if resolved else None
    if args.case_from or args.case_to:
        resolved = _resolve_case_range(args, all_cases)
        return (*resolved, True) if resolved else None
    if args.phase:
        resolved = _resolve_phase(args, all_cases)
        return (*resolved, True) if resolved else None

    cases_path = Path(args.cases)
    return cases_path, str(cases_path), args.live, False


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
  # (phase defaults to live, but --live must still be passed explicitly)
  python -m evaluation.run_eval --phase f3 --live

  # Override live default: force dry-run for phase f3
  python -m evaluation.run_eval --phase f3 --no-live

  # Ad-hoc end-to-end range, no phases.yaml entry needed
  python -m evaluation.run_eval --case-from case-01 --case-to case-10

  # Explicit, non-contiguous list of cases (unknown ids are skipped with a warning)
  python -m evaluation.run_eval --case-ids case-01,case-04,case-08,case-15,case-22

  # Single case, or every case, without editing phases.yaml
  python -m evaluation.run_eval --phase smoke
  python -m evaluation.run_eval --phase all
        """,
    )

    # Mutually exclusive group for phase vs. direct cases path
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--phase",
        help="Phase name (f1, f2, f3, smoke, all, ...) — reads filters from phases.yaml",
    )
    group.add_argument(
        "--cases",
        default=str(BENCHMARK_CASES_PATH),
        help="Path to benchmark_cases.json (default: %(default)s)",
    )
    parser.add_argument(
        "--case-from",
        default=None,
        help="Start of an inclusive case-id range, e.g. case-01 (ad-hoc, no phases.yaml entry needed)",
    )
    parser.add_argument(
        "--case-to",
        default=None,
        help="End of an inclusive case-id range, e.g. case-10",
    )
    parser.add_argument(
        "--case-ids",
        default=None,
        help="Comma-separated, possibly non-contiguous case ids, e.g. case-01,case-04,case-15",
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
    parser.add_argument(
        "--worktree",
        action="store_true",
        default=False,
        help=(
            "Run each case in an isolated git worktree so fixture changes never "
            "bleed across cases. MCP tools are resolved once; axe re-audit is "
            "skipped (worktree is torn down after each case)."
        ),
    )

    args = parser.parse_args(argv)

    # Load all benchmark cases
    all_cases = load_benchmark_cases()

    resolved = _resolve_run_target(args, all_cases)
    if resolved is None:
        return 1
    cases_path, cases_path_desc, live, uses_temp_file = resolved

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
        response = input(
            "⚠️  WARNING: Live PR delivery is enabled! Continue? (type 'yes'): "
        )
        if response.strip().lower() != "yes":
            print("Cancelled.")
            return 1

    summary = run_eval(cases_path=cases_path, output_path=output_path, live=live, use_worktree=args.worktree)
    print(json.dumps(summary, indent=2))  # noqa: T201

    # Clean up temp file if created
    if uses_temp_file and cases_path.exists():
        cases_path.unlink()

    return 0


if __name__ == "__main__":
    sys.exit(main())
