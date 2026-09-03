# Worktree / Docker Sandbox Integration — Implementation Notes

**Date:** 2026-09-02  
**Session:** CMU Capstone — A11y Fixer  
**Phases implemented:** 1 – 4 (of the worktree/Docker sandbox plan)

---

## What Was Done

### Phase 1 — `ResolvedTools` split in `deep_agent.py`

**Problem:** `abuild_agent()` was monolithic — it spawned the angular-cli MCP npx process, fetched all tools, and built the LangGraph graph in one async call. Running 22 benchmark cases meant 22 npx spawns.

**Solution:** Split into three layers:

```
aresolve_tools()          # async, expensive, call ONCE per benchmark run
    → ResolvedTools       # dataclass holding model_spec, top_level_tools,
                          #   cc_mcp_tools (angular-cli), other_subagents [cp, qc, ac]

abuild_graph(resolved, *, fixture_path, backend, checkpointer)
                          # sync, fast, call PER CASE
                          # rebuilds codebase_compiler subagent with per-case fixture path

abuild_agent(*, backend, checkpointer)
                          # thin async wrapper = aresolve_tools() + abuild_graph()
                          # backward-compatible: CLI and one-shot callers unchanged
```

**Key insight — SubAgent is a TypedDict:** `cc_subagent["tools"]` gives the list of tools. We strip `locate_selector_in_component` from `cc_mcp_tools` because `build_from_tools()` re-adds it so the closure captures the correct per-case fixture path (not the default one).

**Subagent ordering preserved:** original order is `[cp, cc, qc, ac]`. `other_subagents` stores `[cp, qc, ac]`; `abuild_graph` inserts the rebuilt `cc_subagent` at index 1.

---

### Phase 2 — `build_from_tools()` in `codebase_compiler.py`

**Problem:** `codebase_compiler.build(model)` was the only way to get a SubAgent, and it called `aget_tools(["angular-cli"])` (npx spawn) every time.

**Solution:** Added a sync `build_from_tools(mcp_tools, model, *, fixture_path=None) -> SubAgent` that takes pre-resolved tools and constructs the SubAgent without any async I/O. Updated `build()` to delegate to it:

```python
async def build(model, *, fixture_path=None) -> SubAgent:
    mcp_tools = await aget_tools(["angular-cli"])
    mcp_tools = [t for t in mcp_tools if t.name != "list_projects"]
    return build_from_tools(mcp_tools, model, fixture_path=fixture_path)
```

**Existing tests unchanged:** They mock `a11y_fixer.agents.codebase_compiler.aget_tools` and call `build("model")` — the mock path is still valid after the refactor.

**`list_projects` filter:** Kept in `build()` (not `build_from_tools()`). When `aresolve_tools()` extracts tools from `cc_subagent["tools"]`, the `list_projects` tool is already filtered (it was filtered when `build()` ran). Only `locate_selector_in_component` is stripped in `aresolve_tools()`.

---

### Phase 3 — `mount_target` param in `DockerSandboxBackend`

**Problem:** `start()` hardcoded `/workspace` in two places — the bind-mount flag and the `node_modules` volume mount. Worktrees need a configurable mount point.

**Solution:** Added `mount_target: str = "/workspace"` to `__init__` and stored as `self._mount_target`. Both occurrences in `start()` replaced:

```python
"-v", f"{self._workdir}:{self._mount_target}",
# and
f"{self._node_modules_volume}:{self._mount_target}/node_modules"
```

Fully backward-compatible — existing callers that don't pass `mount_target` get `/workspace` as before.

---

### Phase 4 — Worktree flow in `run_eval.py`

**Changes:**

1. `_run_one_case(... runner: AxeAuditRunner | None ...)` — when `None`, skips axe re-audit and sets `cleared = False` conservatively. Git reset in `finally` still runs (harmless in worktree — worktree is torn down after anyway).

2. `_arun_eval(... use_worktree: bool = False ...)` — two execution paths:
   - **Default (shared graph):** `abuild_agent()` once → shared AxeAuditRunner → loop over cases.
   - **Worktree mode:** `aresolve_tools()` once → per-case: `create_worktree()` → `abuild_graph(fixture_path=wt_fixture)` → `_run_one_case(runner=None)` → `remove_worktree()`.

3. `run_eval(... use_worktree: bool = False ...)` — passes through to `_arun_eval`.

4. CLI: `--worktree` flag added to `main()`.

