from __future__ import annotations

from pathlib import Path

import pytest

from a11y_fixer import config


def test_to_virtual_path_is_root_relative_with_leading_slash() -> None:
    virtual = config.to_virtual_path(config.fixture_path())
    assert virtual == "/Hallucinate.io"


def test_to_virtual_path_nested_path() -> None:
    virtual = config.to_virtual_path(config.skills_dir() / "a11y-fixer")
    assert virtual == "/.agents/skills/a11y-fixer"


def test_to_virtual_path_rejects_path_outside_repo_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not in the subpath"):
        config.to_virtual_path(tmp_path)


def test_is_default_fixture_true_with_no_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("A11Y_FIXTURE_PATH", raising=False)
    assert config.is_default_fixture() is True


def test_is_default_fixture_false_with_repo_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("A11Y_FIXTURE_PATH", str(tmp_path))
    assert config.is_default_fixture() is False


def test_selected_llm_backend_defaults_to_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("A11Y_LLM_BACKEND", raising=False)
    monkeypatch.delenv("A11Y_LLM_MODEL", raising=False)
    assert config.selected_llm_backend() == config.LLMBackendConfig(backend="ollama", model="ollama:llama3.1")


def test_selected_llm_backend_bare_model_override_gets_backend_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bare model id (no `provider:` prefix) must be combined with the
    selected backend - passing it through unprefixed makes `init_chat_model`
    fail to infer a provider (found via a real `openrouter/free` run)."""
    monkeypatch.setenv("A11Y_LLM_BACKEND", "openrouter")
    monkeypatch.setenv("A11Y_LLM_MODEL", "openrouter/free")
    assert config.selected_llm_backend().model == "openrouter:openrouter/free"


def test_selected_llm_backend_bare_model_override_with_embedded_colon(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenRouter ids can themselves contain a colon (e.g. a `:free` suffix) -
    that must not be mistaken for an already-complete `provider:model` spec
    (found via a real `google/gemma-4-26b-a4b-it:free` run)."""
    monkeypatch.setenv("A11Y_LLM_BACKEND", "openrouter")
    monkeypatch.setenv("A11Y_LLM_MODEL", "google/gemma-4-26b-a4b-it:free")
    assert config.selected_llm_backend().model == "openrouter:google/gemma-4-26b-a4b-it:free"


def test_selected_llm_backend_full_spec_override_used_as_is(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A11Y_LLM_BACKEND", "openrouter")
    monkeypatch.setenv("A11Y_LLM_MODEL", "openrouter:nvidia/nemotron-3-ultra-550b-a55b")
    assert config.selected_llm_backend().model == "openrouter:nvidia/nemotron-3-ultra-550b-a55b"


def test_selected_llm_backend_rejects_unknown_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A11Y_LLM_BACKEND", "bogus")
    with pytest.raises(ValueError, match="Unknown A11Y_LLM_BACKEND"):
        config.selected_llm_backend()
