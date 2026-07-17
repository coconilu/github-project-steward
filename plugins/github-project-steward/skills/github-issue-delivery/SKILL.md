---
name: github-issue-delivery
description: Inventory, prioritize, and sequentially deliver multiple GitHub issues with two independent Codex agents, one developer who implements and updates the pull request and one read-only reviewer who repeats review until no blocking findings remain. Use for batch issue planning or developer-reviewer issue execution.
---

# GitHub Issue Delivery

Run a gated, sequential delivery queue. Use exactly one developer and one independent reviewer per active issue. Never let both agents write to the same worktree.

Resolve `<plugin-root>` as the directory two levels above this skill folder. Use `<plugin-root>/scripts/project_steward.py` for inventory and Project field updates.

## Plan the queue

1. Run `preflight`, then `issue-inventory --repo owner/repo --json`.
2. Load the linked Project with `show-project --json` when available.
3. Exclude blocked, duplicate, Not planned, and already-delivered issues.
4. Order work by dependency unblocking, explicit Priority and Focus, user value, risk reduction, and then smallest coherent Size.
5. Show the proposed sequence, rationale, dependencies, and expected verification.
6. Obtain user approval before starting a batch unless the request explicitly authorizes executing the queue.

Read [references/delivery-protocol.md](references/delivery-protocol.md) before spawning agents.

## Deliver one issue

1. Verify a clean, understood base branch and passing baseline checks.
2. Set the Project item to `In progress`.
3. Spawn the `developer` agent with the issue, acceptance criteria, repository instructions, branch name, validation commands, and PR requirement. Only this agent may edit, commit, and push.
4. Wait until the developer opens or updates a pull request that links the issue.
5. Set the Project item to `In review`.
6. Spawn the `reviewer` agent after the PR exists. Keep it read-only. Require prioritized findings with file and line evidence, check results, and a verdict of `approve` or `changes_requested`.
7. If changes are requested, send every actionable finding to the same developer, wait for fixes and verification, then ask the same reviewer to re-review the new commit range.
8. Repeat until the reviewer reports no blocking findings and required checks pass.
9. Record a concise Outcome. Leave the PR ready for human merge unless the user explicitly requested and authorized merge.
10. Continue to the next issue only after the current review gate passes.

## Hard boundaries

- Do not simulate two roles in one agent when subagent tools are unavailable; report the missing capability.
- Do not develop multiple issues concurrently by default. Sequential order protects dependencies and review isolation.
- Do not let the reviewer modify files, push commits, or silently fix findings.
- Do not merge merely because review is clean.
- Stop for failing baseline checks, unclear destructive migrations, secrets, permission changes, or product decisions not covered by the issue.
- Preserve user changes and never stage an unrelated dirty worktree.
