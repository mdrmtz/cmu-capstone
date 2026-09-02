"""Violation status storage and pre-pipeline gate logic.

Manages .violation_status.json persistence and implements the decision matrix
for skip/create/replace actions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from a11y_fixer.domain.violations import (
    ViolationState,
    ViolationStatus,
    compute_violation_id,
    DuplicatePRInfo,
)


class ViolationStore:
    """Persistent storage for violation tracking across runs."""

    def __init__(self, status_file: Path | None = None):
        """Initialize store.

        Args:
            status_file: Path to .violation_status.json. Defaults to repo root.
        """
        if status_file is None:
            # Find repo root by looking for .git
            current = Path.cwd()
            while current != current.parent:
                if (current / ".git").exists():
                    status_file = current / ".violation_status.json"
                    break
                current = current.parent
            else:
                # Fallback to current directory
                status_file = Path.cwd() / ".violation_status.json"

        self.status_file = status_file
        self._cache: dict[str, ViolationStatus] = {}
        self._load()

    def _load(self) -> None:
        """Load .violation_status.json from disk."""
        if not self.status_file.exists():
            self._cache = {}
            return

        try:
            with open(self.status_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._cache = {
                    vid: ViolationStatus.from_dict(vdata) for vid, vdata in data.items()
                }
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Warning: Failed to load violation status: {e}")
            self._cache = {}

    def save(self) -> None:
        """Write .violation_status.json to disk."""
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        data = {vid: vs.to_dict() for vid, vs in self._cache.items()}
        with open(self.status_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get(self, violation_id: str) -> ViolationStatus | None:
        """Retrieve violation status."""
        return self._cache.get(violation_id)

    def upsert(self, violation_status: ViolationStatus) -> None:
        """Add or update violation status."""
        self._cache[violation_status.violation_id] = violation_status

    def find_duplicate_prs(
        self, violation_id: str, kept_pr_number: int
    ) -> list[DuplicatePRInfo]:
        """Find all duplicate PRs for same violation to close.

        Args:
            violation_id: The violation we're tracking
            kept_pr_number: PR number we're keeping (highest score or newly merged)

        Returns:
            List of DuplicatePRInfo for PRs to close
        """
        # In a real implementation, this would query GitHub to find all PRs
        # with [violation-{violation_id}] in title. For now, we return
        # the structural type so integration can use it.
        return []


class PrePipelineGate:
    """Decision logic: should we skip, create, or replace?"""

    # Score margin threshold: new solution must be at least this much better
    BETTER_SOLUTION_MARGIN = 1.5

    # Quality threshold: if score >= this, auto-merge when replacing
    AUTO_MERGE_THRESHOLD = 18.0

    def __init__(self, store: ViolationStore):
        self.store = store

    def should_process(
        self,
        rule_id: str,
        selector: str,
        new_score: float,
        new_solution_hash: str,
    ) -> tuple[str, str, Optional[int]]:
        """Determine action: CREATE, SKIP, or REPLACE.

        Args:
            rule_id: e.g., "image-alt"
            selector: CSS selector
            new_score: Rubric score of new solution (0-20)
            new_solution_hash: Hash of proposed solution code

        Returns:
            Tuple of (action, reason, old_pr_number_if_any)
            - action: "CREATE", "SKIP", or "REPLACE"
            - reason: Human-readable explanation
            - old_pr_number: PR to close if REPLACE, else None
        """
        violation_id = compute_violation_id(rule_id, selector)
        prior = self.store.get(violation_id)

        # Case 1: First time seeing this violation
        if prior is None:
            status = ViolationStatus(
                violation_id=violation_id,
                rule_id=rule_id,
                selector=selector,
                state=ViolationState.NEW,
                current_score=new_score,
                current_solution_hash=new_solution_hash,
                best_solution_hash=new_solution_hash,
                best_score=new_score,
            )
            self.store.upsert(status)
            self.store.save()
            return ("CREATE", "new_violation", None)

        # Case 2: Marked as WONT_FIX by human decision
        if prior.state == ViolationState.WONT_FIX:
            return ("SKIP", "marked_wont_fix_by_human", None)

        # Case 3: Already merged into main
        if prior.state == ViolationState.MERGED:
            return ("SKIP", "already_merged_to_main", prior.current_pr_number)

        # Case 4: Identical solution (same hash)
        if new_solution_hash == prior.best_solution_hash:
            return ("SKIP", "identical_solution_exists", prior.current_pr_number)

        # Case 5: Open PR exists
        if prior.state == ViolationState.PR_OPEN:
            # Is new solution significantly better?
            if new_score > prior.current_score + self.BETTER_SOLUTION_MARGIN:
                # YES: Replace with better solution
                status = ViolationStatus(
                    violation_id=violation_id,
                    rule_id=rule_id,
                    selector=selector,
                    state=ViolationState.BETTER_SOLUTION_READY,
                    current_score=new_score,
                    current_solution_hash=new_solution_hash,
                    best_solution_hash=new_solution_hash,
                    best_score=new_score,
                    created_at=prior.created_at,
                    updated_at=prior.updated_at,
                )
                self.store.upsert(status)
                self.store.save()
                return (
                    "REPLACE",
                    f"better_solution_ready (new_score={new_score:.1f} vs old={prior.current_score:.1f})",
                    prior.current_pr_number,
                )
            else:
                # NO: Skip, existing PR is good enough
                return (
                    "SKIP",
                    f"existing_pr_adequate (new_score={new_score:.1f} vs old={prior.current_score:.1f})",
                    prior.current_pr_number,
                )

        # Case 6: Closed (for whatever reason)
        if prior.state in (
            ViolationState.CLOSED_DUMMY,
            ViolationState.CLOSED_CONFLICT,
            ViolationState.CLOSED_SUPERSEDED,
        ):
            # Try again with new solution
            status = ViolationStatus(
                violation_id=violation_id,
                rule_id=rule_id,
                selector=selector,
                state=ViolationState.PR_OPEN,
                current_score=new_score,
                current_solution_hash=new_solution_hash,
                best_solution_hash=new_solution_hash,
                best_score=new_score,
                created_at=prior.created_at,
                updated_at=prior.updated_at,
            )
            self.store.upsert(status)
            self.store.save()
            return (
                "CREATE",
                f"retry_closed_violation (prev_reason={prior.close_reason})",
                None,
            )

        # Default: safety fallback
        return ("SKIP", "unknown_state_fallback", None)
