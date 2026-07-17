# Repository instructions

- Keep `README.md` and `README.zh-CN.md` behaviorally synchronized.
- Keep the runtime dependency-free; prefer Python standard library and the authenticated GitHub CLI.
- Use `apply_patch` for edits. Do not rewrite user changes outside this repository.
- Run `python scripts/validate_repo.py` and `python -m unittest discover -s tests -v` before committing.
- Run the Codex plugin and skill validators when their local system paths are available.
- Keep all tests offline. Never create, edit, or delete live GitHub resources from unit tests or CI.
- Treat `plugins/github-project-steward/templates/default-project.json` and the public mother Project as one versioned contract. Verify both before changing the source owner or number.
- Preserve the two-agent boundary: only the developer writes; the reviewer remains read-only.
- Do not add automatic PR merge or Project deletion without an explicit product decision and safety review.
