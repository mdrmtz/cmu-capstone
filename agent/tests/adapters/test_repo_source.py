from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from a11y_fixer.adapters.repo_source import RepoSourceError, is_url, resolve_repo_source


@pytest.mark.parametrize(
    "source",
    [
        "https://github.com/mdrmtz/Hallucinate.io",
        "https://github.com/mdrmtz/Hallucinate.io.git",
        "git@github.com:mdrmtz/Hallucinate.io.git",
        "ssh://git@github.com/mdrmtz/Hallucinate.io.git",
    ],
)
def test_is_url_detects_git_urls(source: str) -> None:
    assert is_url(source) is True


def test_is_url_rejects_plain_local_path() -> None:
    assert is_url("/Users/dev/some/local/checkout") is False
    assert is_url("relative/path") is False


def test_resolve_repo_source_local_path_returns_as_is(tmp_path: Path) -> None:
    local_repo = tmp_path / "existing-checkout"
    local_repo.mkdir()

    resolved = resolve_repo_source(str(local_repo), cache_dir=tmp_path / "cache")

    assert resolved == local_repo.resolve()


def test_resolve_repo_source_raises_for_missing_local_path(tmp_path: Path) -> None:
    with pytest.raises(RepoSourceError, match="does not exist"):
        resolve_repo_source(str(tmp_path / "nope"), cache_dir=tmp_path / "cache")


@pytest.fixture
def source_git_repo(tmp_path: Path) -> Path:
    """A real, disposable git repo named `*.git` so `is_url()` treats it as clonable."""
    repo = tmp_path / "upstream.git"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)  # noqa: S603, S607
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)  # noqa: S603, S607
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)  # noqa: S603, S607
    (repo / "angular.json").write_text("{}\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)  # noqa: S603, S607
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True)  # noqa: S603, S607
    return repo


def test_resolve_repo_source_clones_git_url(source_git_repo: Path, tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"

    resolved = resolve_repo_source(str(source_git_repo), cache_dir=cache_dir)

    assert resolved == cache_dir / "upstream"
    assert (resolved / "angular.json").is_file()


def test_resolve_repo_source_reuses_existing_clone(source_git_repo: Path, tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    first = resolve_repo_source(str(source_git_repo), cache_dir=cache_dir)
    (first / "sentinel.txt").write_text("still here\n", encoding="utf-8")

    second = resolve_repo_source(str(source_git_repo), cache_dir=cache_dir)

    assert second == first
    assert (second / "sentinel.txt").is_file()


def test_resolve_repo_source_raises_on_clone_failure(tmp_path: Path) -> None:
    not_a_repo = "/definitely/not/a/real/repo.git"
    with pytest.raises(RepoSourceError, match="git clone failed"):
        resolve_repo_source(not_a_repo, cache_dir=tmp_path / "cache")
