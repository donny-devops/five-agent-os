# Contributing to Five-Agent Operating System

Thank you for considering contributing! This guide covers how to add a new agent, extend schemas, and run the test suite.

## Table of Contents

- [Development Setup](#development-setup)
- [Running Tests](#running-tests)
- [Linting](#linting)
- [Adding a Sixth Agent](#adding-a-sixth-agent)
- [Handoff Contract Format](#handoff-contract-format)
- [Schema Extension Rules](#schema-extension-rules)
- [Commit Style](#commit-style)

---

## Development Setup

```bash
# Clone the repo
git clone https://github.com/donny-devops/five-agent-operating-system.git
cd five-agent-operating-system

# Create a virtual environment (Python 3.11+)
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dev dependencies
pip install ruff pytest
```

---

## Running Tests

```bash
pytest tests/ -v
```

All three test modules must pass before opening a PR:

| File | What it covers |
|---|---|
| `tests/test_models.py` | `TaskPacket`, `AgentOutput`, `generate_request_id` |
| `tests/test_router.py` | `detect_work_types`, `detect_risk`, `build_route`, `create_task_packet` |
| `tests/test_orchestrator.py` | Individual agent functions + full `run_workflow` integration |

---

## Linting

```bash
ruff check . --output-format=github
```

The project targets Python 3.11+ and enforces rule sets `E`, `W`, `F`, `I`, `B`, `UP`, `C4`, `SIM` (see `pyproject.toml`).

---

## Adding a Sixth Agent

1. **Create the agent markdown spec** in `agents/your-agent-name.md` following the existing agent format.

2. **Register a route** in `src/multi_agent_os/router.py`:
   - Add relevant keywords to `WORK_TYPE_KEYWORDS`
   - Add your agent to the appropriate entry in `ROUTES`
   - Add your agent name to `phase_order` in `build_route()` at the correct pipeline position

3. **Implement the agent function** in `src/multi_agent_os/orchestrator.py`:
   ```python
   @retry()
   def run_your_agent(task: TaskPacket, context: dict[str, Any]) -> AgentOutput:
       output = {...}
       return AgentOutput(task.request_id, "your_agent", "success", output, "medium")
   ```

4. **Register in `_AGENT_DISPATCH`** inside `run_workflow_async()`:
   ```python
   "your_agent": lambda: run_your_agent(task, context),
   ```

5. **Write tests** in `tests/test_orchestrator.py` covering at minimum:
   - `status == "success"` on a normal task
   - Required output keys are present
   - `request_id` is propagated correctly

---

## Handoff Contract Format

Every agent receives a `TaskPacket` and returns an `AgentOutput`. The contract is:

```
TaskPacket  -->  Agent Function  -->  AgentOutput
```

- **Input**: `task: TaskPacket` (read-only — agents must not mutate it)
- **Context**: `context: dict[str, Any]` containing `task_packet` and `agent_outputs` (list of prior outputs)
- **Output**: `AgentOutput` with:
  - `status`: one of `success | revise | escalate | failed`
  - `output`: a flat or nested dict — all values must be JSON-serializable
  - `confidence`: `low | medium | high`
  - `errors`: populated only on `failed` status
  - `duration_ms`: automatically set by `_timed_agent` — do not set manually

---

## Schema Extension Rules

- **`TaskPacket`** lives in `src/multi_agent_os/models.py`. Adding a field requires:
  1. Bumping `SCHEMA_VERSION` (semver patch for additive, minor for breaking)
  2. Providing a `field(default_factory=...)` default so existing callers don't break
  3. Updating `schemas/task_packet.schema.json` to match

- **`AgentOutput`** follows the same rules for the `output` dict keys — document new keys in the agent's markdown spec in `agents/`.

---

## Commit Style

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(router): add confidence scoring to build_route
fix(orchestrator): handle unknown agent name gracefully
test: add edge cases for high-risk routing
ci: pin ruff to 0.4.x
docs: update CONTRIBUTING with sixth-agent guide
```
