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
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlparse

from langgraph.types import Command

from a11y_fixer import config
from a11y_fixer.adapters.audit_runner import AxeAuditRunner, flatten_violation_instances
from a11y_fixer.adapters.pr import delivery as pr_delivery
from a11y_fixer.adapters.pr.github_pr_manager import GitHubPRManager
from a11y_fixer.adapters.repo_source import resolve_repo_source
from a11y_fixer.adapters.violation_store import PrePipelineGate, ViolationStore
from a11y_fixer.domain.guardrail_rules import (
    check_confidence_calibration,
    epistemic_gate,
    validate_raw_axe_reports,
    validate_write_path,
)
from a11y_fixer.domain.hitl_policy import assess_risk
from a11y_fixer.domain.violations import (
    compute_violation_id,
    ViolationStatus,
    ViolationState,
)

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
    if args.url:
        report = asyncio.run(_audit_live_url(args.url))
    else:
        from a11y_fixer.agents import (
            audit_crawler,
        )  # noqa: PLC0415 - deferred: avoid MCP/network cost for --help etc.

        _apply_repo_override(args.repo)
        runner = AxeAuditRunner(fixture_path=config.fixture_path())
        report = (
            runner.run()
            if config.is_default_fixture()
            else asyncio.run(audit_crawler.discover_and_audit(runner))
        )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(  # noqa: T201 - CLI output
        f"wrote {report['total_violation_instances']} violation instances "
        f"across {len(report['pages'])} pages to {output_path}"
    )
    return 0


async def _audit_live_url(url: str) -> dict:
    """Audit-only path for `--url`: no clone, no build, no `ng serve` - just
    discover real routes at the given live URL and scan them directly.

    Falls back to auditing just the one given URL if discovery finds
    nothing - `DEFAULT_PAGES` is Hallucinate.io-specific and would be wrong
    for an arbitrary external site.
    """
    from a11y_fixer.agents import (
        audit_crawler,
    )  # noqa: PLC0415 - deferred: avoid MCP/network cost for --help etc.

    routes = await audit_crawler.discover_routes(url)
    urls = [urljoin(url, route) for route in routes] if routes else [url]
    runner = AxeAuditRunner(fixture_path=config.repo_root())
    return runner.audit_urls(urls)


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
            print(
                f"HITL approval needed: {action.get('description', action)}"
            )  # noqa: T201
            answer = input("Approve? [y/N] ").strip().lower()
            decisions.append(
                {"type": "approve"}
                if answer == "y"
                else {"type": "reject", "message": "rejected by reviewer"}
            )
        result = await graph.ainvoke(
            Command(resume={"decisions": decisions}), config=thread_config
        )
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
        ["git", "status", "--porcelain"],
        cwd=fixture,
        capture_output=True,
        text=True,
        check=True,
    )
    changed_paths = [line[3:] for line in status.stdout.splitlines() if line.strip()]

    changes = []
    for rel_path in changed_paths:
        file_path = fixture / rel_path
        new_content = (
            file_path.read_text(encoding="utf-8") if file_path.exists() else ""
        )
        old_result = subprocess.run(  # noqa: S603, S607
            ["git", "show", f"HEAD:{rel_path}"],
            cwd=fixture,
            capture_output=True,
            text=True,
            check=False,
        )
        old_content = old_result.stdout if old_result.returncode == 0 else ""
        changes.append(
            pr_delivery.FileChange(
                path=rel_path, old_content=old_content, new_content=new_content
            )
        )

    subprocess.run(
        ["git", "checkout", "--", "."],
        cwd=fixture,
        capture_output=True,
        text=True,
        check=False,
    )  # noqa: S603, S607
    subprocess.run(
        ["git", "clean", "-fd"],
        cwd=fixture,
        capture_output=True,
        text=True,
        check=False,
    )  # noqa: S603, S607
    return changes


