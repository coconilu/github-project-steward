# Installation prompts

## Codex

Paste this into Codex:

```text
Install the public Codex plugin from https://github.com/coconilu/github-project-steward.

1. Verify `gh`, Python 3.11+, and `gh auth status`.
2. Add the marketplace with `codex plugin marketplace add coconilu/github-project-steward`.
3. Install `github-project-steward@github-project-steward`.
4. Verify it appears in `codex plugin list`.
5. Do not edit marketplace.json or config.toml by hand.
6. Tell me to start a new Codex task after installation.
```

## Manual PowerShell

```powershell
gh auth status
python --version
codex plugin marketplace add coconilu/github-project-steward
codex plugin add github-project-steward@github-project-steward
codex plugin list
```

If GitHub Projects access is missing:

```powershell
gh auth refresh -s project -s repo
```

Start a new Codex task after installation.
