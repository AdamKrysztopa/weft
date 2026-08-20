"""Regenerates the command table `manual/user-manual.md` embeds — task **3.9**.

`docs/08-manuals.md` §3 clause (b): "the manual's command table is the same generation step,
rendered to Markdown instead of a terminal, run in CI against a committed copy."
`tests/docs/test_generated_docs.py` is what "run in CI" means in practice — it calls the same
functions this script does and fails the build if the checked-in region has drifted. Run this
script by hand after a `Command`'s `help`, permission class or registration changes, and commit
the result:

    uv run python scripts/generate_command_table.py

Not wired into `poe ci-checks` itself — `tests/docs/test_generated_docs.py` already is (swept up
by the existing `test` step, the same reasoning `scripts/generate_contract_reference.py`'s own
docstring gives), and that test *checks* the committed file rather than *writing* it, so a CI run
never mutates the working tree. Only the region between `weft_cli.command_table.SECTION_BEGIN`
and `SECTION_END` is replaced — every hand-written word elsewhere in the manual is untouched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from weft_cli.command_table import command_entries, render_command_table, spliced_manual
from weft_cli.contract_reference import discover_for_reference

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
MANUAL: Final[Path] = REPO_ROOT / "manual" / "user-manual.md"


def main() -> None:
    registry = discover_for_reference()
    commands = command_entries(registry)
    table = render_command_table(commands)
    markdown = MANUAL.read_text(encoding="utf-8")
    MANUAL.write_text(spliced_manual(markdown, table), encoding="utf-8")
    names = ", ".join(sorted(command.name for command in commands))
    print(f"wrote {MANUAL} ({len(commands)} command(s): {names})")


if __name__ == "__main__":
    main()
