---
name: github-project-board
description: Create, copy, link, list, inspect, and render GitHub Projects for repositories. Use when a user asks to create a Project board from the reusable public template, list all Projects, show one Project, or display every Project as a separate Markdown table.
---

# GitHub Project Board

Use the bundled CLI for deterministic GitHub mutations and table rendering. Resolve `<plugin-root>` as the directory two levels above this skill folder, then run `<plugin-root>/scripts/project_steward.py` with Python 3.

## Preflight

Run this before the first GitHub operation:

```text
python <plugin-root>/scripts/project_steward.py preflight
```

Require `gh`, an authenticated GitHub account, `project` scope, and repository access. If preflight fails, report the exact failing check and stop before mutations.

## Choose the operation

- List project metadata: run `list-projects --owner <login>`.
- Show one project: run `show-project --owner <login> --number <n>`.
- Show every project as its own table: run `dashboard --owner <login>`.
- Create a repository board: inspect the repository first, choose useful Area options, run `create-project --dry-run`, then run it without `--dry-run` when the request already authorizes creation.

Prefer `--json` when another reasoning step must consume the result. Return Markdown output directly for human-facing board requests.

## Create a board

1. Resolve the target repository with `gh repo view` through the CLI.
2. Default the Project owner to the repository owner. Override it only when the user names another owner.
3. Derive Area options from real product or architecture boundaries. Keep `Cross-cutting`; avoid copying directory names blindly.
4. Preserve repository privacy: default a private repository to a private Project and a public repository to a public Project.
5. Check for an exact title match before creating. Never create a duplicate silently.
6. Copy the public mother Project so Board, backlog, Completed, and Roadmap views survive. GitHub's public API does not expose view creation.
7. Link the new Project to the repository and verify its fields and views after creation.

Example:

```text
python <plugin-root>/scripts/project_steward.py create-project --repo owner/repo --areas "Core,Web,API,Docs,Cross-cutting" --dry-run
```

Read [references/template-contract.md](references/template-contract.md) when creating or diagnosing a board.

## Safety

- Treat `create-project` and `set-item-fields` as write operations.
- Do not delete a partially configured Project automatically. Return its URL and repair it with `--reuse-existing` only after inspection.
- Never weaken visibility to public for a private repository unless explicitly requested.
- Do not claim that a copied board is configured until fields, views, and repository linkage have been verified.
