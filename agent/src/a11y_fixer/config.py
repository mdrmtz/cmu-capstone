"""Runtime configuration for the A11y Fixer agent.

Resolves the Hallucinate.io fixture path, selects the pluggable LLM backend
(Ollama/Anthropic/OpenAI/OpenRouter), and decides the GitHub PR delivery mode
(live vs. dry-run). All state here is derived from environment variables so
the same code runs unmodified in local dev and CI.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

FIXTURE_DIR_NAME = "Hallucinate.io"

# Repo layout is fixed: agent/src/a11y_fixer/config.py -> parents[3] == cmu-capstone/.
_REPO_ROOT = Path(__file__).resolve().parents[3]

_DEFAULT_MODELS = {
    "ollama": "ollama:llama3.1",
    "anthropic": "anthropic:claude-sonnet-4-5-20250929",
    "openai": "openai:gpt-4o-mini",
    "openrouter": "openrouter:meta-llama/llama-3.3-70b-instruct",
}


def repo_root() -> Path:
    """The cmu-capstone repo root (parent of both agent/ and Hallucinate.io/)."""
    return _REPO_ROOT


def agent_root() -> Path:
    """The agent/ package root (parent of src/)."""
    return Path(__file__).resolve().parents[2]


def fixture_path() -> Path:
    """Resolve the Hallucinate.io fixture path.

    Override with `A11Y_FIXTURE_PATH` for non-standard checkouts; CI always
    passes it explicitly for reliability across checkout layouts.
    """
    override = os.environ.get("A11Y_FIXTURE_PATH")
    if override:
        return Path(override).resolve()
    return _REPO_ROOT / FIXTURE_DIR_NAME


def is_default_fixture() -> bool:
    """True unless `--repo`/`A11Y_FIXTURE_PATH` points at something other than
    the bundled Hallucinate.io fixture - `DEFAULT_PAGES` is only ever correct
    for that one fixture, never for an arbitrary other repo.
    """
    return fixture_path() == _REPO_ROOT / FIXTURE_DIR_NAME


def wiki_dir() -> Path:
    """Institutional-memory directory: HITL rejection lessons only."""
    return agent_root() / "wiki"


def hitl_queue_dir() -> Path:
    """Filesystem-backed human review queue (runtime state, gitignored)."""
    return agent_root() / "hitl_queue"


def repo_cache_dir() -> Path:
    """Where `--repo <url>` clones land (runtime state, gitignored)."""
    return agent_root() / ".repo-cache"


def skills_dir() -> Path:
    """The `.agents/skills/` directory (cmu-capstone root, shared across the project)."""
    return repo_root() / ".agents" / "skills"


def to_virtual_path(path: Path) -> str:
    """Convert a real path to the deep agent's virtual path space.

    `deep_agent.abuild_agent`'s `FilesystemBackend` runs with `virtual_mode=
    True` rooted at `repo_root()`, so every path the agent sees (skills,
    memory, permissions, tool calls) must be root-relative with a leading
    `/`, not a real absolute filesystem path - passing the latter makes the
    backend double the root prefix and report "not found" for a path that
    plainly exists on disk.
    """
    return "/" + path.resolve().relative_to(repo_root()).as_posix()


@dataclass(frozen=True)
class LLMBackendConfig:
    """A resolved provider:model spec plus the env var it came from."""

    backend: str
    model: str


def selected_llm_backend() -> LLMBackendConfig:
    """Select the LLM backend: `A11Y_LLM_BACKEND` env var, default "ollama".

    `A11Y_LLM_MODEL` overrides the default model id for the chosen backend.
    Bare ids (e.g. `openrouter/free`) get the `<backend>:` prefix `init_chat_
    model` requires. Checking for the exact `<backend>:` prefix (not just
    "contains a colon") matters because OpenRouter ids can themselves contain
    a colon, e.g. `google/gemma-4-26b-a4b-it:free` - that must still get
    prefixed to `openrouter:google/gemma-4-26b-a4b-it:free`, not be mistaken
    for an already-complete spec.
    """
    backend = os.environ.get("A11Y_LLM_BACKEND", "ollama").strip().lower()
    if backend not in _DEFAULT_MODELS:
        valid = ", ".join(sorted(_DEFAULT_MODELS))
        msg = f"Unknown A11Y_LLM_BACKEND={backend!r}. Valid values: {valid}"
        raise ValueError(msg)
    model_override = os.environ.get("A11Y_LLM_MODEL", "").strip()
    backend_prefix = f"{backend}:"
    if not model_override:
        model = _DEFAULT_MODELS[backend]
    elif model_override.startswith(backend_prefix):
        model = model_override
    else:
        model = f"{backend_prefix}{model_override}"
    return LLMBackendConfig(backend=backend, model=model)


def configure_model_providers() -> None:
    """Register provider profiles that make model construction env-driven.

    Must run before `create_deep_agent(model=...)` resolves a "provider:model"
    string. Idempotent - safe to call multiple times.
    """
    from deepagents import ProviderProfile, register_provider_profile

    register_provider_profile(
        "ollama",
        ProviderProfile(
            init_kwargs_factory=lambda: {
                "base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
            }
        ),
    )


@dataclass(frozen=True)
class PRDeliveryConfig:
    """GitHub PR delivery mode: token-aware default, explicit CLI override."""

    live: bool
    github_token: str | None
    github_repo: str | None


def resolve_pr_delivery(cli_live: bool | None) -> PRDeliveryConfig:
    """Resolve live vs. dry-run delivery.

    `cli_live=True` forces live (raises if no token). `cli_live=False` forces
    dry-run. `cli_live=None` defaults to dry-run (safe default) unless
    explicitly overridden with --live.
    """
    token = os.environ.get("GITHUB_TOKEN", "").strip() or None
    repo = os.environ.get("GITHUB_REPO", "").strip() or None

    if cli_live is True and not token:
        msg = "--live requires GITHUB_TOKEN to be set"
        raise RuntimeError(msg)

    if cli_live is None:
        # Default to dry-run (safe default) - user must explicitly pass --live
        live = False
    else:
        live = cli_live

    return PRDeliveryConfig(live=live, github_token=token, github_repo=repo)


def langsmith_tracing_enabled() -> bool:
    return os.environ.get("LANGSMITH_TRACING", "").strip().lower() in {
        "true",
        "1",
        "yes",
    }
