from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from a11y_fixer import config
from a11y_fixer.agents import audit_crawler, codebase_compiler, compliance_planner, qa_critic


@pytest.fixture(autouse=True)
def _fake_tools(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    fake = AsyncMock(return_value=["fake-tool"])
    for module in (compliance_planner, codebase_compiler, qa_critic, audit_crawler):
        monkeypatch.setattr(module, "aget_tools", fake)
    return fake


async def test_compliance_planner_spec() -> None:
    spec = await compliance_planner.build()
    assert spec["name"] == "compliance_planner"
    assert spec["tools"] == ["fake-tool"]
    skill_dir = config.skills_dir() / "a11y-fixer"
    assert spec["skills"] == [config.to_virtual_path(skill_dir)]
    assert skill_dir.is_dir()


async def test_qa_critic_spec() -> None:
    spec = await qa_critic.build()
    assert spec["name"] == "qa_critic"
    assert "skills" not in spec


async def test_audit_crawler_spec() -> None:
    spec = await audit_crawler.build()
    assert spec["name"] == "audit_crawler"
    skill_dir = config.skills_dir() / "playwright-mcp"
    assert spec["skills"] == [config.to_virtual_path(skill_dir)]
    assert skill_dir.is_dir()


async def test_codebase_compiler_spec_permission_ordering() -> None:
    spec = await codebase_compiler.build("ollama:llama3.1")
    assert spec["name"] == "codebase_compiler"

    permissions = spec["permissions"]
    modes = [p.mode for p in permissions]
    # allow rules for read/write must precede the catch-all write deny,
    # since FilesystemPermission checking is first-match-wins.
    assert modes[-1] == "deny"
    assert modes[:-1] == ["allow", "allow"]

    write_allow = next(p for p in permissions if p.mode == "allow" and "write" in p.operations)
    virtual_fixture = config.to_virtual_path(config.fixture_path())
    assert all(path.startswith(virtual_fixture) for path in write_allow.paths)
    assert any(path.endswith("*.component.html") for path in write_allow.paths)
    assert any(path.endswith("src/index.html") for path in write_allow.paths)

    deny_rule = permissions[-1]
    assert deny_rule.paths == ["/**"]
    assert deny_rule.operations == ["write"]