def deliver_violation(
    violation: dict,
    response: ViolationResponse,
    *,
    fixture: Path,
    pr_config: config.PRDeliveryConfig,
    output_dir: Path,
) -> dict:
    """Route one resolved violation to the human queue or PR delivery.

    Captures (and resets) the fixture's git diff unconditionally, before the
    route is decided - codebase_compiler's writes happen during graph
    invocation, before this function is ever called, so the human path must
    reset the working tree too or a queued violation's diff would
    contaminate the next violation.
    """
    changes = _capture_and_reset_git_changes(fixture)
    if not changes:
        return {
            "delivered": False,
            "reason": "codebase_compiler made no file changes",
            "route": response.route,
        }

    path_violations = []
    for change in changes:
        _, reason = validate_write_path(change.path, root=fixture)
        if reason is not None:
            path_violations.append(f"{change.path}: {reason}")

    p_ik = max(0.0, min(1.0, response.score / 20.0))
    gate = epistemic_gate(p_ik)
    assessments = [
        assess_risk(
            rule=violation["rule"],
            file_path=change.path,
            rubric_score=response.score,
            p_ik=p_ik,
        )
        for change in changes
    ]
    # Every guardrail signal may only escalate the model's own call, never downgrade it.
    route = (
        "human"
        if response.route == "human"
        or path_violations
        or gate["verdict"] == "BLOCK"
        or any(a.route == "human" for a in assessments)
        else "auto"
    )

    if route == "human":
        config.hitl_queue_dir().mkdir(parents=True, exist_ok=True)
        queue_path = _hitl_queue_path(violation)
        queue_path.write_text(
            json.dumps(
                {
                    "violation": violation,
                    "response": response.model_dump(),
                    "risk_assessments": [vars(a) for a in assessments],
                    "epistemic_gate": gate,
                    "path_violations": path_violations,
                    "changes": [vars(change) for change in changes],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return {"delivered": False, "queue_path": str(queue_path), "route": route}

    # NEW: Task 2.1-2.3 - Compute violation ID and solution hash for tracking
    violation_id = compute_violation_id(violation["rule"], violation["selector"])
    solution_hash = hashlib.sha256(response.code.encode("utf-8")).hexdigest()[:12]

    # NEW: Task 2.2 - Build PR title with violation ID tag
    title = f"a11y-fixer: fix {violation['rule']} ({violation['selector']}) [violation-{violation_id}]"

    # NEW: Task 2.3 - Build branch name with violation ID
    branch_name = f"a11y-fixer/{violation_id}"

    # NEW: Task 2.3 - Enhance PR body with violation metadata
    body = (
        f"{response.rationale}\n\n"
        f"---\n\n"
        f"**Violation Metadata** (Phase 0.2 Tracking)\n"
        f"- Violation ID: `{violation_id}`\n"
        f"- Rule: {violation['rule']}\n"
        f"- Selector: `{violation['selector']}`\n"
        f"- Solution Hash: `{solution_hash}`\n"
        f"- Score: {response.score}/20\n"
    )

    plan = pr_delivery.PullRequestPlan(
        title=title,
        body=body,
        branch_name=branch_name,
        changes=changes,
    )
    result = pr_delivery.deliver(plan, config=pr_config, output_dir=output_dir)

    # NEW: Task 3.2-3.4 - Auto-merge and dedup cleanup (only in live mode)
    if pr_config.github_token and result and isinstance(result, pr_delivery.LiveResult):
        # Task 3.2: Attempt auto-merge if score is high enough
        pr_number = result.pull_request_number
        auto_merge_threshold = 18.0
        if response.score >= auto_merge_threshold:
            try:
                pr_mgr = GitHubPRManager(
                    github_token=pr_config.github_token,
                    github_repo=pr_config.github_repo,
                )
                merge_result = pr_mgr.auto_merge_pr(
                    pr_number, response.score, threshold=auto_merge_threshold
                )
                print(f"  ✅ Auto-merged PR {pr_number}: {merge_result}")  # noqa: T201

                # Task 3.3: Close duplicate PRs if merge succeeded
                if merge_result.get("merged"):
                    dup_result = pr_mgr.cleanup_duplicate_prs(
                        violation_id, kept_pr_number=pr_number
                    )
                    if dup_result.get("closed_duplicates"):
                        print(
                            f"  🧹 Closed {len(dup_result['closed_duplicates'])} duplicate PRs"
                        )  # noqa: T201
            except Exception as exc:  # noqa: BLE001
                print(f"  ⚠️  Auto-merge/cleanup failed: {exc}")  # noqa: T201
        else:
            print(
                f"  ⏸️  Score {response.score} < threshold {auto_merge_threshold}, PR held for review"
            )  # noqa: T201

    return {"delivered": True, "result": result, "route": route}


def warn_on_overconfidence(context: str, rationale: str) -> None:
    """Print a warning if `rationale` trips the overconfidence-marker scanner.

    Shared by the live CLI and the offline eval harness so both surfaces flag
    the same fabrication-prone language, not just build/test/route failures.
    """
    calibration = check_confidence_calibration(rationale)
    if calibration["verdict"] == "PASS":
        return
    markers = ", ".join(
        marker for marker, _context, _alt in calibration["flagged_phrases"]
    )
    print(
        f"[{context}] confidence-calibration {calibration['verdict']} (markers: {markers})"
    )  # noqa: T201


def _filter_violations_by_case_ids(
    violations: list[dict], case_ids: str | None
) -> list[dict]:
    """Filter violations to only those matching benchmark case IDs (if provided).

    If `--case-ids case-01,case-03` is given, loads benchmark_cases.json and
    filters violations to only those in those cases. Returns all violations
    if case_ids is None.
    """
    if case_ids is None:
        return violations

    # Load benchmark cases and build a set of (rule, page, selector) tuples to match
    benchmark_path = config.agent_root() / "evaluation" / "benchmark_cases.json"
    if not benchmark_path.exists():
        print(
            f"warning: benchmark_cases.json not found at {benchmark_path}; skipping case filtering"
        )  # noqa: T201
        return violations

    try:
        benchmark_cases = json.loads(benchmark_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(
            f"warning: failed to load benchmark_cases.json: {exc}; skipping case filtering"
        )  # noqa: T201
        return violations

    requested_case_ids = {c.strip() for c in case_ids.split(",")}
    target_specs = set()
    for case in benchmark_cases:
        if case.get("id") in requested_case_ids:
            target_specs.add((case.get("rule"), case.get("page"), case.get("selector")))

    if not target_specs:
        print(
            f"warning: no benchmark cases matched {requested_case_ids}; returning all violations"
        )  # noqa: T201
        return violations

    filtered = [
        v
        for v in violations
        if (
            v.get("rule"),
            urlparse(v.get("url", "")).path or "/",
            v.get("selector"),
        )
        in target_specs
    ]
    print(
        f"filtered {len(violations)} violations → {len(filtered)} matching case IDs {requested_case_ids}"
    )  # noqa: T201
    return filtered


async def _acmd_run(args: argparse.Namespace) -> int:
    from a11y_fixer.agents import (
        audit_crawler,
    )  # noqa: PLC0415 - deferred: avoid MCP/network cost for --help etc.
    from a11y_fixer.deep_agent import (
        abuild_agent,
    )  # noqa: PLC0415 - deferred: avoid MCP/network cost for --help etc.

    _apply_repo_override(args.repo)

    if args.audit:
        report = json.loads(Path(args.audit).read_text(encoding="utf-8"))
        validation_error = validate_raw_axe_reports(report.get("raw_reports", []))
        if validation_error is not None:
            print(
                f"invalid audit report {args.audit}: {validation_error}"
            )  # noqa: T201
            return 2
    elif config.is_default_fixture():
        report = AxeAuditRunner(fixture_path=config.fixture_path()).run()
    else:
        report = await audit_crawler.discover_and_audit(
            AxeAuditRunner(fixture_path=config.fixture_path())
        )

    violations = flatten_violation_instances(report)
    if not violations:
        print("no violations found - nothing to do")  # noqa: T201
        return 0

    # NEW: Filter by case IDs if --case-ids provided
    violations = _filter_violations_by_case_ids(violations, args.case_ids)
    if not violations:
        print("no violations after filtering by case IDs")  # noqa: T201
        return 0

    pr_config = config.resolve_pr_delivery(args.live)
    fixture = config.fixture_path()
    output_dir = config.agent_root() / "evaluation" / "results" / "prs"

    # NEW: Initialize Phase 0.2 violation tracking
    store = ViolationStore(status_file=config.agent_root() / ".violation_status.json")
    gate = PrePipelineGate(store)
    metrics = {
        "processed": 0,
        "skipped": 0,
        "created": 0,
        "replaced": 0,
    }

    graph = await abuild_agent()

    failures = 0
    for index, violation in enumerate(violations):
        # NEW: Check PrePipelineGate FIRST
        violation_id = compute_violation_id(violation["rule"], violation["selector"])
        action, reason, old_pr_number = gate.should_process(
            rule_id=violation["rule"],
            selector=violation["selector"],
            new_score=None,  # Will update after qa_critic
            new_solution_hash=None,  # Will update after codebase_compiler
        )

        if action == "SKIP":
            print(f"⏭️  Skipping {violation_id}: {reason}")  # noqa: T201
            metrics["skipped"] += 1
            # NEW: Task 3.4 - Persist skip decision (maintains state across runs)
            status = store.get(violation_id)
            if status:
                # Update existing status to reflect it's still valid but skipped this run
                status = status
            else:
                # Create new status for this violation
                status = ViolationStatus(
                    violation_id=violation_id,
                    rule_id=violation["rule"],
                    selector=violation["selector"],
                    current_pr_number=None,
                    current_score=None,
                    current_solution_hash=None,
                    state=ViolationState.NEW,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            store.upsert(status)
            continue

        # action == "CREATE" or "REPLACE" — proceed with full pipeline
        print(f"▶️  Processing {violation_id}: {action}")  # noqa: T201
        metrics["created"] += 1

        message = (
            "Resolve this axe-core violation:\n"
            f"rule: {violation['rule']}\n"
            f"page: {violation['url']}\n"
            f"selector: {violation['selector']}\n"
            f"html: {violation['html']}\n"
            f"failure_summary: {violation.get('failure_summary')}\n"
        )

        # Retry up to 3 times for non-deterministic empty responses
        MAX_ATTEMPTS = 3
        violation_succeeded = False
        for attempt in range(MAX_ATTEMPTS):
            thread_config = {
                "configurable": {
                    "thread_id": f"violation-{index}-attempt{attempt + 1}",
                    "recursion_limit": 50,
                }
            }
            try:
                result = await graph.ainvoke(
                    {"messages": [{"role": "user", "content": message}]},
                    config=thread_config,
                )
                result = await resolve_interrupts(
                    graph, thread_config, result, auto_approve=args.yes
                )

                response = result.get("structured_response")
                if response is None:
                    if attempt < MAX_ATTEMPTS - 1:
                        continue  # Try again with fresh thread_id
                    # All retries exhausted
                    print(
                        f"[{violation['rule']}] no structured response produced after retries - skipping"
                    )  # noqa: T201
                    break

                # Successfully got a response
                warn_on_overconfidence(violation["rule"], response.rationale)
                outcome = deliver_violation(
                    violation,
                    response,
                    fixture=fixture,
                    pr_config=pr_config,
                    output_dir=output_dir,
                )
                print(f"[{violation['rule']}] {outcome}")  # noqa: T201

                # NEW: Task 3.4 - Persist delivery result to violation store
                if outcome.get("delivered"):
                    result = outcome.get("result")
                    pr_number = None
                    if isinstance(result, pr_delivery.LiveResult):
                        pr_number = result.pull_request_number

                    solution_hash = hashlib.sha256(
                        response.code.encode("utf-8")
                    ).hexdigest()[:12]
                    status = ViolationStatus(
                        violation_id=violation_id,
                        rule_id=violation["rule"],
                        selector=violation["selector"],
                        current_pr_number=pr_number,
                        current_score=response.score,
                        current_solution_hash=solution_hash,
                        state=(
                            ViolationState.MERGED
                            if (pr_config.github_token and response.score >= 18.0)
                            else ViolationState.PR_OPEN
                        ),
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    )
                    store.upsert(status)
                    print(
                        f"  💾 Persisted {violation_id} (PR#{pr_number}, score {response.score}/20)"
                    )  # noqa: T201

                violation_succeeded = True
                break
            except (
                Exception
            ) as exc:  # noqa: BLE001 - one violation's failure must not abort the rest of the batch
                # Don't retry on exceptions, just skip and move to next violation
                failures += 1
                print(
                    f"[{violation['rule']}] FAILED: {type(exc).__name__}: {exc}"
                )  # noqa: T201
                break

        if not violation_succeeded and attempt == MAX_ATTEMPTS - 1 and response is None:
            # Explicitly mark as failed if all retries exhausted with no response
            failures += 1

    # NEW: Print Phase 0.2 metrics at end
    print("\n" + "=" * 50)  # noqa: T201
    print(f"=== Phase 0.2 Violation Tracking Metrics ===")  # noqa: T201
    print(f"Total violations in audit: {len(violations)}")  # noqa: T201
    print(f"Skipped (duplicates prevented): {metrics['skipped']}")  # noqa: T201
    print(f"Created (new violations): {metrics['created']}")  # noqa: T201
    print(f"Replaced (better solution): {metrics['replaced']}")  # noqa: T201
    print(f"Failed to resolve: {failures}")  # noqa: T201
    print("=" * 50 + "\n")  # noqa: T201

    if failures:
        print(f"{failures}/{len(violations)} violation(s) failed")  # noqa: T201
    return 1 if failures else 0


def _cmd_run(args: argparse.Namespace) -> int:
    return asyncio.run(_acmd_run(args))


def _cmd_review(args: argparse.Namespace) -> int:
    from a11y_fixer.hitl.review_queue import (
        ReviewQueue,
    )  # noqa: PLC0415 - deferred: keeps --help free of extra imports

    pr_config = config.resolve_pr_delivery(args.live)
    output_dir = config.agent_root() / "evaluation" / "results" / "prs"
    queue = ReviewQueue(
        config.hitl_queue_dir(),
        wiki_dir=config.wiki_dir(),
        pr_config=pr_config,
        output_dir=output_dir,
    )

    if args.list:
        pending = queue.list_pending()
        if not pending:
            print("hitl queue is empty")  # noqa: T201
            return 0
        for path in pending:
            violation = json.loads(path.read_text(encoding="utf-8"))["violation"]
            print(
                f"{path.name}: {violation['rule']} ({violation.get('selector', '?')})"
            )  # noqa: T201
        return 0

    if not args.item or not (args.approve or args.reject):
        print(
            "usage: a11y-fixer review <item> (--approve | --reject) [--notes ...]"
        )  # noqa: T201
        return 1

    queue_path = (
        Path(args.item)
        if Path(args.item).is_absolute()
        else config.hitl_queue_dir() / args.item
    )
    if not queue_path.exists():
        print(f"not found in the hitl queue: {queue_path}")  # noqa: T201
        return 1

    decision = "approve" if args.approve else "reject"
    result = queue.review(
        queue_path, decision, reviewer=args.reviewer, notes=args.notes or ""
    )
    print(json.dumps(result, default=str, indent=2))  # noqa: T201
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="a11y-fixer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser(
        "audit", help="Run a full axe-core audit against the fixture"
    )
    audit_parser.add_argument(
        "--output", default=str(config.agent_root() / DEFAULT_AUDIT_OUTPUT)
    )
    audit_target_group = audit_parser.add_mutually_exclusive_group()
    audit_target_group.add_argument(
        "--repo",
        default=None,
        help="Local path or git URL of the Angular repo to audit (default: the bundled Hallucinate.io fixture)",
    )
    audit_target_group.add_argument(
        "--url",
        default=None,
        help="Audit a live, already-running site directly (no clone/build/serve) - audit-only, can't deliver fixes",
    )
    audit_parser.set_defaults(func=_cmd_audit)

    run_parser = subparsers.add_parser(
        "run", help="Run the deep agent over every violation in an audit report"
    )
    run_parser.add_argument(
        "--audit",
        default=None,
        help="Path to a normalized audit JSON; runs a fresh audit if omitted",
    )
    run_parser.add_argument(
        "--repo",
        default=None,
        help="Local path or git URL of the Angular repo to fix (default: the bundled Hallucinate.io fixture)",
    )
    run_parser.add_argument(
        "--case-ids",
        default=None,
        help="Comma-separated case IDs to test (e.g. case-01,case-03,case-13); if provided, only these benchmark cases are processed",
    )
    run_parser.add_argument(
        "--yes",
        action="store_true",
        help="Auto-approve every HITL interrupt (non-interactive)",
    )
    live_group = run_parser.add_mutually_exclusive_group()
    live_group.add_argument(
        "--live",
        dest="live",
        action="store_true",
        default=None,
        help="Force live PR delivery",
    )
    live_group.add_argument(
        "--no-live", dest="live", action="store_false", help="Force dry-run delivery"
    )
    run_parser.set_defaults(func=_cmd_run)

    review_parser = subparsers.add_parser(
        "review", help="List or decide on queued HITL review items"
    )
    review_parser.add_argument(
        "item",
        nargs="?",
        default=None,
        help="Queue filename (see --list) to approve or reject",
    )
    review_parser.add_argument(
        "--list", action="store_true", help="List pending queue items and exit"
    )
    decision_group = review_parser.add_mutually_exclusive_group()
    decision_group.add_argument(
        "--approve", action="store_true", help="Approve and deliver the queued fix"
    )
    decision_group.add_argument(
        "--reject", action="store_true", help="Reject and record a wiki lesson"
    )
    review_parser.add_argument(
        "--notes",
        default=None,
        help="Constraint/reason text (used as the wiki lesson on --reject)",
    )
    review_parser.add_argument(
        "--reviewer",
        default="cli",
        help="Reviewer name recorded in the decision (default: %(default)s)",
    )
    review_live_group = review_parser.add_mutually_exclusive_group()
    review_live_group.add_argument(
        "--live",
        dest="live",
        action="store_true",
        default=None,
        help="Force live PR delivery on --approve",
    )
    review_live_group.add_argument(
        "--no-live",
        dest="live",
        action="store_false",
        help="Force dry-run delivery on --approve",
    )
    review_parser.set_defaults(func=_cmd_review)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
