# Developer-reviewer delivery protocol

## Agent contracts

| Role | May write | Required output | Forbidden |
| --- | --- | --- | --- |
| Developer | Issue branch and PR | Implementation, tests, commits, pushed branch, linked PR, validation summary | Self-approval, unrelated cleanup, merge without authorization |
| Reviewer | No | Evidence-backed findings, check status, `approve` or `changes_requested` | File edits, commits, pushes, vague approval |

## Developer prompt contract

Include:

- repository and issue URL;
- exact issue acceptance criteria and non-goals;
- base and branch naming requirements;
- relevant `AGENTS.md` instructions;
- allowed file and system scope;
- required tests and static checks;
- requirement to use `Closes #<number>` in the PR body;
- requirement to report the PR URL and current commit SHA.

Require the developer to inspect the live repository before changing files. Do not tell it the expected code solution unless the issue already mandates one.

## Reviewer prompt contract

Include only the repository, issue, PR, base/head commits, repository instructions, and required checks. Do not pass the developer's private reasoning or an expected verdict.

Require this response shape:

```text
verdict: approve | changes_requested
checked_commit: <sha>
checks: <pass/fail/pending summary>
findings:
  - priority: P0 | P1 | P2 | P3
    location: <file:line>
    evidence: <specific failure or risk>
    required_change: <bounded remediation>
```

`approve` requires no P0, P1, or P2 findings and all required checks passing. P3 suggestions may remain only when explicitly non-blocking.

## State sequence

```text
Ready
  ↓ developer starts
In progress
  ↓ PR exists
In review
  ↓ reviewer requests changes
In progress
  ↓ developer pushes fixes
In review
  ↓ reviewer approves + checks pass
PR ready for human merge
```

Set Done only after the repository's completion policy is satisfied, normally after merge. Record Outcome when the review gate passes or after merge, whichever policy the user chose.

## Retry and stop rules

- Reuse the same developer so it owns remediation context.
- Reuse the same reviewer but require it to inspect the new commit SHA.
- Cap identical unresolved review cycles at three; then stop and surface the architectural or product decision.
- Stop immediately for secrets, unexplained generated files, destructive data migration, broadened permissions, or unrelated user changes.
- Do not begin the next issue while the current issue has blocking findings or failing required checks.
