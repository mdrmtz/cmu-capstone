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

from a11y_fixer import cli, config
from a11y_fixer.adapters.audit_runner import AxeAuditRunner
from a11y_fixer.domain.guardrail_rules import brier_score, expected_calibration_error

BENCHMARK_CASES_PATH = Path(__file__).resolve().parent / "benchmark_cases.json"
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


def _recheck_cleared(fixture: Path, case: dict) -> bool:
    """Re-run a scoped axe-core audit against just this case's page and check the rule cleared.

    One `ng serve`/axe-core round-trip per case is the simplest correct
    implementation; batching by unique page is a possible future
    optimization if benchmark runtime becomes a bottleneck.
    """
    runner = AxeAuditRunner(fixture_path=fixture)
    report = runner.run(pages=(case["page"],))
    page_report = report["pages"][0] if report["pages"] else {"violation_rules": []}
    return case["rule"] not in page_report["violation_rules"]


async def _run_one_case(
    graph: Any,
    case: dict,
    *,
    pr_config: config.PRDeliveryConfig,
    fixture: Path,
    output_dir: Path,
) -> CaseResult:
    start = time.monotonic()
    thread_config = {"configurable": {"thread_id": case["id"]}}
    message = (
        "Resolve this axe-core violation:\n"
        f"rule: {case['rule']}\n"
        f"page: {case['page']}\n"
        f"selector: {case['selector']}\n"
        f"wcag: {case['wcag']}\n"
        f"ground truth hint: {case['ground_truth_fix']}\n"
    )
    try:
        result = await graph.ainvoke({"messages": [{"role": "user", "content": message}]}, config=thread_config)
        result = await cli.resolve_interrupts(graph, thread_config, result, auto_approve=True)
        response = result.get("structured_response")
        if response is None:
            return CaseResult(
                case_id=case["id"], rule=case["rule"], page=case["page"], route="human",
                rubric_score=0.0, cleared=False, latency_seconds=time.monotonic() - start,
                error="no structured response produced",
            )
        cli.deliver_violation(case, response, fixture=fixture, pr_config=pr_config, output_dir=output_dir)
        cleared = _recheck_cleared(fixture, case)
        return CaseResult(
            case_id=case["id"], rule=case["rule"], page=case["page"], route=response.route,
            rubric_score=response.score, cleared=cleared, latency_seconds=time.monotonic() - start,
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
    results = [
        await _run_one_case(graph, case, pr_config=pr_config, fixture=fixture, output_dir=output_dir) for case in cases
    ]

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
    parser = argparse.ArgumentParser(prog="run_eval")
    parser.add_argument("--cases", default=str(BENCHMARK_CASES_PATH))
    parser.add_argument("--output", default=str(DEFAULT_RESULTS_PATH))
    args = parser.parse_args(argv)

    summary = run_eval(cases_path=Path(args.cases), output_path=Path(args.output), live=False)
    print(json.dumps(summary, indent=2))  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
