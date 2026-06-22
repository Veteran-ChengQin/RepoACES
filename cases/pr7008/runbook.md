# Runbook

## Directory Layout

- `cases/pr7008/task.md`: task prompt given to OpenHands.
- `cases/pr7008/validation.md`: evaluator-only validation notes.
- `workspaces/pr7008-run-001/FastGPT`: clean baseline repository mounted into OpenHands.
- `runs/pr7008`: run logs, diffs, and reports.

## First Manual/Canvas Run

1. Start Agent Canvas with only `workspaces` mounted as `/projects`.
2. Open `http://localhost:8000`.
3. Configure the LLM provider and model.
4. Open workspace `/projects/pr7008-run-001/FastGPT`.
5. Paste the task from `cases/pr7008/task.md`.
6. Let OpenHands inspect, implement, and test.
7. After completion, collect diff and test logs into `runs/pr7008`.

## Isolation Rule

The OpenHands container should only receive the `workspaces` directory. Do not mount `cases` or `runs` into OpenHands, because they contain evaluator-only metadata and may later contain golden patches.
