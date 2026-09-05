"""Unit tests for `weft_clean.table_linearizer`.

Mirrors `packages/weft-rag/src/weft_clean/table_linearizer.py`. Covers the
happy path (a wide-gap row becomes one cell per line), the edge case of a
short line being left alone even though it contains a wide gap (the
row-length guard), and the error case of a non-positive `gap_width`
refused by the config's own validator. Also covers task 1.7's own worked
example: `TableLinearizer` declares `intact = (WhitespaceGaps,)`, truthfully
— and task 2.35's addition, `destroys = (Verbatim,)`, per
`weft_clean.property`'s module docstring.

**`test_resolving_a_pipeline_naming_table_linearize_with_a_gap_width_actually_validates_it`
is a repair test.** A review found `TableLinearizer` shipping with no
`config_model`, so `weft_kernel.resolution.resolve` refused any `with:`
block naming `gap_width` — its one real knob — with `StageNotConfigurableError`,
claiming falsely that the stage "cannot be parameterised at all". The direct
`TableLinearizerConfig(...)` construction the tests above use never goes
through `resolve()`, so it could not have caught this.
"""

from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from weft_clean.contract import Cleaner
from weft_clean.property import Verbatim, WhitespaceGaps
from weft_clean.table_linearizer import TableLinearizer, TableLinearizerConfig
from weft_kernel import resolution
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Outcome, Produced
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _node(content: str) -> Node:
    return Node.synthetic(content=content, media_type=MediaType.TEXT, reason="test fixture")


async def test_run_splits_a_wide_gap_row_into_one_cell_per_line() -> None:
    # Arrange
    linearizer = TableLinearizer()
    parent = _node("Column One Header    Column Two Header    Column Three")

    # Act
    outcome: Outcome[Sequence[Node]] = await linearizer.run([parent], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value[0].content == "Column One Header\nColumn Two Header\nColumn Three"


async def test_run_leaves_a_short_wide_gap_line_alone() -> None:
    # Arrange — below `_MIN_ROW_LENGTH`, so even a wide gap is not read as a table row.
    linearizer = TableLinearizer()
    parent = _node("a    b")

    # Act
    outcome = await linearizer.run([parent], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value[0].content == "a    b"


async def test_run_answers_nothing_to_produce_for_an_empty_batch() -> None:
    # Arrange
    linearizer = TableLinearizer()

    # Act
    outcome = await linearizer.run([], _ctx())

    # Assert
    assert outcome == NothingToProduce(reason="no nodes to linearize")


def test_config_refuses_a_non_positive_gap_width() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        TableLinearizerConfig(gap_width=0)


def test_needs_whitespace_gaps_intact_and_destroys_verbatim() -> None:
    # Act / Assert — declared on the class, readable with no instance, per `02` §3.
    assert TableLinearizer.intact == (WhitespaceGaps,)
    assert TableLinearizer.destroys == (Verbatim,)


def test_resolving_a_pipeline_naming_table_linearize_with_a_gap_width_actually_validates_it() -> (
    None
):
    # Arrange — `02` §3's own `with:` shape, naming the one real knob this plugin has.
    registry = Registry()
    registry.add(Cleaner, "table-linearize", TableLinearizer, distribution="weft-clean")
    pipeline = Pipeline(
        name="cleaning",
        stages=(StageDeclaration(id="table", use="table-linearize", config={"gap_width": 5}),),
    )

    # Act
    resolved = resolution.resolve(pipeline, registry=registry, contracts={"table": Cleaner})

    # Assert — the block actually reached and validated against `TableLinearizerConfig`,
    # never silently dropped or refused as "not configurable".
    assert resolved.stages[0].config == TableLinearizerConfig(gap_width=5)
