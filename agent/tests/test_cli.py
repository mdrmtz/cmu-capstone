from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from langgraph.types import Command

from a11y_fixer import cli, config
from a11y_fixer.adapters.pr.delivery import DryRunResult
from a11y_fixer.deep_agent import ViolationResponse


def test_build_parser_audit_defaults() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["audit"])
    assert args.command == "audit"
    assert args.output


def test_build_parser_run_live_flags() -> None:
    parser = cli.build_parser()
    assert parser.parse_args(["run", "--live"]).live is True
    assert parser.parse_args(["run", "--no-live"]).live is False
    assert parser.parse_args(["run"]).live is None


def test_build_parser_run_rejects_conflicting_live_flags() -> None:
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["run", "--live", "--no-live"])


def test_cmd_audit_writes_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_report = {"total_violation_instances": 3, "pages": [{"url": "/", "violation_rules": ["html-has-lang"]}]}
    monkeypatch.setattr(cli.AxeAuditRunner, "run", lambda self: fake_report)  # noqa: ARG005

    output_path = tmp_path / "audit.json"
    parser = cli.build_parser()
    args = parser.parse_args(["audit", "--output", str(output_path)])

    exit_code = cli._cmd_audit(args)  # noqa: SLF001

    assert exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8")) == fake_report


class _FakeInterrupt:
    def __init__(self, value: dict) -> None:
        self.value = value


async def test_resolve_interrupts_auto_approve_resumes_until_clean() -> None:
    interrupted_result = {"__interrupt__": [_FakeInterrupt({"action_requests": [{"description": "write fix"}]})]}
    final_result = {"messages": [], "structured_response": None}
    graph = MagicMock()
    graph.ainvoke = AsyncMock(return_value=final_result)

    result = await cli.resolve_interrupts(graph, {"configurable": {"thread_id": "t1"}}, interrupted_result, auto_approve=True)

    assert result is final_result
    graph.ainvoke.assert_called_once()
    (call_args, call_kwargs) = graph.ainvoke.call_args
    resumed_command = call_args[0]
    assert isinstance(resumed_command, Command)
    assert resumed_command.resume == {"decisions": [{"type": "approve"}]}


async def test_resolve_interrupts_manual_reject(monkeypatch: pytest.MonkeyPatch) -> None:
    interrupted_result = {"__interrupt__": [_FakeInterrupt({"action_requests": [{"description": "write fix"}]})]}
    final_result = {"messages": [], "structured_response": None}
    graph = MagicMock()
    graph.ainvoke = AsyncMock(return_value=final_result)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "n")

    await cli.resolve_interrupts(graph, {"configurable": {"thread_id": "t1"}}, interrupted_result, auto_approve=False)

    resumed_command = graph.ainvoke.call_args[0][0]
    assert resumed_command.resume["decisions"][0]["type"] == "reject"


async def test_resolve_interrupts_passthrough_when_not_interrupted() -> None:
    final_result = {"messages": [], "structured_response": None}
    graph = MagicMock()
    graph.ainvoke = AsyncMock()

    result = await cli.resolve_interrupts(graph, {}, final_result, auto_approve=True)

    assert result is final_result
    graph.ainvoke.assert_not_called()


def _violation() -> dict:
    return {"rule": "color-contrast", "url": "/product", "selector": ".cta", "html": "<button>Buy</button>"}


def test_deliver_violation_routes_human_to_review_queue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "hitl_queue_dir", lambda: tmp_path / "hitl_queue")
    response = ViolationResponse(
        rule="color-contrast", wcag="1.4.3", selector=".cta", technique_id="G18", technique_type="sufficient",
        code="", rationale="ambiguous background", score=10.0, route="human",
    )

    outcome = cli.deliver_violation(
        _violation(), response, fixture=tmp_path, pr_config=config.PRDeliveryConfig(live=False, github_token=None, github_repo=None),
        output_dir=tmp_path / "prs",
    )

    assert outcome["delivered"] is False
    assert Path(outcome["queue_path"]).exists()


