#!/usr/bin/env python3
"""Dependency-free repository validation for CI."""

from __future__ import annotations

import json
import py_compile
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "github-project-steward"
MANIFEST = PLUGIN / ".codex-plugin" / "plugin.json"
MARKETPLACE = ROOT / ".agents" / "plugins" / "marketplace.json"
LIFECYCLE = ROOT / "docs" / "AGENT_PLUGIN_LIFECYCLE.md"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


def fail(message: str) -> None:
    raise AssertionError(message)


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid JSON at {path.relative_to(ROOT)}: {exc}")


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if "[TODO:" in text:
        fail(f"placeholder remains in {path.relative_to(ROOT)}")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        fail(f"missing YAML frontmatter in {path.relative_to(ROOT)}")
    try:
        end = lines.index("---", 1)
    except ValueError:
        fail(f"unterminated YAML frontmatter in {path.relative_to(ROOT)}")
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        if ":" not in line:
            fail(f"invalid frontmatter line in {path.relative_to(ROOT)}: {line}")
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip().strip('"')
    if set(fields) != {"name", "description"}:
        fail(f"frontmatter must contain only name and description in {path.relative_to(ROOT)}")
    return fields


def main() -> int:
    manifest = load_json(MANIFEST)
    marketplace = load_json(MARKETPLACE)
    if manifest["name"] != PLUGIN.name:
        fail("plugin folder and manifest name differ")
    if not SEMVER.fullmatch(manifest["version"]):
        fail("plugin version is not strict semver")
    if manifest.get("skills") != "./skills/":
        fail("plugin skills path must be ./skills/")
    entry = next((item for item in marketplace.get("plugins", []) if item.get("name") == manifest["name"]), None)
    if not entry:
        fail("marketplace entry is missing")
    if entry.get("source", {}).get("path") != "./plugins/github-project-steward":
        fail("marketplace source path is wrong")
    if set(entry.get("policy", {})) != {"installation", "authentication"}:
        fail("marketplace policy is incomplete")

    skill_count = 0
    for skill_file in sorted((PLUGIN / "skills").glob("*/SKILL.md")):
        skill_count += 1
        fields = parse_frontmatter(skill_file)
        if fields["name"] != skill_file.parent.name:
            fail(f"skill folder and name differ: {skill_file.relative_to(ROOT)}")
        agent_yaml = skill_file.parent / "agents" / "openai.yaml"
        if not agent_yaml.exists():
            fail(f"agents/openai.yaml is missing for {fields['name']}")
        agent_text = agent_yaml.read_text(encoding="utf-8")
        if f"${fields['name']}" not in agent_text:
            fail(f"default prompt does not name ${fields['name']}")
    if skill_count != 3:
        fail(f"expected 3 skills, found {skill_count}")

    template = load_json(PLUGIN / "templates" / "default-project.json")
    if [view["name"] for view in template["views"]] != ["Board", "backlog", "Completed", "Roadmap"]:
        fail("template view contract changed unexpectedly")

    lifecycle_text = LIFECYCLE.read_text(encoding="utf-8")
    required_lifecycle_content = [
        "## Install",
        "## Update",
        "## Uninstall",
        "codex plugin marketplace add coconilu/github-project-steward",
        "codex plugin marketplace upgrade github-project-steward",
        "codex plugin add github-project-steward@github-project-steward",
        "codex plugin remove github-project-steward@github-project-steward",
        "codex plugin marketplace remove github-project-steward",
    ]
    for required in required_lifecycle_content:
        if required not in lifecycle_text:
            fail(f"agent lifecycle document is missing: {required}")

    for readme_name in ["README.md", "README.zh-CN.md"]:
        readme_text = (ROOT / readme_name).read_text(encoding="utf-8")
        if "docs/AGENT_PLUGIN_LIFECYCLE.md" not in readme_text:
            fail(f"{readme_name} does not link the agent lifecycle document")

    py_compile.compile(str(PLUGIN / "scripts" / "project_steward.py"), doraise=True)
    print(f"OK: {manifest['name']} {manifest['version']} with {skill_count} skills")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
