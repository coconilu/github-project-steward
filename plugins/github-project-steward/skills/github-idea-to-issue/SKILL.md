---
name: github-idea-to-issue
description: Turn a product, engineering, maintenance, or documentation idea into a well-scoped GitHub issue and optionally add it to a GitHub Project with workflow fields. Use when a user asks to capture, push, record, split, or manage an idea as an issue.
---

# GitHub Idea to Issue

Resolve `<plugin-root>` as the directory two levels above this skill folder. Use `<plugin-root>/scripts/project_steward.py` for issue creation and Project field updates.

## Workflow

1. Inspect the target repository, its contribution rules, open issues, labels, and linked Project before drafting.
2. Search for likely duplicates by stable nouns and affected modules. Prefer updating an existing issue when it already represents the idea.
3. Convert the idea into an outcome-oriented issue using [references/issue-contract.md](references/issue-contract.md).
4. Split the idea when independently testable outcomes or different risk owners would otherwise share one issue.
5. Infer conservative Project defaults: Status `Inbox`, Priority `P2`, Focus `Later`, Size `M`. Choose Area from the actual Project options.
6. Use `create-issue --dry-run` when authorization is ambiguous. A direct request to push or create the issue authorizes creation.
7. Create the issue, add it to the Project, update its fields, and return the issue URL plus the resulting Project placement.

Example:

```text
python <plugin-root>/scripts/project_steward.py create-issue --repo owner/repo --title "Concise outcome" --body-file issue.md --project-owner owner --project-number 1 --priority P1 --focus Now --area Core --size M
```

## Quality gate

Require all of these before creation:

- The problem and user or maintainer impact are concrete.
- The proposed scope has an observable completion condition.
- Acceptance criteria are testable.
- Non-goals prevent the issue from absorbing adjacent work.
- Dependencies, risks, and evidence are included when known.

Do not invent repository facts. Mark uncertain assumptions explicitly in the issue body.

## Partial failure

If GitHub creates the issue but Project insertion or field assignment fails, preserve the issue, report its URL, and repair the Project placement separately. Never create a duplicate issue to recover from a field error.