**Worktree fixture path:** `worktree.path / "Hallucinate.io"` — the worktree is created at `cmu-capstone/a11y-fixer-case-NN/`, so the fixture is at `cmu-capstone/a11y-fixer-case-NN/Hallucinate.io/`.

**`node_modules` symlink:** `link_dirs=("Hallucinate.io/node_modules",)` symlinks the original's `node_modules` into the worktree, so `ng build` resolves packages without a full `npm ci` per case. Guarded by `if source.exists()` in `create_worktree`.

---

## What Was Learned

### Virtual path alignment is per-case in worktree mode

`config.to_virtual_path(path)` computes `"/" + path.resolve().relative_to(repo_root()).as_posix()`. For the default fixture: `/Hallucinate.io`. For a worktree: `/a11y-fixer-case-01/Hallucinate.io`. Permissions and `FilesystemMiddleware` rules must be rebuilt per-case using the worktree's virtual path — that's exactly what `abuild_graph(fixture_path=wt_fixture)` does.

### `locate_selector_in_component` captures fixture path at call time

The `@tool`-decorated `locate_selector_in_component` function defaults `codebase_root` to `config.fixture_path()`. In worktree mode we need it to default to the worktree fixture. Since the tool is a closure over Python's default-argument evaluation, stripping it from `cc_mcp_tools` and letting `build_from_tools()` re-add it is the correct approach — the new instance is created in the context of the per-case `fixture_path`.

> **Actually:** `locate_selector_in_component` uses `config.fixture_path()` at call time, not at definition time, so the above concern may be moot — but `build_from_tools` re-adding it is still correct because it keeps the fixture-scoped permissions consistent.

### axe re-audit skipped in worktree mode (known limitation)

`_recheck_cleared(runner, case)` requires a running `ng serve` pointing at the worktree. Starting a server per worktree would add significant latency. For now: `cleared = False` when `runner=None`. A future phase can start a per-worktree server and pass a real runner.

### Device-bash VM cannot run macOS venv

The `device_bash` remote VM is Linux (aarch64). The project venv (`agent/.venv/`) is symlinked to `/opt/homebrew/opt/python@3.13/bin/python3.13` (macOS Homebrew). Attempting to execute it in the VM fails with "No such file or directory". The workaround is to use `computer_*` tools (requires computer use to be enabled) or to run tests from a Mac terminal session directly. `uv python install` was also blocked (no egress in the VM).

### Static verification steps that work without a running Python

1. `python3 -c "import ast; ast.parse(open(f).read())"` — syntax check with any Python version.
2. `grep -n` on function signatures and call sites — cross-module consistency.
3. `git diff --stat HEAD` — confirms which files actually changed.

### `create_worktree` API

```python
create_worktree(
    repo_path: Path,           # cmu-capstone/ (the git root)
    *,
    base_dir: Path | None,     # where to create the worktree dir
    branch_name: str | None,   # becomes the dir name with / → -
    link_dirs: tuple[str, ...] # relative paths to symlink from repo_path
) -> Worktree(path, branch, repo_path)
```

`remove_worktree(worktree, force=True)` removes dir + branch + prunes admin state.

---

## How to Use Worktree Mode

```bash
# Single case, isolated worktree
cd cmu-capstone/agent
.venv/bin/python -m evaluation.run_eval --case-ids case-01 --worktree

# Full benchmark, one worktree per case
.venv/bin/python -m evaluation.run_eval --phase all --worktree
```

## Files Modified

| File | Change |
|------|--------|
| `src/a11y_fixer/deep_agent.py` | Added `ResolvedTools`, `aresolve_tools()`, `abuild_graph()`; `abuild_agent()` now delegates |
| `src/a11y_fixer/agents/codebase_compiler.py` | Added `build_from_tools()`; `build()` delegates to it |
| `src/a11y_fixer/adapters/sandbox/docker_backend.py` | Added `mount_target` param to `__init__` and `start()` |
| `evaluation/run_eval.py` | Optional runner in `_run_one_case`; worktree flow + `--worktree` flag |

## Files Already Complete (Not Modified)

| File | Status |
|------|--------|
| `src/a11y_fixer/adapters/sandbox/git_worktree.py` | ✅ Complete — `create_worktree`, `remove_worktree`, `list_worktrees` |
| `sandbox/Dockerfile` | ✅ Ready — `a11y-fixer-sandbox:latest` image |
| `src/a11y_fixer/adapters/sandbox/__init__.py` | Exports to add in Phase 6 |
