# Public Project template contract

The canonical template is declared in `<plugin-root>/templates/default-project.json` and published as a public GitHub Project. Treat the JSON file as the reviewable snapshot and the Project URL as the copy source.

## Required workflow fields

| Field | Type | Options or purpose |
| --- | --- | --- |
| Status | Single select | Inbox, Ready, In progress, In review, Done, Not planned |
| Priority | Single select | P0, P1, P2, P3 |
| Focus | Single select | Now, Next, Later |
| Size | Single select | S, M, L |
| Area | Single select | Repository-specific architecture or product boundaries |
| Outcome | Text | Delivered result, important trade-offs, and remaining work |
| Start date | Date | Roadmap start |
| Target date | Date | Roadmap target |

GitHub also supplies Title, Assignees, Labels, Linked pull requests, Milestone, Repository, Reviewers, Parent issue, Sub-issues progress, Created, Updated, and Closed.

## Required views

| View | Layout | Configuration |
| --- | --- | --- |
| Board | Board | Vertically group by Status |
| backlog | Table | Filter `status:Inbox,Ready`; group by Priority |
| Completed | Table | Filter `status:Done`; show Outcome; sort by Closed descending |
| Roadmap | Roadmap | Exclude Inbox and Not planned; use Start date |

## API boundary

The GitHub GraphQL API exposes Project view reads but no create/update view mutations. `gh project field-create` can create fields but cannot reconstruct these views. Always create a full board by copying the public template with `gh project copy`, then edit metadata, link the repository, and replace Area options.

## Verification

After copying:

1. Compare Status, Priority, Focus, Size, Outcome, Start date, and Target date with this contract.
2. Confirm all four views exist.
3. Confirm the Project is linked to the intended repository.
4. Confirm visibility matches the requested or repository-derived policy.
5. Confirm Area options match the repository rather than the source template.
