#!/usr/bin/env python3
"""Deterministic GitHub Projects and issue operations for GitHub Project Steward.

The Codex skills own planning and judgment. This CLI owns repeatable GitHub CLI
calls, field updates, idempotency checks, and Markdown rendering.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE_FILE = PLUGIN_ROOT / "templates" / "default-project.json"
STATUS_ORDER = {
    "In progress": 0,
    "In review": 1,
    "Ready": 2,
    "Inbox": 3,
    "Done": 4,
    "Not planned": 5,
    "": 6,
}
FOCUS_ORDER = {"Now": 0, "Next": 1, "Later": 2, "": 3}
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "": 4}
OPTION_COLORS = ["BLUE", "PURPLE", "GREEN", "ORANGE", "YELLOW", "PINK", "RED", "GRAY"]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


class StewardError(RuntimeError):
    """A user-actionable error without a Python traceback by default."""


@dataclass(frozen=True)
class RepoInfo:
    name_with_owner: str
    owner: str
    name: str
    url: str
    description: str
    is_private: bool


class Gh:
    """Small, injectable wrapper around the GitHub CLI."""

    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or shutil.which("gh") or ""
        if not self.executable:
            raise StewardError("GitHub CLI `gh` is required but was not found on PATH.")

    def run(
        self,
        args: Sequence[str],
        *,
        input_text: str | None = None,
        expect_json: bool = False,
    ) -> Any:
        command = [self.executable, *args]
        retryable = self._is_retryable(args, input_text)
        direct_env_candidate = self._direct_fallback_env() if retryable else None
        attempts = (2 if direct_env_candidate is not None else 4) if retryable else 1
        completed: subprocess.CompletedProcess[str] | None = None
        last_detail = ""
        for attempt in range(attempts):
            completed = subprocess.run(
                command,
                input=input_text,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if completed.returncode == 0:
                break
            last_detail = (completed.stderr or completed.stdout).strip()
            transient = self._is_transient(last_detail)
            auth_probe = tuple(args[:2]) == ("auth", "status")
            if attempt + 1 >= attempts or not transient:
                direct_env = direct_env_candidate if retryable and (transient or auth_probe) else None
                if direct_env is not None:
                    direct = subprocess.run(
                        command,
                        input=input_text,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        check=False,
                        env=direct_env,
                    )
                    if direct.returncode == 0:
                        completed = direct
                        break
                    direct_detail = (direct.stderr or direct.stdout).strip()
                    last_detail = f"{last_detail}\nDirect fallback also failed: {direct_detail}"
                rendered = " ".join(command[:4])
                suffix = f"\nFailed after {attempt + 1} attempt(s)." if retryable else ""
                raise StewardError(f"GitHub command failed: {rendered}\n{last_detail}{suffix}")
            time.sleep(0.4 * (2**attempt))

        assert completed is not None
        output = completed.stdout.strip()
        if not expect_json:
            return output
        if not output:
            return {}
        try:
            return json.loads(output)
        except json.JSONDecodeError as exc:
            raise StewardError(f"GitHub returned invalid JSON: {exc}") from exc

    @staticmethod
    def _is_retryable(args: Sequence[str], input_text: str | None) -> bool:
        prefix = tuple(args[:2])
        if prefix in {
            ("auth", "status"),
            ("repo", "view"),
            ("project", "list"),
            ("project", "view"),
            ("project", "field-list"),
            ("project", "item-list"),
            ("issue", "list"),
        }:
            return True
        if prefix == ("api", "user"):
            return True
        if prefix == ("api", "graphql") and input_text:
            try:
                query = str(json.loads(input_text).get("query", "")).lstrip()
            except json.JSONDecodeError:
                return False
            return query.startswith("query")
        return False

    @staticmethod
    def _is_transient(detail: str) -> bool:
        lowered = detail.casefold()
        return any(
            marker in lowered
            for marker in (
                "eof",
                "unknown owner type",
                "connection reset",
                "connection refused",
                "timeout",
                "timed out",
                "temporary failure",
                "http 502",
                "http 503",
                "http 504",
                "stream error",
            )
        )

    @staticmethod
    def _direct_fallback_env() -> dict[str, str] | None:
        if os.environ.get("GH_STEWARD_DISABLE_DIRECT_FALLBACK", "").casefold() in {"1", "true", "yes"}:
            return None
        proxy_keys = {"http_proxy", "https_proxy", "all_proxy"}
        configured = [(key, value) for key, value in os.environ.items() if key.casefold() in proxy_keys and value]
        if not configured:
            return None
        for _, value in configured:
            host = (urlparse(value).hostname or "").casefold()
            if host not in {"127.0.0.1", "localhost", "::1"}:
                return None
        return {key: value for key, value in os.environ.items() if key.casefold() not in proxy_keys}

    def graphql(self, query: str, variables: Mapping[str, Any]) -> dict[str, Any]:
        payload = json.dumps({"query": query, "variables": dict(variables)}, ensure_ascii=False)
        result = self.run(["api", "graphql", "--input", "-"], input_text=payload, expect_json=True)
        if result.get("errors"):
            messages = "; ".join(str(error.get("message", error)) for error in result["errors"])
            raise StewardError(f"GitHub GraphQL request failed: {messages}")
        return result.get("data", {})


def load_template(path: Path = DEFAULT_TEMPLATE_FILE) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StewardError(f"Template metadata is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise StewardError(f"Template metadata is invalid JSON: {path}: {exc}") from exc


def repo_info(gh: Gh, repo: str | None) -> RepoInfo:
    args = [
        "repo",
        "view",
        "--json",
        "nameWithOwner,name,owner,url,description,isPrivate",
    ]
    if repo:
        args.insert(2, repo)
    data = gh.run(args, expect_json=True)
    owner = data.get("owner") or {}
    owner_login = owner.get("login") if isinstance(owner, dict) else str(owner)
    return RepoInfo(
        name_with_owner=str(data["nameWithOwner"]),
        owner=str(owner_login),
        name=str(data["name"]),
        url=str(data["url"]),
        description=str(data.get("description") or ""),
        is_private=bool(data.get("isPrivate")),
    )


def current_login(gh: Gh) -> str:
    data = gh.run(["api", "user"], expect_json=True)
    return str(data["login"])


def project_list(gh: Gh, owner: str, limit: int = 100) -> list[dict[str, Any]]:
    data = gh.run(
        ["project", "list", "--owner", owner, "--format", "json", "--limit", str(limit)],
        expect_json=True,
    )
    return list(data.get("projects", []))


def project_items(gh: Gh, owner: str, number: int, limit: int = 200) -> list[dict[str, Any]]:
    data = gh.run(
        [
            "project",
            "item-list",
            str(number),
            "--owner",
            owner,
            "--format",
            "json",
            "--limit",
            str(limit),
        ],
        expect_json=True,
    )
    return list(data.get("items", []))


def project_metadata(gh: Gh, owner: str, number: int) -> dict[str, Any]:
    return gh.run(
        ["project", "view", str(number), "--owner", owner, "--format", "json"],
        expect_json=True,
    )


PROJECT_VIEWS_QUERY = """
query($projectId: ID!) {
  node(id: $projectId) {
    ... on ProjectV2 {
      views(first: 20) { nodes { number name layout filter } }
    }
  }
}
"""


def project_views(gh: Gh, project_id: str) -> list[dict[str, Any]]:
    data = gh.graphql(PROJECT_VIEWS_QUERY, {"projectId": project_id})
    project = data.get("node") or {}
    return list(((project.get("views") or {}).get("nodes")) or [])


def markdown_escape(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ")
    return text.replace("|", "\\|")


def markdown_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    rendered_rows = [[markdown_escape(cell) for cell in row] for row in rows]
    header = "| " + " | ".join(markdown_escape(cell) for cell in headers) + " |"
    divider = "| " + " | ".join("---" for _ in headers) + " |"
    lines = [header, divider]
    lines.extend("| " + " | ".join(row) + " |" for row in rendered_rows)
    return "\n".join(lines)


def item_value(item: Mapping[str, Any], name: str) -> Any:
    candidates = [name, name.lower(), name.casefold()]
    for key in candidates:
        if key in item:
            return item[key]
    for key, value in item.items():
        if str(key).casefold() == name.casefold():
            return value
    return ""


def item_content(item: Mapping[str, Any]) -> Mapping[str, Any]:
    content = item.get("content")
    return content if isinstance(content, Mapping) else {}


def item_sort_key(item: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        STATUS_ORDER.get(str(item_value(item, "Status")), 99),
        FOCUS_ORDER.get(str(item_value(item, "Focus")), 99),
        PRIORITY_ORDER.get(str(item_value(item, "Priority")), 99),
        str(item.get("title") or item_content(item).get("title") or "").casefold(),
    )


def is_completed_item(item: Mapping[str, Any]) -> bool:
    return str(item_value(item, "Status")).strip().casefold() == "done"


def filter_project_items(
    items: Sequence[Mapping[str, Any]], *, include_completed: bool = False
) -> tuple[list[Mapping[str, Any]], int]:
    if include_completed:
        return list(items), 0
    visible = [item for item in items if not is_completed_item(item)]
    return visible, len(items) - len(visible)


def assignees_text(item: Mapping[str, Any]) -> str:
    values = item.get("assignees") or item_content(item).get("assignees") or []
    if isinstance(values, str):
        return values
    if not isinstance(values, list):
        return ""
    names: list[str] = []
    for value in values:
        if isinstance(value, Mapping):
            names.append(str(value.get("login") or value.get("name") or ""))
        else:
            names.append(str(value))
    return ", ".join(name for name in names if name)


def render_projects(projects: Sequence[Mapping[str, Any]], owner: str) -> str:
    rows = []
    for project in projects:
        rows.append(
            [
                project.get("number", ""),
                f"[{project.get('title', '')}]({project.get('url', '')})",
                "Closed" if project.get("closed") else "Open",
                "Public" if project.get("public") else "Private",
                (project.get("items") or {}).get("totalCount", ""),
                (project.get("fields") or {}).get("totalCount", ""),
            ]
        )
    title = f"## GitHub Projects — {owner}"
    if not rows:
        return f"{title}\n\n_No projects found._"
    return f"{title}\n\n" + markdown_table(
        ["#", "Project", "State", "Visibility", "Items", "Fields"], rows
    )


def render_project_board(
    metadata: Mapping[str, Any],
    items: Sequence[Mapping[str, Any]],
    views: Sequence[Mapping[str, Any]],
    *,
    completed_hidden: int = 0,
) -> str:
    title = str(metadata.get("title") or f"Project {metadata.get('number', '')}")
    url = str(metadata.get("url") or "")
    view_names = ", ".join(str(view.get("name")) for view in views if view.get("name"))
    heading = f"## [{title}]({url})" if url else f"## {title}"
    summary = f"Views: {view_names}" if view_names else "Views: unavailable"
    if completed_hidden:
        summary += f" · Done hidden: {completed_hidden} (use --include-completed to show)"
    rows = []
    for item in sorted(items, key=item_sort_key):
        content = item_content(item)
        item_url = content.get("url") or item.get("url") or ""
        item_title = item.get("title") or content.get("title") or ""
        linked_title = f"[{item_title}]({item_url})" if item_url else item_title
        rows.append(
            [
                item_value(item, "Status"),
                item_value(item, "Priority"),
                item_value(item, "Focus"),
                item_value(item, "Area"),
                item_value(item, "Size"),
                content.get("type") or item.get("type") or "",
                content.get("number") or item.get("number") or "",
                linked_title,
                assignees_text(item),
            ]
        )
    if not rows and completed_hidden:
        noun = "item" if completed_hidden == 1 else "items"
        table = (
            f"_No active items. {completed_hidden} completed {noun} hidden; "
            "use --include-completed to show them._"
        )
    elif not rows:
        table = "_No items in this project._"
    else:
        table = markdown_table(
            ["Status", "Priority", "Focus", "Area", "Size", "Type", "#", "Title", "Assignees"],
            rows,
        )
    return f"{heading}\n\n{summary}\n\n{table}"


def normalize_csv(value: str | None) -> list[str]:
    if not value:
        return []
    result: list[str] = []
    for part in value.split(","):
        cleaned = part.strip()
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


def project_readme(repo: RepoInfo) -> str:
    return f"""Managed repository: [{repo.name_with_owner}]({repo.url})

