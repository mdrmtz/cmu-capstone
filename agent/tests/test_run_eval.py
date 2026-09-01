from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AGENT_ROOT / "evaluation"))

from run_eval import BENCHMARK_CASES_PATH, CaseResult, compute_metrics, load_benchmark_cases  # noqa: E402


def test_benchmark_cases_file_matches_reconciled_ground_truth() -> None:
    cases = load_benchmark_cases()
    assert len(cases) == 22
    rules = {case["rule"] for case in cases}
    assert rules == {"html-has-lang", "color-contrast", "image-alt", "button-name", "link-name"}
    assert all({"id", "page", "rule", "selector", "wcag", "ground_truth_fix"} <= set(case) for case in cases)


def test_load_benchmark_cases_default_path_is_real_file() -> None:
    assert BENCHMARK_CASES_PATH.exists()
    assert json.loads(BENCHMARK_CASES_PATH.read_text(encoding="utf-8"))


def _result(**overrides: object) -> CaseResult:
    defaults = {
        "case_id": "case-01",
        "rule": "html-has-lang",
        "page": "/",
        "route": "auto",
        "rubric_score": 18.0,
        "cleared": True,
        "latency_seconds": 2.0,
        "error": None,
    }
    defaults.update(overrides)
    return CaseResult(**defaults)  # type: ignore[arg-type]


def test_compute_metrics_on_empty_results() -> None:
    assert compute_metrics([]) == {"total_cases": 0}


def test_compute_metrics_all_cleared_perfect_confidence() -> None:
    results = [_result(rubric_score=20.0, cleared=True) for _ in range(4)]
    metrics = compute_metrics(results)
    assert metrics["total_cases"] == 4
    assert metrics["violation_clearance_rate"] == 1.0
    assert metrics["human_escalation_rate"] == 0.0
    assert metrics["error_rate"] == 0.0
    assert metrics["brier_score"] == pytest.approx(0.0)


def test_compute_metrics_mixed_outcomes() -> None:
    results = [
        _result(case_id="c1", rule="html-has-lang", cleared=True, rubric_score=20.0, route="auto"),
        _result(case_id="c2", rule="color-contrast", cleared=False, rubric_score=10.0, route="human"),
        _result(case_id="c3", rule="image-alt", cleared=True, rubric_score=15.0, route="auto"),
        _result(case_id="c4", rule="image-alt", cleared=False, rubric_score=5.0, route="auto", error="build failed"),
    ]
    metrics = compute_metrics(results)

    assert metrics["total_cases"] == 4
    assert metrics["violation_clearance_rate"] == pytest.approx(0.5)
    assert metrics["human_escalation_rate"] == pytest.approx(0.25)
    assert metrics["error_rate"] == pytest.approx(0.25)
    assert metrics["by_rule"]["image-alt"] == {"total": 2, "cleared": 1}
    assert metrics["by_rule"]["html-has-lang"] == {"total": 1, "cleared": 1}


def test_compute_metrics_mean_latency() -> None:
    results = [_result(latency_seconds=1.0), _result(latency_seconds=3.0)]
    assert compute_metrics(results)["mean_latency_seconds"] == pytest.approx(2.0)
