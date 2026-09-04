"""Resolves the target repo to audit/fix: a local path is used as-is, a git
URL is shallow-cloned into a cache directory. This is what makes the
fixture pluggable via a single `--repo` CLI argument instead of hardcoding
`Hallucinate.io` - point `a11y-fixer` at any Angular repo's URL or checkout.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_URL_RE = re.compile(r"^(https?://|git@|ssh://)")

_GITHUB_URL_RE = re.compile(
    r"^(?:https?://github\.com/|git@github\.com:|ssh://git@github\.com/)"
    r"(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)


class RepoSourceError(RuntimeError):
    """Raised when resolving or cloning the target repo fails."""


def is_url(source: str) -> bool:
    """True if `source` looks like a git URL rather than a local path."""
    stripped = source.strip()
    return bool(_URL_RE.match(stripped)) or stripped.endswith(".git")


def _slug_for(url: str) -> str:
    name = url.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"\.git$", "", name) or "repo"


def resolve_repo_source(source: str, *, cache_dir: Path) -> Path:
    """Return a local, checked-out path for `source`.

    A local directory path is resolved and returned as-is. A git URL is
    shallow-cloned (`--depth 1`) into `cache_dir`, reusing an existing clone
    at the same URL-derived directory name if one is already present rather
    than re-cloning on every run.
    """
    stripped = source.strip()
    if not is_url(stripped):
        path = Path(stripped).expanduser().resolve()
        if not path.is_dir():
            msg = f"local repo path does not exist: {path}"
            raise RepoSourceError(msg)
        return path

    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / _slug_for(stripped)
    if target.is_dir():
        return target

    result = subprocess.run(  # noqa: S603, S607 - fixed subcommand, source is the caller's own --repo argument
        ["git", "clone", "--depth", "1", stripped, str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        msg = f"git clone failed for {stripped!r} (exit {result.returncode}):\n{result.stderr}"
        raise RepoSourceError(msg)
    return target


def derive_github_repo(source: str, *, resolved_path: Path | None = None) -> str | None:
    """Best-effort `owner/repo` for GitHub PR delivery, derived from `source`.

    `source` is whatever was passed to `--repo` (a URL or a local path) - this
    is what closes the gap where `config.resolve_pr_delivery()` used to read a
    static `GITHUB_REPO` env var with no relation to `--repo` at all, so PR
    delivery for a dynamically-targeted repo (ACME, ABC, ...) would silently
    target whatever `GITHUB_REPO` happened to be exported as instead.

    A GitHub URL is parsed directly. A local path (or any source that isn't a
    recognizable GitHub URL) falls back to reading `resolved_path`'s own
    `origin` remote, if it has one and it points at GitHub. Returns `None`
    when nothing github.com-shaped can be found, so callers can fall back to
    their own default rather than silently mis-targeting PR delivery.
    """
    match = _GITHUB_URL_RE.match(source.strip())
    if match:
        return f"{match['owner']}/{match['repo']}"

    if resolved_path is None or not resolved_path.is_dir():
        return None

    result = subprocess.run(  # noqa: S603, S607 - fixed subcommand, resolved_path is our own resolved clone/checkout
        ["git", "-C", str(resolved_path), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None

    remote_match = _GITHUB_URL_RE.match(result.stdout.strip())
    return f"{remote_match['owner']}/{remote_match['repo']}" if remote_match else None
