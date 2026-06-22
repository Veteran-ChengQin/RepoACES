# FastGPT Code Sandbox Queue Concurrency Task

You are working in the FastGPT repository.

Implement queueId-based concurrency limiting for the Code Sandbox JS/Python execution APIs.

## Requirements

- `/sandbox/js` and `/sandbox/python` should accept an optional `queueId`.
- Add `SANDBOX_QUEUE_ID_CONCURRENCY`.
- If `SANDBOX_QUEUE_ID_CONCURRENCY` is unset or empty, preserve existing behavior.
- If configured, requests with the same `queueId` must be limited by FIFO concurrency.
- Requests with different `queueId` values should not block each other unnecessarily.
- The queue slot must be released after execution finishes, including error paths.
- The FastGPT service-side CodeSandbox client should be able to forward `queueId`.
- Add focused unit tests for the limiter behavior.
- Add or update integration tests for the sandbox APIs.
- Update relevant README or upgrade docs.

## Working Instructions

- Do not look up the original pull request or any online implementation of this change.
- Inspect the existing codebase first.
- Propose a short implementation plan before editing.
- Keep the change focused on the Code Sandbox queue concurrency feature.
- Run the most relevant tests you can run in this environment.
- Leave a concise summary of changed files, test commands, and any remaining gaps.
