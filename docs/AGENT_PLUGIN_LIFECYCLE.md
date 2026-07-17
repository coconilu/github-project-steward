# Agent plugin lifecycle runbook

Use this document as the executable contract for a terminal-capable agent managing GitHub Project Steward.

| Setting | Value |
| --- | --- |
| Repository | `coconilu/github-project-steward` |
| Marketplace | `github-project-steward` |
| Plugin | `github-project-steward@github-project-steward` |

## Control rules

1. Execute only the lifecycle action explicitly requested by the user: **Install**, **Update**, or **Uninstall**. Never run all three in sequence.
2. Use `codex plugin` commands. Do not edit `marketplace.json`, `config.toml`, or cache directories by hand.
3. Prefer `--json` for verification. Do not claim success until the final state is verified.
4. Never expose authentication tokens. Return failed commands and sanitized errors.
5. Pause only when interactive authentication or new user authorization is required; give the user the exact next action.
6. After any successful lifecycle change, tell the user to start a new Codex task so plugin and skill state is reloaded.

## Install

Use this procedure only when the user asks to install the plugin.

1. Verify `codex --version`, `python --version` (Python 3.11+), and `gh --version`.
2. Run `gh auth status`. Confirm the active GitHub account can access the target repositories and has the `repo` and `project` scopes. If a scope is missing, run `gh auth refresh -s repo -s project`. Pause if this requires browser interaction.
3. Run `codex plugin marketplace list --json`.
   - If `github-project-steward` is absent, run `codex plugin marketplace add coconilu/github-project-steward --json`.
   - If it is already configured, run `codex plugin marketplace upgrade github-project-steward --json`; do not remove it first.
4. Run `codex plugin add github-project-steward@github-project-steward --json`.
5. Run `codex plugin list --json`. Verify that the plugin reports `installed: true` and `enabled: true`, and report its version.

## Update

Use this procedure only when the user asks to update the plugin.

1. Run `codex plugin marketplace list --json` and `codex plugin list --json`. Record the installed version.
2. If either the marketplace or plugin is absent, stop and report that the plugin is not installed; direct the user to the **Install** procedure instead of silently changing the requested action.
3. Run `codex plugin marketplace upgrade github-project-steward --json`.
4. Reinstall from the refreshed snapshot with `codex plugin add github-project-steward@github-project-steward --json`.
5. Run `codex plugin list --json`. Verify `installed: true` and `enabled: true`, then report the before and after versions. If they match, report that the installation was already current.

## Uninstall

Use this procedure only when the user asks to uninstall the plugin.

1. Run `codex plugin list --json` and `codex plugin marketplace list --json` to record the current state.
2. If the plugin is installed, run `codex plugin remove github-project-steward@github-project-steward --json`. If it is already absent, report that fact and continue verification.
3. Verify that `github-project-steward@github-project-steward` is absent from the installed plugin list.
4. The `github-project-steward` marketplace is dedicated to this repository. If no other installed plugin reports `marketplaceName: github-project-steward`, remove the source with `codex plugin marketplace remove github-project-steward --json`. If another plugin depends on it, keep the marketplace and report why.
5. Run both list commands again. Verify that the plugin is absent and, when removed in step 4, the marketplace is absent. Do not manually delete remaining cache directories.

## Final report

Return a compact result containing:

| Field | Required content |
| --- | --- |
| Action | Install, Update, or Uninstall |
| Result | Success, already current/absent, or failed |
| Version | Installed version, or before → after for updates |
| Verification | The final `codex plugin list --json` state |
| User action | Start a new Codex task, or the exact authentication step if blocked |
