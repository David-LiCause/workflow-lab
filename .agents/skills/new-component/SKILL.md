---
name: new-component
description: Seed a new reusable component in workflow-lab with spec-driven development. Interviews the user, then writes the spec, tests, implementation, and README unattended. Use when the user asks to create, seed, or scaffold a component.
---

# New component

Two parts: **Part 1 is interactive. Part 2 runs unattended**, without stopping.

## Part 1: Interview (interactive)

Ask the user, a few questions at a time:

- **Name** (snake_case) and one-line purpose
- **Inputs and outputs:** what goes in, what comes out
- **Core behaviors:** what it must do, key edge cases
- **Out of scope:** what it deliberately doesn't do
- **Dependencies and config:** libraries, services, env vars

Then write back a short summary of the goals and scope. Continue only once the user confirms it.

## Part 2: Build (unattended)

Do steps 1–6 in order without asking the user anything. Run commands from the workspace root. Paths below use `<p>` for
`packages/workflow-lab` and `<c>` for `<p>/src/workflow_lab/components/<name>`.

### 1. Spec

Write `<c>/SPEC.md`:

1. **Purpose:** 1–2 lines.
2. **Interface:** signatures with types.
3. **Inputs and outputs**
4. **Behavior rules:** numbered `R1`, `R2`, … Each rule is testable.
5. **Errors:** what raises, what is handled.
6. **Config and dependencies:** env vars, optional extras.
7. **Out of scope**

### 2. Interface stub

Write `<c>/__init__.py` with real signatures, types, and docstrings. Bodies raise `NotImplementedError`.

### 3. Tests

Write `<p>/tests/components/<name>/test_<name>.py`:

- At least one test per rule, named `test_r<N>_<what>`.
- Fakes only (`MockLLM`, `tmp_path`, in-memory SQLite). No network or API keys.
- If the component talks to an external service, add
  `<p>/tests/components/<name>/integration/test_<name>_live.py` with
  `pytestmark = pytest.mark.integration`, calling `require_env("VAR")` for each needed env var
  (fails if missing). Add any new vars to the root `.env.example`.

Run `uv run pytest <p>/tests/components/<name>` and confirm the tests fail with `NotImplementedError`.

### 4. Implement

Write `<c>/<name>.py` and export it from `__init__.py`.

- Never weaken a test to make it pass. If a test contradicts the spec, fix the test to match the
  spec and note it in the final report.
- Add dependencies with `uv add --package workflow-lab --optional <extra> <pkg>`. For a new extra,
  also add it to the root dev dependency `workflow-lab[...]` with `uv add --dev`, so tests have it.
- Iterate until `uv run pytest <p>/tests/components/<name>` passes.

### 5. Finish

Run `uv run pytest && uv run ruff check . && uv run ruff format .`. Add the component to the
components table in `<p>/README.md`.

### 6. Component README

Write `<c>/README.md`, short and human-readable:

- **What it does:** 1–2 lines.
- **Signature:** inputs and outputs.
- **Example:** a minimal usage snippet.
- **Using it in LangGraph:** a thin node wrapper that reads from state, calls the component, and
  returns a state update, plus the `add_node` line.

End with a short report: what was built, files created, and any spec gaps or test fixes.
