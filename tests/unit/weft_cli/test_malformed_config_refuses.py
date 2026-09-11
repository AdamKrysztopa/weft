"""A malformed `weft.toml` section is a named refusal, never a traceback.

**Found by running the binary at ledger task 7.4**, from a directory outside this repository. One
mistyped key in `[llm.roles]` — `generate = { provider = "scripted", nonsense = 1 }` — printed a
full Python traceback ending in `pydantic_core._pydantic_core.ValidationError` and exited `1`.

`weft_cli.cli.main` already has a handler for exactly this, and **its own comment claims this
coverage**: it catches `WeftError` around `build_dependencies` and explains that it is there for
*"`weft.toml` is not valid TOML, `[packs] allow`/`[plugins]` is malformed"*. The gap is that
`llm_section_from_config`, `service_selection_from_config` and `permission_policy_from_config`
validate with pydantic and let `ValidationError` — which is not a `WeftError` — straight past it.
So the sections parsed by hand are covered, the sections parsed by a model are not, and the comment
reads as though all of them were.

**This is the most likely user error there is.** `weft.toml` is the one file every operator edits,
and `docs/03-cli.md` → *Output* is explicit that a failure names what is wrong and what to do. A
traceback names a pydantic documentation URL.

The refusal is `RESOLUTION_FAILED` (**4**), not `OPERATION_FAILED` (1): no command was chosen, the
surface a command would be chosen from could not be built, and 4 is what `main`'s existing handler
already returns for every sibling failure at that point.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Final

import pytest

#: One malformed table per config reader that validates with pydantic. Each is a plausible typo
#: rather than a contrived break — an unknown key is what a person actually produces.
_MALFORMED: Final[tuple[tuple[str, str], ...]] = (
    ('[llm.roles]\ngenerate = { provider = "scripted", nonsense = 1 }\n', "llm.roles"),
    ("[services]\nembed = 17\n", "services"),
    ('[permissions]\noverwrite = "maybe"\n', "permissions"),
)


def _run(cwd: Path) -> subprocess.CompletedProcess[str]:
    """`weft pipeline list` in `cwd`, as a person runs it.

    A subprocess, because the property is about what somebody *sees*: an in-process call would
    prove nothing about whether the exception escaped `main`'s own handler, which is the whole
    defect.
    """
    return subprocess.run(  # noqa: S603 - sys.executable, fixed argv, no shell, no user input
        [sys.executable, "-m", "weft_cli.cli", "pipeline", "list"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(("table", "section"), _MALFORMED)
def test_a_malformed_section_refuses_without_a_traceback(
    table: str, section: str, tmp_path: Path
) -> None:
    # Arrange
    (tmp_path / "weft.toml").write_text(table, encoding="utf-8")

    # Act
    result = _run(tmp_path)

    # Assert
    combined = result.stdout + result.stderr
    assert "Traceback (most recent call last)" not in combined, (
        f"a mistyped [{section}] table gives the operator a Python traceback:\n{combined[:600]}"
    )
    assert "pydantic" not in combined.lower(), (
        f"the refusal for a mistyped [{section}] table names pydantic rather than weft.toml"
    )
    assert result.returncode == 4, (
        f"a mistyped [{section}] table exited {result.returncode}; no command was chosen, so this "
        f"is a resolution failure (4) like every other failure at this point in `main`"
    )
    assert "weft.toml" in combined, (
        f"the refusal for a mistyped [{section}] table never names the file to edit"
    )


def test_a_well_formed_config_still_runs(tmp_path: Path) -> None:
    # The other direction. A refusal that fired on everything would pass every assertion above,
    # which is `docs/internal/lessons.md` L5.19 applied to a guard rather than to a sweep.
    (tmp_path / "weft.toml").write_text('[llm.roles]\ngenerate = { provider = "scripted" }\n')

    result = _run(tmp_path)

    assert result.returncode == 0, f"a valid weft.toml was refused:\n{result.stderr[:400]}"
