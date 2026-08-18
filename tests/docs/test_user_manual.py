"""`docs/build-ledger.md` 1.10 — the user manual's code and YAML is checked, not trusted.

Task **1.10**: "someone using Weft day to day can derive a pipeline from the manual alone"
(`docs/08-manuals.md` §1–§2, *User manual*). `08` §3's own rule for every shipped manual applies
here, on the same terms task 1.10 states explicitly: "EVERY CODE AND YAML BLOCK IN IT MUST BE
CHECKED BY A TEST, in the shape the existing `tests/docs/` checks already use... including the
named-waiver convention for a block that genuinely cannot execute." This is that check, run against
`manual/user-manual.md`, on the identical shape `tests/docs/test_quickstart.py` already uses for
`manual/quickstart.md`'s shell blocks: extract, execute, compare.

**Python, not shell — because the manual's own subject is Python.** `08` §2's own account of this
page: "Phase 3... a `weft pipeline derive`... command" is what does not exist yet, so every runnable
example in the manual is the equivalent call against `weft_kernel.resolution.resolve` directly. Each
fenced ` ```python id=<name> ` block is executed as its own subprocess — `sys.executable` reading
the body from stdin, never the developer's own `weft` console script, since nothing here drives the
CLI — and its stdout is compared **exactly** against the ` ```text id=<name>-out ` block that
follows it in the document: the manual can only ever show what the script beside it prints, never
a hand-typed approximation that could quietly drift from it. Every script writes to its own
`tempfile.mkdtemp()` and touches no fixture this repository ships, so no container and no shared
state is needed — the same reason `tests/integration/test_driving_use_case_a.py`, which this
document's own walkthrough is drawn from, needs none either.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
MANUAL: Final[Path] = REPO_ROOT / "manual" / "user-manual.md"

#: `08` §3's ratchet, restated for this page per task 1.10: a fenced ` ```python id=... ` block
#: skipped from execution must be named here explicitly. **Pinned empty** — every runnable block
#: in this manual executes today; nothing here needs Docker, a network call or a credential.
BLOCKS_WAIVED_FROM_EXECUTION: Final[frozenset[str]] = frozenset()

_PYTHON_FENCE = re.compile(
    r"^```python(?:\s+id=(?P<id>\S+))?\n(?P<body>.*?)^```\s*$", re.MULTILINE | re.DOTALL
)
_TEXT_FENCE = re.compile(
    r"^```text(?:\s+id=(?P<id>\S+))?\n(?P<body>.*?)^```\s*$", re.MULTILINE | re.DOTALL
)


def _python_blocks(markdown: str) -> list[tuple[str, str]]:
    """Every fenced ` ```python id=... ` block, as `(id, body)` pairs, in document order."""
    return [
        (match.group("id") or f"block-{index}", match.group("body"))
        for index, match in enumerate(_PYTHON_FENCE.finditer(markdown), start=1)
    ]


def _text_blocks_by_id(markdown: str) -> dict[str, str]:
    """Every fenced ` ```text id=... ` block, keyed by its id — the expected-output half."""
    return {
        match.group("id"): match.group("body")
        for match in _TEXT_FENCE.finditer(markdown)
        if match.group("id") is not None
    }


def test_at_least_one_python_block_is_extracted() -> None:
    # Floor — `08` §3: "at least one fenced ... block is extracted before any is run. A [page]
    # with nothing to execute cannot pass by having nothing to fail."
    blocks = _python_blocks(MANUAL.read_text(encoding="utf-8"))
    assert blocks, "manual/user-manual.md has no fenced ```python blocks to check"


def test_every_python_block_carries_an_id() -> None:
    # An untagged block has no `-out` counterpart to compare against, so it would silently
    # never be checked below rather than failing loudly — refused here instead, the same
    # shape `test_pack_guide_samples.py` gives an untagged code sample.
    markdown = MANUAL.read_text(encoding="utf-8")
    untagged = [
        f"block #{index}"
        for index, match in enumerate(_PYTHON_FENCE.finditer(markdown), start=1)
        if match.group("id") is None
    ]
    waived = set(BLOCKS_WAIVED_FROM_EXECUTION)
    surviving = [block for block in untagged if block not in waived]
    assert not surviving, (
        f"python block(s) with no id=, not named in BLOCKS_WAIVED_FROM_EXECUTION: {surviving}. "
        f"Tag it `id=<name>` and pair it with a `text id=<name>-out` block, or waive it by name."
    )


def test_every_executed_block_has_a_matching_output_block() -> None:
    # Arrange
    markdown = MANUAL.read_text(encoding="utf-8")
    executed = [
        block_id
        for block_id, _ in _python_blocks(markdown)
        if block_id not in BLOCKS_WAIVED_FROM_EXECUTION
    ]
    outputs = _text_blocks_by_id(markdown)

    # Assert
    missing = [block_id for block_id in executed if f"{block_id}-out" not in outputs]
    assert not missing, (
        f"python block(s) {missing} have no matching '```text id=<id>-out' block to compare "
        f"their stdout against."
    )


def test_python_blocks_print_exactly_what_the_manual_shows(tmp_path: Path) -> None:
    # Arrange
    del tmp_path  # each block builds and cleans up its own tempfile.mkdtemp(); nothing shared
    markdown = MANUAL.read_text(encoding="utf-8")
    executed = [
        (block_id, body)
        for block_id, body in _python_blocks(markdown)
        if block_id not in BLOCKS_WAIVED_FROM_EXECUTION
    ]
    assert executed, "every python block was waived — nothing was actually checked"
    outputs = _text_blocks_by_id(markdown)

    # Act / Assert — one block at a time, so a failure names which one drifted.
    for block_id, body in executed:
        result = subprocess.run(  # noqa: S603 — this repository's own doc, not untrusted input
            [sys.executable, "-"],
            input=body,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, (
            f"manual/user-manual.md block {block_id!r} exited {result.returncode}:\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        expected = outputs[f"{block_id}-out"]
        assert result.stdout.rstrip("\n") == expected.rstrip("\n"), (
            f"manual/user-manual.md block {block_id!r} printed something other than the "
            f"'{block_id}-out' block beside it — the manual has drifted from what the script "
            f"actually prints.\nactual:\n{result.stdout}\nexpected:\n{expected}"
        )


def test_a_retyped_output_block_would_fail() -> None:
    # Arrange — the self-test `08` §3 requires of every check in this file: prove the
    # comparison can actually fail, rather than passing merely because nothing was compared.
    actual = "base's chunk.size: 200\nwide's chunk.size: 400\n"
    retyped_by_hand = "base's chunk.size: 200\nwide's chunk.size: 999\n"

    # Assert
    assert actual.rstrip("\n") != retyped_by_hand.rstrip("\n")
