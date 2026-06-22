# FastGPT PR 7008 Validation

This case evaluates whether an agent can implement queueId-based concurrency limiting for FastGPT Code Sandbox.

## Baseline And Golden

- Baseline commit: `4af1ef77674851e30478bef5a9e5cb6ded6db660`
- Golden merge commit: `bd140f7144d9fe979b866740859a0e18b9659e87`
- Upstream PR: `https://github.com/labring/FastGPT/pull/7008`

Do not expose the golden commit or PR URL to the evaluated agent.

## Recommended Validation Commands

Run from the FastGPT workspace after the agent finishes:

```powershell
git diff --check
cd projects/code-sandbox
$env:SANDBOX_MAX_MEMORY_MB="256"
$env:SANDBOX_TOKEN="test"
$env:SANDBOX_QUEUE_ID_CONCURRENCY="1"
pnpm test
pnpm build
```

## Evaluation Dimensions

- Behavior: same queueId is limited by FIFO concurrency; different queueIds remain independent; slots release on success and failure.
- Compatibility: empty or unset `SANDBOX_QUEUE_ID_CONCURRENCY` preserves previous behavior.
- Integration: `/sandbox/js`, `/sandbox/python`, and the service-side CodeSandbox client support `queueId`.
- Test quality: unit tests cover limiter edge cases; integration tests cover API behavior.
- Engineering quality: implementation is small, maintainable, and avoids unrelated rewrites.
- Documentation: README or upgrade notes mention the new env var and request field.
