# FastGPT Code Sandbox queueId Concurrency Issue

I have access to a TypeScript/Node.js monorepo in the directory `/projects/pr7008-run-003/FastGPT/`.
You can explore and modify files using the available tools.

Base commit: `4af1ef77674851e30478bef5a9e5cb6ded6db660`

Consider the following issue description:

<issue_description>
FastGPT Code Sandbox currently executes JavaScript and Python sandbox requests through its execution APIs and worker pools. It supports the existing global execution behavior, but it does not support limiting concurrency for requests that belong to the same logical queue or job.

Add optional `queueId`-based concurrency limiting for the Code Sandbox JavaScript and Python execution APIs.

Expected behavior:

- The JavaScript sandbox execution API and the Python sandbox execution API should accept an optional `queueId` field in the request body.
- Add an environment variable named `SANDBOX_QUEUE_ID_CONCURRENCY`.
- If `SANDBOX_QUEUE_ID_CONCURRENCY` is unset or empty, preserve the existing behavior.
- If `SANDBOX_QUEUE_ID_CONCURRENCY` is configured to a positive integer, requests with the same non-empty `queueId` should be limited by FIFO concurrency using that value.
- Requests with different non-empty `queueId` values should not block each other except for normal shared worker capacity.
- Requests without `queueId`, or with an empty or whitespace-only `queueId`, should preserve the existing behavior and should not enter a per-queue limiter.
- Queue slots must be released after execution finishes, including success paths, thrown errors, and rejected executions.
- The FastGPT service-side CodeSandbox client should be able to forward `queueId` when it calls the Code Sandbox service.
- Existing JavaScript and Python sandbox execution behavior, worker lifecycle behavior, resource-limit behavior, and sandbox security behavior should remain unchanged except for the new optional queueId limiting feature.
</issue_description>

Can you help me implement the necessary changes to the repository so that the requirements specified in the `<issue_description>` are met?

I've already taken care of all changes to any test files needed by the evaluation harness. This means you DON'T have to modify the testing logic or any tests in any way.

Your task is to make the minimal changes to non-test source files in the `/projects/pr7008-run-003/FastGPT/` directory to ensure the `<issue_description>` is satisfied. If a very small documentation update is necessary for the new environment variable or request field, keep it narrowly focused and do not rewrite unrelated documentation sections.

Do not look up the original pull request, golden commit, issue discussion, or any online implementation of this change.

Follow these phases to resolve the issue:

Phase 1. READING: read the problem and reword it in clearer terms.
   1.1 Extract API names, option names, environment variables, edge cases, and compatibility requirements.
   1.2 Explain the current behavior that must be preserved.
   1.3 Enumerate the expected behavior for same queueId, different queueIds, missing queueId, empty queueId, success paths, and error paths.

Phase 2. RUNNING: inspect the repository and available development environment.
   2.1 Identify the package manager and relevant scripts from repository files.
   2.2 Do not install unrelated packages.
   2.3 If dependencies or commands are unavailable, report the exact blocker and continue with code inspection and smaller checks.

Phase 3. EXPLORATION: find files related to the problem and possible solutions.
   3.1 Use code search for sandbox execution APIs, request schemas, environment variables, process pools, and CodeSandbox client calls.
   3.2 Identify files related to the problem statement.
   3.3 Propose the methods and files to fix the issue and explain why.
   3.4 Select the most likely minimal fix locations.

Phase 4. REPRODUCTION OR VERIFICATION DESIGN: before implementing any fix, define how you will verify the behavior.
   4.1 Prefer existing scripts and focused checks already available in the repository.
   4.2 You may create a temporary local reproduction script if useful, but remove it before finalizing unless explicitly needed.
   4.3 Do not add or modify test files.

Phase 5. FIX ANALYSIS: state clearly the problem and how to fix it.
   5.1 State where the missing queueId behavior belongs.
   5.2 State how FIFO limiting should preserve existing behavior when disabled or when queueId is absent.
   5.3 State how queue slots will be released on success and failure.
   5.4 State the compatibility risks you need to avoid.

Phase 6. FIX IMPLEMENTATION: edit the source code to implement your chosen solution.
   6.1 Make minimal, focused changes to non-test files.
   6.2 Do not redesign unrelated worker pools, sandbox security, resource limits, or documentation.

Phase 7. VERIFICATION: test your implementation as much as the environment allows.
   7.1 Run formatting/static checks if available.
   7.2 Run the most relevant build or package checks you can run.
   7.3 If a command cannot run, record the exact command and failure reason.

8. FINAL REVIEW: carefully re-read the problem description and compare your changes with the base commit `4af1ef77674851e30478bef5a9e5cb6ded6db660`.
   8.1 Ensure all requirements are addressed.
   8.2 Ensure only necessary non-test files were changed.
   8.3 If any checks fail because of your implementation, revise until they pass.
   8.4 Leave a concise final summary of changed files, verification commands, and remaining gaps.

Be thorough in exploration, testing, and reasoning. Quality and completeness are more important than speed.