def test_capture_and_reset_git_changes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)  # noqa: S603, S607
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)  # noqa: S603, S607
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)  # noqa: S603, S607
    (repo / "index.html").write_text("<html>\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)  # noqa: S603, S607
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)  # noqa: S603, S607

    (repo / "index.html").write_text('<html lang="en">\n', encoding="utf-8")

    changes = cli._capture_and_reset_git_changes(repo)  # noqa: SLF001

    assert len(changes) == 1
    assert changes[0].path == "index.html"
    assert changes[0].old_content == "<html>\n"
    assert changes[0].new_content == '<html lang="en">\n'
    # working tree reset back to HEAD
    assert (repo / "index.html").read_text(encoding="utf-8") == "<html>\n"


def test_deliver_violation_routes_auto_to_dry_run_pr(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)  # noqa: S603, S607
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)  # noqa: S603, S607
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)  # noqa: S603, S607
    (repo / "index.html").write_text("<html>\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)  # noqa: S603, S607
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)  # noqa: S603, S607
    (repo / "index.html").write_text('<html lang="en">\n', encoding="utf-8")

    response = ViolationResponse(
        rule="html-has-lang", wcag="3.1.1", selector="html", technique_id="H57", technique_type="sufficient",
        code='<html lang="en">', rationale="site-wide language fix", score=20.0, route="auto",
    )
    outcome = cli.deliver_violation(
        {"rule": "html-has-lang", "url": "/", "selector": "html", "html": "<html>"},
        response,
        fixture=repo,
        pr_config=config.PRDeliveryConfig(live=False, github_token=None, github_repo=None),
        output_dir=tmp_path / "prs",
    )

    assert outcome["delivered"] is True
    assert isinstance(outcome["result"], DryRunResult)
    assert outcome["result"].diff_path.exists()


def test_deliver_violation_reports_no_changes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)  # noqa: S603, S607
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)  # noqa: S603, S607
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)  # noqa: S603, S607
    (repo / "index.html").write_text("<html>\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)  # noqa: S603, S607
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)  # noqa: S603, S607

    response = ViolationResponse(
        rule="html-has-lang", wcag="3.1.1", selector="html", technique_id="H57", technique_type="sufficient",
        code="", rationale="no-op", score=0.0, route="auto",
    )
    outcome = cli.deliver_violation(
        {"rule": "html-has-lang", "url": "/", "selector": "html", "html": "<html>"},
        response,
        fixture=repo,
        pr_config=config.PRDeliveryConfig(live=False, github_token=None, github_repo=None),
        output_dir=tmp_path / "prs",
    )

    assert outcome["delivered"] is False
    assert "reason" in outcome


def _audit_report(cases: list[tuple[str, str]]) -> dict:
    """Build a minimal normalized-report payload `flatten_violation_instances` accepts."""
    return {
        "raw_reports": [
            {
                "url": url,
                "violations": [{"id": rule, "tags": [], "nodes": [{"html": f"<{rule}>", "target": [rule], "failureSummary": None}]}],
            }
            for url, rule in cases
        ]
    }


def test_cmd_run_continues_after_one_violation_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps(_audit_report([("/a", "rule-a"), ("/b", "rule-b")])), encoding="utf-8")

    invoked: list[str] = []

    class FakeGraph:
        async def ainvoke(self, messages: dict, config: dict) -> dict:  # noqa: ARG002
            invoked.append(config["configurable"]["thread_id"])
            if len(invoked) == 1:
                msg = "boom"
                raise RuntimeError(msg)
            return {"structured_response": None}

    async def fake_abuild_agent(**_kwargs: object) -> FakeGraph:
        return FakeGraph()

    monkeypatch.setattr("a11y_fixer.deep_agent.abuild_agent", fake_abuild_agent)

    parser = cli.build_parser()
    args = parser.parse_args(["run", "--audit", str(audit_path), "--no-live", "--yes"])

    exit_code = cli._cmd_run(args)  # noqa: SLF001

    assert invoked == ["violation-0", "violation-1"]
    assert exit_code == 1
