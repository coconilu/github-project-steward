from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins" / "github-project-steward" / "scripts" / "project_steward.py"
SPEC = importlib.util.spec_from_file_location("project_steward", SCRIPT)
assert SPEC and SPEC.loader
steward = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = steward
SPEC.loader.exec_module(steward)


class FakeGh:
    def __init__(self, projects=None):
        self.projects = projects or []
        self.calls = []

    def run(self, args, **kwargs):
        self.calls.append((list(args), kwargs))
        if args[:2] == ["project", "list"]:
            return {"projects": self.projects, "totalCount": len(self.projects)}
        raise AssertionError(f"unexpected gh call: {args}")


class ProjectStewardTests(unittest.TestCase):
    def test_markdown_table_escapes_pipes_and_newlines(self):
        table = steward.markdown_table(["A", "B"], [["x|y", "one\ntwo"]])
        self.assertIn("x\\|y", table)
        self.assertIn("one two", table)

    def test_normalize_csv_deduplicates_and_preserves_order(self):
        self.assertEqual(
            steward.normalize_csv("Core, Web,Core, Docs "),
            ["Core", "Web", "Docs"],
        )

    def test_items_sort_by_status_focus_priority_then_title(self):
        items = [
            {"title": "Later", "status": "Ready", "focus": "Later", "priority": "P0"},
            {"title": "Now", "status": "Ready", "focus": "Now", "priority": "P2"},
            {"title": "Active", "status": "In progress", "focus": "Now", "priority": "P3"},
        ]
        ordered = [item["title"] for item in sorted(items, key=steward.item_sort_key)]
        self.assertEqual(ordered, ["Active", "Now", "Later"])

    def test_project_readme_binds_the_repository(self):
        repo = steward.RepoInfo(
            name_with_owner="octo/example",
            owner="octo",
            name="example",
            url="https://github.com/octo/example",
            description="",
            is_private=False,
        )
        readme = steward.project_readme(repo)
        self.assertIn("octo/example", readme)
        self.assertIn("Inbox → Ready → In progress → In review → Done", readme)

    def test_create_project_dry_run_has_no_mutating_calls(self):
        gh = FakeGh()
        repo = steward.RepoInfo(
            name_with_owner="octo/example",
            owner="octo",
            name="example",
            url="https://github.com/octo/example",
            description="",
            is_private=False,
        )
        result = steward.create_project(
            gh,
            repo=repo,
            target_owner="octo",
            title="Example board",
            description="Example",
            visibility="PUBLIC",
            areas=["Core", "Docs"],
            template_owner="source",
            template_number=7,
            reuse_existing=False,
            dry_run=True,
        )
        self.assertTrue(result["dryRun"])
        self.assertEqual(result["template"], {"owner": "source", "number": 7})
        self.assertEqual(len(gh.calls), 1)
        self.assertEqual(gh.calls[0][0][:2], ["project", "list"])

    def test_duplicate_project_requires_explicit_reuse(self):
        gh = FakeGh(projects=[{"number": 2, "title": "Example board", "url": "https://example.test/2"}])
        repo = steward.RepoInfo("octo/example", "octo", "example", "https://github.com/octo/example", "", False)
        with self.assertRaises(steward.StewardError):
            steward.create_project(
                gh,
                repo=repo,
                target_owner="octo",
                title="Example board",
                description="Example",
                visibility="PUBLIC",
                areas=["Core"],
                template_owner="source",
                template_number=7,
                reuse_existing=False,
                dry_run=True,
            )

    def test_template_snapshot_contains_required_views_and_fields(self):
        template = steward.load_template()
        self.assertEqual(
            [view["name"] for view in template["views"]],
            ["Board", "backlog", "Completed", "Roadmap"],
        )
        for field in ["Status", "Priority", "Focus", "Size", "Area", "Outcome"]:
            self.assertIn(field, template["fields"])

    @patch.object(steward.time, "sleep")
    @patch.object(steward.subprocess, "run")
    def test_read_only_gh_commands_retry_transient_failures(self, run, sleep):
        run.side_effect = [
            CompletedProcess(["gh"], 1, "", "unknown owner type"),
            CompletedProcess(["gh"], 0, '{"projects": []}', ""),
        ]
        result = steward.Gh("gh").run(
            ["project", "list", "--owner", "octo", "--format", "json"],
            expect_json=True,
        )
        self.assertEqual(result, {"projects": []})
        self.assertEqual(run.call_count, 2)
        sleep.assert_called_once()

    @patch.object(steward.time, "sleep")
    @patch.object(steward.subprocess, "run")
    def test_mutating_gh_commands_are_never_retried(self, run, sleep):
        run.return_value = CompletedProcess(["gh"], 1, "", "EOF")
        with self.assertRaises(steward.StewardError):
            steward.Gh("gh").run(["issue", "create", "--repo", "octo/example"])
        self.assertEqual(run.call_count, 1)
        sleep.assert_not_called()

    @patch.dict(os.environ, {"http_proxy": "http://127.0.0.1:6666"}, clear=False)
    @patch.object(steward.time, "sleep")
    @patch.object(steward.subprocess, "run")
    def test_read_only_command_falls_back_around_failed_loopback_proxy(self, run, sleep):
        run.side_effect = [
            CompletedProcess(["gh"], 1, "", "EOF"),
            CompletedProcess(["gh"], 1, "", "EOF"),
            CompletedProcess(["gh"], 0, '{"projects": []}', ""),
        ]
        result = steward.Gh("gh").run(
            ["project", "list", "--owner", "octo", "--format", "json"],
            expect_json=True,
        )
        self.assertEqual(result, {"projects": []})
        self.assertEqual(run.call_count, 3)
        fallback_env = run.call_args_list[-1].kwargs["env"]
        self.assertFalse(any(key.casefold() in {"http_proxy", "https_proxy", "all_proxy"} for key in fallback_env))

    @patch.dict(os.environ, {"http_proxy": "http://127.0.0.1:6666"}, clear=False)
    @patch.object(steward.subprocess, "run")
    def test_auth_status_rechecks_directly_after_proxy_false_negative(self, run):
        run.side_effect = [
            CompletedProcess(["gh"], 1, "", "The token in keyring is invalid."),
            CompletedProcess(["gh"], 0, "authenticated", ""),
        ]
        result = steward.Gh("gh").run(["auth", "status"])
        self.assertEqual(result, "authenticated")
        self.assertEqual(run.call_count, 2)
        self.assertIn("env", run.call_args_list[-1].kwargs)


if __name__ == "__main__":
    unittest.main()
