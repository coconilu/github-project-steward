# Issue contract

Use this structure unless the repository has a more specific issue template.

```markdown
## Problem

Describe the current behavior, affected user or maintainer, and why it matters.

## Desired outcome

Describe the observable result without prematurely prescribing the implementation.

## Scope

- Included change
- Included change

## Acceptance criteria

- [ ] Observable, testable condition
- [ ] Required regression or documentation evidence

## Non-goals

- Adjacent work deliberately excluded from this issue

## Dependencies and risks

- Dependency, migration, compatibility, security, or uncertainty

## Evidence

- Relevant file, screenshot, log, discussion, benchmark, or link
```

## Splitting rule

Split an idea into multiple issues when any of these differ:

- independent user outcomes;
- separate deploy or rollback boundaries;
- different repository modules or owners;
- different validation strategies;
- one part can ship while another remains blocked.

Use a parent tracking issue only when the pieces form one coherent milestone. Avoid turning a parent issue into a second copy of every child specification.

## Default Project placement

| Field | Default | Change when |
| --- | --- | --- |
| Status | Inbox | The user explicitly approves it as Ready |
| Priority | P2 | Evidence supports urgent impact or strategic sequencing |
| Focus | Later | It is approved for Now or deliberately queued Next |
| Size | M | Repository evidence supports a smaller or larger coherent scope |
| Area | Required when a Project is used | Select an existing option; never invent a value silently |
