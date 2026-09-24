# Agent instructions

Quality requirements in this repository are executable. `CLAUDE.md` holds the project's rules and
reasoning; this file only points at the commands that enforce them.

- While iterating: `uv run poe ci-task` (format, lint, types, cognitive complexity, impacted tests).
- Before calling work done: `uv run poe ci-checks`, the canonical gate CI runs. It needs the
  container from `compose.yaml` (`docker compose up -d`) and `WEFT_DATABASE_URL`.
- A task is not complete while any check in that gate fails.
- Fix a violation in the code. Never make a gate pass by weakening it: no new `noqa`,
  `type: ignore` or `pyright: ignore`, no ruff ignores or exclusions, no raised thresholds, no
  lower pyright strictness, no skipped tests, no step removed from a `poe` task or from CI.
- If a check looks genuinely wrong, say so and ask; do not edit it in place.
