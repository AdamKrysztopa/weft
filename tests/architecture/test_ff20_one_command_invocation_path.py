"""Fitness function 20 — a `Command` is run from exactly one place.

Ledger task **7.0**, `docs/internal/lessons.md` `L8.31`, and `docs/internal/05-grilling-sessions.md`
→ G12. The permission gate G12 settled was called from exactly one place — inside
`weft_cli.cli.run_command` — and that function returns a `Rendered`. The typed result a library
caller needs comes from `Command.run`, which nothing gated. `weft_cli.confirm`'s own docstring calls
itself *"the invocation seam"* and argues, correctly for a single caller, that the check belongs
there. Phase 7's pack is the first second caller, and it would silently have got no gate at all.

**The general form is what this check enforces.** Placing a cross-cutting concern at *"the one place
that calls X"* is a bet that there will never be a second caller, and the bet's expiry date is
written down nowhere — `CLAUDE.md`'s own rule is that such concerns live at the registration seam,
never in a rule a caller must remember. Task 7.0 moved the gate into
`weft_command.invocation.invoke`, where consent is a **required** argument. That repair is only
durable if nothing later grows a second path, and a second path is exactly what a green suite would
not notice: the new caller would work, and it would simply not be gated.

**The property is checked structurally, at the seam rather than at the callers.** Every command run
in this tree goes through `weft_kernel.seam.wrap(..., contract="Command", ...)` — that is what
attaches the span, the error attribution and the transient strip. So *"how many places run a
command"* is *"how many `wrap` calls declare the `Command` contract"*, and the answer must be one.
Asking it this way rather than by hunting `.run(` call sites is deliberate: `.run` is an ordinary
method name that dozens of unrelated objects have, and a textual sweep for it would be noise with a
waiver list growing under it (`docs/internal/lessons.md` `L8.25`).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

#: The module that may run a command. **One entry, and it is the seam itself.** A second entry here
#: is a second invocation path, which is the defect this function exists to refuse — so an addition
#: is a `docs/internal/05-grilling-sessions.md` conversation, not an edit.
INVOCATION_SITES: Final[frozenset[str]] = frozenset({"weft_command/invocation.py"})


def _source_files() -> list[Path]:
    return sorted(
        path
        for pattern in ("packages/*/src/**/*.py", "testing/*/src/**/*.py")
        for path in REPO_ROOT.glob(pattern)
    )


def _declares_the_command_contract(call: ast.Call) -> bool:
    """Whether this `wrap(...)` call says it is sealing a `Command`."""
    return any(
        keyword.arg == "contract"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value == "Command"
        for keyword in call.keywords
    )


def command_invocation_sites() -> dict[str, int]:
    """Every shipped module that seals a `Command`, and how many times."""
    found: dict[str, int] = {}
    for path in _source_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover — a file that will not parse is the gate's problem
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            callee = node.func
            name = callee.attr if isinstance(callee, ast.Attribute) else getattr(callee, "id", None)
            if name == "wrap" and _declares_the_command_contract(node):
                relative = str(path.relative_to(REPO_ROOT)).split("src/", 1)[-1]
                found[relative] = found.get(relative, 0) + 1
    return found


def test_the_sweep_reads_the_shipped_tree() -> None:
    # The floor. A sweep matching nothing passes identically to one finding nothing wrong
    # (`docs/internal/lessons.md` L5.19), and this one's subject is a glob over paths that could
    # move.
    files = _source_files()
    assert len(files) > 100, (
        f"only {len(files)} source files found — the glob is not reading the tree"
    )


def test_exactly_one_module_runs_a_command() -> None:
    # Arrange / Act
    sites = command_invocation_sites()

    # Assert
    assert set(sites) == INVOCATION_SITES, (
        f"these modules seal a `Command` through the kernel seam: {sorted(sites)}, and exactly "
        f"{sorted(INVOCATION_SITES)} may. A second invocation path is not a failing test — it is a "
        f"caller that quietly gets no permission gate, which is what task 7.0 repaired and what "
        f"`weft_cli.confirm` documented as impossible while it was already true (lessons.md L8.31)."
    )


def test_the_one_site_seals_a_command_once() -> None:
    # Two `wrap` calls inside the seam would mean two paths through it, which the single-module
    # assertion above cannot see.
    sites = command_invocation_sites()
    assert sites == {"weft_command/invocation.py": 1}, f"the seam seals more than once: {sites}"


def test_the_check_can_actually_fail() -> None:
    """Plant a second invocation site and watch the detector find it.

    `docs/internal/lessons.md` `L5.6`: a check whose two sides come from one source cannot fail.
    Both the positive and the negative shape are planted here, because the discriminator is one
    keyword — a `wrap` call that does *not* declare `contract="Command"` seals a stage, not a
    command, and there are many of those.
    """
    a_command = ast.parse(
        'wrap(instance.run, distribution=d, contract="Command", plugin=n, stage=s)'
    ).body[0]
    a_stage = ast.parse('wrap(plugin.run, distribution=d, contract="Retriever", plugin=n)').body[0]
    assert isinstance(a_command, ast.Expr) and isinstance(a_command.value, ast.Call)
    assert isinstance(a_stage, ast.Expr) and isinstance(a_stage.value, ast.Call)

    assert _declares_the_command_contract(a_command.value)
    assert not _declares_the_command_contract(a_stage.value), (
        "every stage seal would be reported as a command invocation, so the check would fail "
        "constantly on correct code and be waived into uselessness"
    )
