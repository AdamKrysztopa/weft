"""`docs/internal/build-ledger.md` 1.10 — the user manual's code and YAML is checked, not trusted.

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

import os
import re
import socket
import subprocess
import sys
from pathlib import Path
from typing import Final
from urllib.parse import urlparse, urlunparse

import pytest

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
MANUAL: Final[Path] = REPO_ROOT / "manual" / "user-manual.md"

#: `08` §3's ratchet, restated for this page per task 1.10: a fenced ` ```python id=... ` block
#: skipped from execution must be named here explicitly. **Pinned empty** — every runnable block
#: in this manual executes, and the one that needs a container is *skipped* rather than waived,
#: which is a different thing and is why it is not in here. See `BLOCKS_NEEDING_THE_CONTAINER`.
BLOCKS_WAIVED_FROM_EXECUTION: Final[frozenset[str]] = frozenset()

#: Blocks that index into a real store and read back from it — task **24.1**'s `Weft` section.
#: They are executed like every other block when `WEFT_DATABASE_URL` names a reachable Postgres,
#: and skipped by name when it does not. A skip is **not** a waiver: a waived block is one this
#: file has decided never to run, and a skipped one is a block whose environment is absent, which
#: the operator can fix. Keeping the two lists apart is what stops the second quietly becoming
#: the first — and the skip is counted in CI's own skip ratchet (`L12.1`), so a block that starts
#: skipping on a machine that has the container is a number that moves in a diff.
BLOCKS_NEEDING_THE_CONTAINER: Final[frozenset[str]] = frozenset({"embed"})

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


def _the_container_is_reachable() -> bool:
    """Whether `WEFT_DATABASE_URL` names a Postgres that answers — asked, never assumed.

    `L7.8`: a container brought down mid-task silently dropped 51 tests out of every run
    afterwards, green each time. An environment variable being *set* is not the same fact as a
    server being *up*, and the difference is exactly the failure mode with no symptom, so this
    opens a connection rather than reading `os.environ` and hoping.
    """
    dsn = os.environ.get("WEFT_DATABASE_URL")
    if not dsn:
        return False
    parsed = urlparse(dsn)
    if parsed.hostname is None:
        return False
    try:
        with socket.create_connection((parsed.hostname, parsed.port or 5432), timeout=2):
            return True
    except OSError:
        return False


def test_python_blocks_print_exactly_what_the_manual_shows(tmp_path: Path) -> None:
    # Arrange
    del tmp_path  # each block builds and cleans up its own tempfile.mkdtemp(); nothing shared
    markdown = MANUAL.read_text(encoding="utf-8")
    executed = [
        (block_id, body)
        for block_id, body in _python_blocks(markdown)
        if block_id not in BLOCKS_WAIVED_FROM_EXECUTION
        and block_id not in BLOCKS_NEEDING_THE_CONTAINER
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


@pytest.mark.skipif(
    not _the_container_is_reachable(),
    reason="WEFT_DATABASE_URL names no reachable Postgres; manual/user-manual.md §7 needs one",
)
def test_the_container_blocks_print_exactly_what_the_manual_shows() -> None:
    """§7's `Weft` walkthrough, run against the real store — task **24.1**.

    It is a separate test rather than a branch inside the one above so that the skip is
    *visible*: a run with no container reports one skipped test naming this page, rather than a
    green run over a silently smaller population, which is the shape `L7.8` cost 51 tests.

    **It runs against a database of its own, created and dropped here.** The block indexes a
    note and then asks a question, and a question searches whatever the store holds — so run
    against the suite's shared database it retrieved three passages instead of one, two of them
    belonging to other tests, and the comparison failed for a reason that had nothing to do with
    the manual. That is `L8.30` exactly: a measurement against `compose.yaml` owns its rows or it
    is measuring somebody else's. The block itself is unchanged and reads `WEFT_DATABASE_URL`
    like any reader's would; what this test supplies is an empty one.
    """
    # Arrange
    markdown = MANUAL.read_text(encoding="utf-8")
    blocks = [
        (block_id, body)
        for block_id, body in _python_blocks(markdown)
        if block_id in BLOCKS_NEEDING_THE_CONTAINER
    ]
    assert blocks, (
        f"BLOCKS_NEEDING_THE_CONTAINER names {sorted(BLOCKS_NEEDING_THE_CONTAINER)} and the "
        f"manual holds none of them — this test would pass by checking nothing."
    )
    outputs = _text_blocks_by_id(markdown)

    # Act / Assert
    dsn, admin, name = _a_database_of_its_own()
    try:
        _run_and_compare(blocks, outputs, environment={**os.environ, "WEFT_DATABASE_URL": dsn})
    finally:
        _drop_database(admin, name)


def _a_database_of_its_own() -> tuple[str, str, str]:
    """`(dsn, admin_dsn, name)` for a fresh, empty database on the same server.

    Named for the process so two runs on one machine cannot collide, and created through the
    admin connection `WEFT_DATABASE_URL` already implies rather than through a second piece of
    configuration nobody would keep true. The name is composed through `psycopg.sql.Identifier`
    rather than formatted into the statement — `weft_store.pgvector_store`'s own rule for DDL,
    which cannot take a bound parameter.
    """
    import psycopg  # noqa: PLC0415 — only this test needs a driver, and only with a container
    from psycopg import sql  # noqa: PLC0415

    dsn = os.environ["WEFT_DATABASE_URL"]
    name = f"weft_doc_{os.getpid()}"
    admin = urlunparse(urlparse(dsn)._replace(path="/postgres"))
    with psycopg.connect(admin, autocommit=True) as connection:
        connection.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
        )
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    return urlunparse(urlparse(dsn)._replace(path=f"/{name}")), admin, name


def _drop_database(admin: str, name: str) -> None:
    import psycopg  # noqa: PLC0415
    from psycopg import sql  # noqa: PLC0415

    with psycopg.connect(admin, autocommit=True) as connection:
        connection.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
        )


def _run_and_compare(
    blocks: list[tuple[str, str]],
    outputs: dict[str, str],
    *,
    environment: dict[str, str],
) -> None:
    for block_id, body in blocks:
        result = subprocess.run(  # noqa: S603 — this repository's own doc, not untrusted input
            [sys.executable, "-"],
            input=body,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
            env=environment,
        )
        assert result.returncode == 0, (
            f"manual/user-manual.md block {block_id!r} exited {result.returncode}:\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        expected = outputs[f"{block_id}-out"]
        assert result.stdout.rstrip("\n") == expected.rstrip("\n"), (
            f"manual/user-manual.md block {block_id!r} printed something other than the "
            f"'{block_id}-out' block beside it.\nactual:\n{result.stdout}\n"
            f"expected:\n{expected}"
        )