## Workflow

- Status: Inbox → Ready → In progress → In review → Done; declined work goes to Not planned.
- Priority ranks work inside the repository; Focus separates Now, Next, and Later.
- Area identifies the product or architecture boundary; Size is S, M, or L.
- Pull requests use `Closes #<number>` and record the delivered result in Outcome.
- Board, backlog, Completed, and Roadmap support execution, triage, review, and planning.
"""


def project_fields(gh: Gh, owner: str, number: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    metadata = project_metadata(gh, owner, number)
    data = gh.run(
        ["project", "field-list", str(number), "--owner", owner, "--format", "json", "--limit", "100"],
        expect_json=True,
    )
    return metadata, list(data.get("fields", []))


UPDATE_SINGLE_SELECT_QUERY = """
mutation($fieldId: ID!, $options: [ProjectV2SingleSelectFieldOptionInput!]!) {
  updateProjectV2Field(input: {fieldId: $fieldId, singleSelectOptions: $options}) {
    projectV2Field {
      ... on ProjectV2SingleSelectField { id name options { id name color description } }
    }
  }
}
"""


def update_area_options(gh: Gh, owner: str, number: int, areas: Sequence[str]) -> None:
    if not areas:
        return
    _, fields = project_fields(gh, owner, number)
    area_field = next((field for field in fields if field.get("name") == "Area"), None)
    if not area_field:
        raise StewardError(f"Project {owner}/{number} does not contain an Area field.")
    options = [
        {
            "name": name,
            "color": OPTION_COLORS[index % len(OPTION_COLORS)],
            "description": f"Work in the {name} area",
        }
        for index, name in enumerate(areas)
    ]
    gh.graphql(UPDATE_SINGLE_SELECT_QUERY, {"fieldId": area_field["id"], "options": options})


def find_existing_project(projects: Sequence[Mapping[str, Any]], title: str) -> Mapping[str, Any] | None:
    expected = title.strip().casefold()
    return next((project for project in projects if str(project.get("title", "")).strip().casefold() == expected), None)


def create_project(
    gh: Gh,
    *,
    repo: RepoInfo,
    target_owner: str,
    title: str,
    description: str,
    visibility: str,
    areas: Sequence[str],
    template_owner: str,
    template_number: int,
    reuse_existing: bool,
    dry_run: bool,
) -> dict[str, Any]:
    existing = find_existing_project(project_list(gh, target_owner), title)
    if existing and not reuse_existing:
        raise StewardError(
            f'A project titled "{title}" already exists at {existing.get("url")}. '
            "Use --reuse-existing only after confirming it is the intended board."
        )

    plan = {
        "action": "reuse" if existing else "copy",
        "repository": repo.name_with_owner,
        "targetOwner": target_owner,
        "title": title,
        "visibility": visibility,
        "areas": list(areas),
        "template": {"owner": template_owner, "number": template_number},
    }
    if dry_run:
        return {"dryRun": True, **plan}

    if existing:
        created = dict(existing)
    else:
        created = gh.run(
            [
                "project",
                "copy",
                str(template_number),
                "--source-owner",
                template_owner,
                "--target-owner",
                target_owner,
                "--title",
                title,
                "--format",
                "json",
            ],
            expect_json=True,
        )

    number = int(created["number"])
    try:
        gh.run(
            [
                "project",
                "edit",
                str(number),
                "--owner",
                target_owner,
                "--description",
                description,
                "--readme",
                project_readme(repo),
                "--visibility",
                visibility,
                "--format",
                "json",
            ],
            expect_json=True,
        )
        gh.run(
            [
                "project",
                "link",
                str(number),
                "--owner",
                target_owner,
                "--repo",
                repo.name_with_owner,
            ]
        )
        update_area_options(gh, target_owner, number, areas)
    except StewardError as exc:
        url = created.get("url", "")
        raise StewardError(
            f"Project was created but configuration stopped partway through. "
            f"Inspect {url or f'{target_owner}/{number}'} before retrying with --reuse-existing.\n{exc}"
        ) from exc

    result = project_metadata(gh, target_owner, number)
    result["template"] = {"owner": template_owner, "number": template_number}
    result["repository"] = repo.name_with_owner
    result["areas"] = list(areas)
    return result


def field_lookup(fields: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {str(field.get("name", "")).casefold(): field for field in fields}


def set_project_item_fields(
    gh: Gh,
    *,
    owner: str,
    project_number: int,
    item_id: str,
    values: Mapping[str, str | None],
) -> dict[str, str]:
    metadata, fields = project_fields(gh, owner, project_number)
    project_id = str(metadata["id"])
    by_name = field_lookup(fields)
    updated: dict[str, str] = {}

    for name, raw_value in values.items():
        value = (raw_value or "").strip()
        if not value:
            continue
        field = by_name.get(name.casefold())
        if not field:
            raise StewardError(f'Project field "{name}" was not found in {owner}/{project_number}.')
        args = [
            "project",
            "item-edit",
            "--id",
            item_id,
            "--project-id",
            project_id,
            "--field-id",
            str(field["id"]),
        ]
        options = field.get("options") or []
        if options:
            option = next(
                (option for option in options if str(option.get("name", "")).casefold() == value.casefold()),
                None,
            )
            if not option:
                allowed = ", ".join(str(option.get("name")) for option in options)
                raise StewardError(f'Invalid {name} value "{value}". Allowed values: {allowed}.')
            args.extend(["--single-select-option-id", str(option["id"])])
        else:
            args.extend(["--text", value])
        gh.run(args)
        updated[name] = value
    return updated


def create_issue(
    gh: Gh,
    *,
    repo: str,
    title: str,
    body: str,
    labels: Sequence[str],
    assignees: Sequence[str],
    project_owner: str | None,
    project_number: int | None,
    field_values: Mapping[str, str | None],
    dry_run: bool,
) -> dict[str, Any]:
    plan = {
        "repository": repo,
        "title": title,
        "labels": list(labels),
        "assignees": list(assignees),
        "projectOwner": project_owner,
        "projectNumber": project_number,
        "fields": {key: value for key, value in field_values.items() if value},
    }
    if dry_run:
        return {"dryRun": True, **plan, "body": body}

    args = ["issue", "create", "--repo", repo, "--title", title, "--body", body]
    for label in labels:
        args.extend(["--label", label])
    for assignee in assignees:
        args.extend(["--assignee", assignee])
    issue_url = str(gh.run(args)).strip()
    match = re.search(r"/issues/(\d+)(?:\D|$)", issue_url)
    issue_number = int(match.group(1)) if match else None

    result: dict[str, Any] = {"url": issue_url, "number": issue_number, **plan}
    if project_owner is None and project_number is None:
        return result
    if not project_owner or project_number is None:
        raise StewardError("--project-owner and --project-number must be supplied together.")

    try:
        item = gh.run(
            [
                "project",
                "item-add",
                str(project_number),
                "--owner",
                project_owner,
                "--url",
                issue_url,
                "--format",
                "json",
            ],
            expect_json=True,
        )
        item_id = str(item["id"])
        updated = set_project_item_fields(
            gh,
            owner=project_owner,
            project_number=project_number,
            item_id=item_id,
            values=field_values,
        )
        result["projectItemId"] = item_id
        result["updatedFields"] = updated
    except StewardError as exc:
        raise StewardError(
            f"Issue {issue_url} was created, but adding or configuring its project item failed.\n{exc}"
        ) from exc
    return result


def issue_inventory(gh: Gh, repo: str, limit: int) -> list[dict[str, Any]]:
    return list(
        gh.run(
            [
                "issue",
                "list",
                "--repo",
                repo,
                "--state",
                "open",
                "--limit",
                str(limit),
                "--json",
                "number,title,url,labels,assignees,milestone,createdAt,updatedAt,body",
            ],
            expect_json=True,
        )
    )


def render_issues(issues: Sequence[Mapping[str, Any]], repo: str) -> str:
    rows = []
    for issue in issues:
        labels = issue.get("labels") or []
        label_text = ", ".join(
            str(label.get("name") if isinstance(label, Mapping) else label) for label in labels
        )
        assignees = issue.get("assignees") or []
        assignee_text = ", ".join(
            str(value.get("login") if isinstance(value, Mapping) else value) for value in assignees
        )
        milestone = issue.get("milestone") or {}
        rows.append(
            [
                issue.get("number", ""),
                f"[{issue.get('title', '')}]({issue.get('url', '')})",
                label_text,
                milestone.get("title", "") if isinstance(milestone, Mapping) else milestone,
                assignee_text,
                str(issue.get("updatedAt", ""))[:10],
            ]
        )
    if not rows:
        return f"## Open issues — {repo}\n\n_No open issues found._"
    return f"## Open issues — {repo}\n\n" + markdown_table(
        ["#", "Issue", "Labels", "Milestone", "Assignees", "Updated"], rows
    )


def emit(data: Any, *, as_json: bool, markdown: str | None = None) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif markdown is not None:
        print(markdown)
    elif isinstance(data, Mapping):
        rows = [(key, json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value) for key, value in data.items()]
        print(markdown_table(["Field", "Value"], rows))
    else:
        print(data)


def add_common_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")


def build_parser() -> argparse.ArgumentParser:
    template = load_template()
    source = template.get("source") or {}
    parser = argparse.ArgumentParser(
        description="Create and operate GitHub Projects using the GitHub Project Steward template."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser("preflight", help="Verify gh authentication and project access.")
    add_common_json(preflight)

    list_parser = subparsers.add_parser("list-projects", help="List all Projects for an owner.")
    list_parser.add_argument("--owner", default="@me")
    list_parser.add_argument("--limit", type=int, default=100)
    add_common_json(list_parser)

    show = subparsers.add_parser("show-project", help="Render one Project as a Markdown table.")
    show.add_argument("--owner", default="@me")
    show.add_argument("--number", required=True, type=int)
    show.add_argument("--limit", type=int, default=200)
    show.add_argument(
        "--include-completed",
        action="store_true",
        help="Include items whose Project Status is Done; hidden by default.",
    )
    add_common_json(show)

    dashboard = subparsers.add_parser(
        "dashboard", help="Render every Project for an owner as its own Markdown table."
    )
    dashboard.add_argument("--owner", default="@me")
    dashboard.add_argument("--project-limit", type=int, default=100)
    dashboard.add_argument("--item-limit", type=int, default=200)
    dashboard.add_argument(
        "--include-completed",
        action="store_true",
        help="Include items whose Project Status is Done; hidden by default.",
    )
    add_common_json(dashboard)

    create = subparsers.add_parser("create-project", help="Copy the public template for a repository.")
    create.add_argument("--repo", help="owner/name; defaults to the current repository.")
    create.add_argument("--target-owner", help="Defaults to the repository owner.")
    create.add_argument("--title")
    create.add_argument("--description")
    create.add_argument("--visibility", choices=["PUBLIC", "PRIVATE"])
    create.add_argument(
        "--areas",
        default=",".join(template.get("fields", {}).get("Area", {}).get("options", [])),
        help="Comma-separated Area options.",
    )
    create.add_argument("--template-owner", default=source.get("owner", "coconilu"))
    create.add_argument("--template-number", type=int, default=int(source.get("number", 4)))
    create.add_argument("--reuse-existing", action="store_true")
    create.add_argument("--dry-run", action="store_true")
    add_common_json(create)

    issue = subparsers.add_parser("create-issue", help="Create an issue and optionally add it to a Project.")
    issue.add_argument("--repo", required=True)
    issue.add_argument("--title", required=True)
    body_group = issue.add_mutually_exclusive_group(required=True)
    body_group.add_argument("--body")
    body_group.add_argument("--body-file", type=Path)
    issue.add_argument("--labels", help="Comma-separated labels.")
    issue.add_argument("--assignees", help="Comma-separated GitHub logins.")
    issue.add_argument("--project-owner")
    issue.add_argument("--project-number", type=int)
    issue.add_argument("--status", default="Inbox")
    issue.add_argument("--priority", default="P2")
    issue.add_argument("--focus", default="Later")
    issue.add_argument("--area")
    issue.add_argument("--size", default="M")
    issue.add_argument("--dry-run", action="store_true")
    add_common_json(issue)

    inventory = subparsers.add_parser("issue-inventory", help="List open issues for planning.")
    inventory.add_argument("--repo", required=True)
    inventory.add_argument("--limit", type=int, default=200)
    add_common_json(inventory)

    set_fields = subparsers.add_parser("set-item-fields", help="Update workflow fields on a Project item.")
    set_fields.add_argument("--owner", required=True)
    set_fields.add_argument("--project-number", required=True, type=int)
    set_fields.add_argument("--item-id", required=True)
    set_fields.add_argument("--status")
    set_fields.add_argument("--priority")
    set_fields.add_argument("--focus")
    set_fields.add_argument("--area")
    set_fields.add_argument("--size")
    set_fields.add_argument("--outcome")
    add_common_json(set_fields)
    return parser


def command_preflight(args: argparse.Namespace, gh: Gh) -> None:
    version = gh.run(["--version"]).splitlines()[0]
    auth = gh.run(["auth", "status"])
    login = current_login(gh)
    projects = project_list(gh, login, limit=1)
    data = {"ok": True, "login": login, "gh": version, "projectAccess": True, "sampleCount": len(projects)}
    emit(data, as_json=args.json, markdown=markdown_table(["Check", "Result"], [
        ["GitHub CLI", version], ["Authenticated login", login], ["Projects API", "Available"],
        ["Auth detail", auth.replace("\n", " · ")],
    ]))


def command_list_projects(args: argparse.Namespace, gh: Gh) -> None:
    owner = current_login(gh) if args.owner == "@me" else args.owner
    projects = project_list(gh, owner, args.limit)
    emit({"owner": owner, "projects": projects}, as_json=args.json, markdown=render_projects(projects, owner))


def board_payload(
    gh: Gh,
    owner: str,
    number: int,
    limit: int,
    *,
    include_completed: bool = False,
) -> dict[str, Any]:
    resolved_owner = current_login(gh) if owner == "@me" else owner
    metadata = project_metadata(gh, resolved_owner, number)
    fetched_items = project_items(gh, resolved_owner, number, limit)
    items, completed_hidden = filter_project_items(
        fetched_items, include_completed=include_completed
    )
    views = project_views(gh, str(metadata["id"]))
    return {
        "owner": resolved_owner,
        "project": metadata,
        "views": views,
        "items": items,
        "filter": {
            "includeCompleted": include_completed,
            "completedHidden": completed_hidden,
            "fetchedItems": len(fetched_items),
        },
    }


def command_show_project(args: argparse.Namespace, gh: Gh) -> None:
    data = board_payload(
        gh,
        args.owner,
        args.number,
        args.limit,
        include_completed=args.include_completed,
    )
    markdown = render_project_board(
        data["project"],
        data["items"],
        data["views"],
        completed_hidden=data["filter"]["completedHidden"],
    )
    emit(data, as_json=args.json, markdown=markdown)


def command_dashboard(args: argparse.Namespace, gh: Gh) -> None:
    owner = current_login(gh) if args.owner == "@me" else args.owner
    projects = project_list(gh, owner, args.project_limit)
    boards = [
        board_payload(
            gh,
            owner,
            int(project["number"]),
            args.item_limit,
            include_completed=args.include_completed,
        )
        for project in projects
    ]
    markdown = "\n\n".join(
        render_project_board(
            board["project"],
            board["items"],
            board["views"],
            completed_hidden=board["filter"]["completedHidden"],
        )
        for board in boards
    )
    if not boards:
        markdown = f"## GitHub Projects — {owner}\n\n_No projects found._"
    emit({"owner": owner, "boards": boards}, as_json=args.json, markdown=markdown)


def command_create_project(args: argparse.Namespace, gh: Gh) -> None:
    repo = repo_info(gh, args.repo)
    target_owner = args.target_owner or repo.owner
    title = args.title or f"{repo.name} Product & Development Board"
    description = args.description or f"Manage ideas, priorities, delivery, reviews, and outcomes for {repo.name_with_owner}."
    visibility = args.visibility or ("PRIVATE" if repo.is_private else "PUBLIC")
    areas = normalize_csv(args.areas)
    result = create_project(
        gh,
        repo=repo,
        target_owner=target_owner,
        title=title,
        description=description,
        visibility=visibility,
        areas=areas,
        template_owner=args.template_owner,
        template_number=args.template_number,
        reuse_existing=args.reuse_existing,
        dry_run=args.dry_run,
    )
    emit(result, as_json=args.json)


def command_create_issue(args: argparse.Namespace, gh: Gh) -> None:
    if args.body_file:
        body = args.body_file.read_text(encoding="utf-8")
    else:
        body = args.body
    result = create_issue(
        gh,
        repo=args.repo,
        title=args.title,
        body=body,
        labels=normalize_csv(args.labels),
        assignees=normalize_csv(args.assignees),
        project_owner=args.project_owner,
        project_number=args.project_number,
        field_values={
            "Status": args.status,
            "Priority": args.priority,
            "Focus": args.focus,
            "Area": args.area,
            "Size": args.size,
        },
        dry_run=args.dry_run,
    )
    emit(result, as_json=args.json)


def command_issue_inventory(args: argparse.Namespace, gh: Gh) -> None:
    issues = issue_inventory(gh, args.repo, args.limit)
    emit({"repository": args.repo, "issues": issues}, as_json=args.json, markdown=render_issues(issues, args.repo))


def command_set_item_fields(args: argparse.Namespace, gh: Gh) -> None:
    updated = set_project_item_fields(
        gh,
        owner=args.owner,
        project_number=args.project_number,
        item_id=args.item_id,
        values={
            "Status": args.status,
            "Priority": args.priority,
            "Focus": args.focus,
            "Area": args.area,
            "Size": args.size,
            "Outcome": args.outcome,
        },
    )
    emit({"updated": updated, "itemId": args.item_id}, as_json=args.json)


COMMANDS = {
    "preflight": command_preflight,
    "list-projects": command_list_projects,
    "show-project": command_show_project,
    "dashboard": command_dashboard,
    "create-project": command_create_project,
    "create-issue": command_create_issue,
    "issue-inventory": command_issue_inventory,
    "set-item-fields": command_set_item_fields,
}


def main(argv: Sequence[str] | None = None, *, gh: Gh | None = None) -> int:
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        client = gh or Gh()
        COMMANDS[args.command](args, client)
        return 0
    except (StewardError, OSError, UnicodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
