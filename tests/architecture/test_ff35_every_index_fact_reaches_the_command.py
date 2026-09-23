"""Fitness function 35 — every `IndexResult` field reaches `IndexCommandResult` (`L28.40`).

`weft_cli.ingest.run_index` returns an `IndexResult`, and `IndexCommand.run` builds the
`IndexCommandResult` a renderer reads field by field. A field that call does not copy is reported
to nobody. `43.8` put `layers_changed` on `IndexResult`, tested it there, and no operator ever saw
a moved layer; `43.15` added the failure path beside it, and Exit C's corpus `raptor` then refused
on thirty sources while `weft index` exited 0 saying nothing (`R43.9`).

The walk reads every `IndexResult` dataclass field and every attribute the one
`IndexCommandResult(...)` call inside `IndexCommand.run` reads off any name: 19 fields when this
was written, three waived. At `61ac61a` it failed on `layers_changed`.
"""

from __future__ import annotations

import ast
import dataclasses
from typing import Final

from weft_cli.ingest import IndexResult

from .conftest import REPO_ROOT

_COMMANDS: Final = REPO_ROOT / "packages" / "weft-rag" / "src" / "weft_cli" / "commands.py"

#: Fields `IndexCommand.run` reads for something other than the operator's output.
NOT_REPORTED: Final[dict[str, str]] = {
    "resolved_pipeline": "persisted in the index run record, not rendered",
    "content_hashes": "the run record's corpus identity, not rendered",
    "pipeline_identity": "stored on each source record by `run_index`; no command reads it",
}


def copied_fields(source: str) -> frozenset[str]:
    """Every `<name>.<attribute>` read inside the `IndexCommandResult(...)` call in `run`."""
    run = next(
        member
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ClassDef) and node.name == "IndexCommand"
        for member in node.body
        if isinstance(member, ast.AsyncFunctionDef) and member.name == "run"
    )
    calls = [
        node
        for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "IndexCommandResult"
    ]
    assert len(calls) == 1, (
        f"expected one IndexCommandResult(...) in IndexCommand.run, found {len(calls)}"
    )
    return frozenset(
        node.attr
        for node in ast.walk(calls[0])
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
    )


def unreported(fields: list[str], copied: frozenset[str]) -> list[str]:
    return [name for name in fields if name not in copied and name not in NOT_REPORTED]


def _index_result_fields() -> list[str]:
    return [field.name for field in dataclasses.fields(IndexResult)]


def test_every_index_result_field_reaches_the_command_result() -> None:
    # Act
    missing = unreported(_index_result_fields(), copied_fields(_COMMANDS.read_text("utf-8")))

    # Assert
    assert not missing, (
        f"IndexResult carries {missing}, and IndexCommand.run never copies them into "
        "IndexCommandResult, so no renderer can print them. Copy each one and render it, or add "
        "it to NOT_REPORTED saying who reads it instead."
    )


def test_every_waiver_is_still_a_field_nothing_copies() -> None:
    # Arrange
    fields = _index_result_fields()
    copied = copied_fields(_COMMANDS.read_text("utf-8"))

    # Act
    stale = sorted(name for name in NOT_REPORTED if name not in fields or name in copied)

    # Assert
    assert not stale, f"NOT_REPORTED names {stale}, which are gone or now copied: drop them."


def test_the_check_can_actually_fail() -> None:
    # Arrange
    planted = (
        "class IndexCommand:\n"
        "    async def run(self):\n"
        "        return IndexCommandResult(summary=result.summary)\n"
    )

    # Act
    missing = unreported(["summary", "layers_changed"], copied_fields(planted))

    # Assert
    assert missing == ["layers_changed"]
