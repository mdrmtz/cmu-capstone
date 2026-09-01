"""CLI entrypoint: the single composition boundary for running the agent.

`audit` runs a fresh axe-core report. `run` drives the deep agent over every
violation in a report (fresh or `--audit <path>`), resolving any HITL
interrupts (every `write_file`/`edit_file` pauses for approval - see
`deep_agent.abuild_agent`), then delivers `route: "auto"` results as a PR (or
dry-run diff, per `--live`/`--no-live`) and queues `route: "human"` results
for review.

Both subcommands accept `--repo <path-or-url>` to point at any Angular repo
instead of the bundled Hallucinate.io fixture - a local path is used as-is,
a git URL is shallow-cloned into `config.repo_cache_dir()`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from langgraph.types import Command

from a11y_fixer import config
from a11y_fixer.adapters.audit_runner import AxeAuditRunner, flatten_violation_instances
from a11y_fixer.adapters.pr import delivery as pr_delivery
from a11y_fixer.adapters.repo_source import resolve_repo_source

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from a11y_fixer.deep_agent import ViolationResponse

DEFAULT_AUDIT_OUTPUT = "evaluation/results/audit.json"


def _apply_repo_override(repo_arg: str | None) -> None:
    """Resolve `--repo` (if given) and point every downstream module at it.

    Reuses the existing `A11Y_FIXTURE_PATH` override that `config.
    fixture_path()` already checks first - no other module needs to know
    about `--repo` at all. Prints the resolved path unconditionally so the
    target repo is always visible to whoever runs the command, not a hidden
    default.
    """
    if repo_arg:
        resolved = resolve_repo_source(repo_arg, cache_dir=config.repo_cache_dir())
        os.environ["A11Y_FIXTURE_PATH"] = str(resolved)
    print(f"target repo: {config.fixture_path()}")  # noqa: T201


def _cmd_audit(args: argparse.Namespace) -> int:
    _apply_repo_override(args.repo)
    runner = AxeAuditRunner(fixture_path=config.fixture_path())
    report = runner.run()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(  # noqa: T201 - CLI output
        f"wrote {report['total_violation_instances']} violation instances "
        f"across {len(report['pages'])} pages to {output_path}"
    )
    return 0


async def resolve_interrupts(
    graph: CompiledStateGraph,
    thread_config: dict[str, Any],
    result: dict[str, Any],
    *,
    auto_approve: bool,
) -> dict[str, Any]:
    """Loop resolving HITL interrupts (see `HumanInTheLoopMiddleware`'s
    `HITLRequest`/`HITLResponse` contract) until the graph run completes.

    Async because the graph's MCP-backed tools are coroutine-only (`langchain-
    mcp-adapters` wraps every MCP tool call in `StructuredTool(coroutine=...)`
    with no sync `func=`) - resuming via sync `graph.invoke()` raises
    `NotImplementedError: StructuredTool does not support sync invocation`
    the moment a subagent actually calls one for real.
    """
    while result.get("__interrupt__"):
        pending = result["__interrupt__"][0].value
        action_requests = pending.get("action_requests", [])
        decisions = []
        for action in action_requests:
            if auto_approve:
                decisions.append({"type": "approve"})
                continue
            print(f"HITL approval needed: {action.get('description', action)}")  # noqa: T201
            answer = input("Approve? [y/N] ").strip().lower()
            decisions.append({"type": "approve"} if answer == "y" else {"type": "reject", "message": "rejected by reviewer"})
        result = await graph.ainvoke(Command(resume={"decisions": decisions}), config=thread_config)
    return result


def _hitl_queue_path(violation: dict) -> Path:
    slug = f"{violation['rule']}-{violation['selector']}"
    slug = "".join(ch if ch.isalnum() else "-" for ch in slug).strip("-") or "violation"
    return config.hitl_queue_dir() / f"{time.time_ns()}-{slug}.json"


def _capture_and_reset_git_changes(fixture: Path) -> list[pr_delivery.FileChange]:
    """Diff the fixture's working tree against HEAD, then reset it.

    Each violation gets its own PR/dry-run branch, so the working tree must
    return to a clean baseline before the next violation runs - otherwise
    violations would contaminate each other's diffs.
    """
    status = subprocess.run(  # noqa: S603, S607
        ["git", "status", "--porcelain"], cwd=fixture, capture_output=True, text=True, check=True
    )
    changed_paths = [line[3:] for line in status.stdout.splitlines() if line.strip()]

    changes = []
    for rel_path in changed_paths:
        file_path = fixture / rel_path
        new_content = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
        old_result = subprocess.run(  # noqa: S603, S607
            ["git", "show", f"HEAD:{rel_path}"], cwd=fixture, capture_output=True, text=True, check=False
        )
        old_content = old_result.stdout if old_result.returncode == 0 else ""
        changes.append(pr_delivery.FileChange(path=rel_path, old_content=old_content, new_content=new_content))

    subprocess.run(["git", "checkout", "--", "."], cwd=fixture, capture_output=True, text=True, check=False)  # noqa: S603, S607
    subprocess.run(["git", "clean", "-fd"], cwd=fixture, capture_output=True, text=True, check=False)  # noqa: S603, S607
    return changes


def deliver_violation(
    violation: dict,
    response: ViolationResponse,
    *,
    fixture: Path,
    pr_config: config.PRDeliveryConfig,
    output_dir: Path,
) -> dict:
    """Route one resolved violation to the human queue or PR delivery."""
    if response.route == "human":
        config.hitl_queue_dir().mkdir(parents=True, exist_ok=True)
        queue_path = _hitl_queue_path(violation)
        queue_path.write_text(
            json.dumps({"violation": violation, "response": response.model_dump()}, indent=2), encoding="utf-8"
        )
        return {"delivered": False, "queue_path": str(queue_path)}

    changes = _capture_and_reset_git_changes(fixture)
    if not changes:
        return {"delivered": False, "reason": "codebase_compiler made no file changes"}

    plan = pr_delivery.PullRequestPlan(
        title=f"a11y-fixer: fix {violation['rule']} ({violation['selector']})",
        body=response.rationale,
        branch_name=f"a11y-fixer/{violation['rule']}-{int(time.time())}",
        changes=changes,
    )
    result = pr_delivery.deliver(plan, config=pr_config, output_dir=output_dir)
    return {"delivered": True, "result": result}


async def _acmd_run(args: argparse.Namespace) -> int:
    from a11y_fixer.deep_agent import abuild_agent  # noqa: PLC0415 - deferred: avoid MCP/network cost for --help etc.

    _apply_repo_override(args.repo)

    if args.audit:
        report = json.loads(Path(args.audit).read_text(encoding="utf-8"))
    else:
        report = AxeAuditRunner(fixture_path=config.fixture_path()).run()

    violations = flatten_violation_instances(report)
    if not violations:
        print("no violations found - nothing to do")  # noqa: T201
        return 0

    pr_config = config.resolve_pr_delivery(args.live)
    fixture = config.fixture_path()
    output_dir = config.agent_root() / "evaluation" / "results" / "prs"

    graph = await abuild_agent()

    failures = 0
    for index, violation in enumerate(violations):
        thread_config = {"configurable": {"thread_id": f"violation-{index}"}}
        message = (
            "Resolve this axe-core violation:\n"
            f"rule: {violation['rule']}\n"
            f"page: {violation['url']}\n"
            f"selector: {violation['selector']}\n"
            f"html: {violation['html']}\n"
            f"failure_summary: {violation.get('failure_summary')}\n"
        )
        try:
            result = await graph.ainvoke({"messages": [{"role": "user", "content": message}]}, config=thread_config)
            result = await resolve_interrupts(graph, thread_config, result, auto_approve=args.yes)

            response = result.get("structured_response")
            if response is None:
                print(f"[{violation['rule']}] no structured response produced - skipping")  # noqa: T201
                continue

            outcome = deliver_violation(violation, response, fixture=fixture, pr_config=pr_config, output_dir=output_dir)
            print(f"[{violation['rule']}] {outcome}")  # noqa: T201
        except Exception as exc:  # noqa: BLE001 - one violation's failure must not abort the rest of the batch
            failures += 1
            print(f"[{violation['rule']}] FAILED: {type(exc).__name__}: {exc}")  # noqa: T201

    if failures:
        print(f"{failures}/{len(violations)} violation(s) failed")  # noqa: T201
    return 1 if failures else 0


def _cmd_run(args: argparse.Namespace) -> int:
    return asyncio.run(_acmd_run(args))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="a11y-fixer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser("audit", help="Run a full axe-core audit against the fixture")
    audit_parser.add_argument("--output", default=str(config.agent_root() / DEFAULT_AUDIT_OUTPUT))
    audit_parser.add_argument(
        "--repo",
        default=None,
        help="Local path or git URL of the Angular repo to audit (default: the bundled Hallucinate.io fixture)",
    )
    audit_parser.set_defaults(func=_cmd_audit)

    run_parser = subparsers.add_parser("run", help="Run the deep agent over every violation in an audit report")
    run_parser.add_argument("--audit", default=None, help="Path to a normalized audit JSON; runs a fresh audit if omitted")
    run_parser.add_argument(
        "--repo",
        default=None,
        help="Local path or git URL of the Angular repo to fix (default: the bundled Hallucinate.io fixture)",
    )
    run_parser.add_argument("--yes", action="store_true", help="Auto-approve every HITL interrupt (non-interactive)")
    live_group = run_parser.add_mutually_exclusive_group()
    live_group.add_argument("--live", dest="live", action="store_true", default=None, help="Force live PR delivery")
    live_group.add_argument("--no-live", dest="live", action="store_false", help="Force dry-run delivery")
    run_parser.set_defaults(func=_cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
