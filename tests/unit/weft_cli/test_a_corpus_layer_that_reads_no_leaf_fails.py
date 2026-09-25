"""Carried repair R43.51: a corpus layer build that reads no leaf from its sources fails by name.

Over a store whose `in lineage.sources` answered nothing (`R43.50`), `weft index --layers` on
eight indexed documents published a generation holding no summary at exit 0 and printed nothing
about the layer. The build holds the sources it asked for, so zero leaves from them is a store
that could not answer the filter, never an empty corpus. On a rebuild, the empty generation
replaced a whole tree.
"""

from pathlib import Path

import pytest

from tests.unit.weft_cli.corpus_build_doubles import (
    LAYER,
    LEAVES,
    GenerationStore,
    ScriptedModel,
    index,
    published,
    write_corpus,
    write_layer,
)
from weft_kernel.payload import Node
from weft_store.contract import Cursor, Filter, FilterOp, Page


class _BlindToSources(GenerationStore):
    """Answers every filter naming `lineage.sources` with nothing, as R43.50's store did."""

    async def matching(self, filter: Filter, cursor: Cursor | None = None) -> Page[Node]:
        if _names_sources(filter):
            return Page(items=())
        return await super().matching(filter, cursor)


def _names_sources(filter: Filter) -> bool:
    if filter.field == "lineage.sources":
        return True
    return any(_names_sources(clause) for clause in filter.clauses)


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    ScriptedModel.reset()
    write_layer(tmp_path)
    return write_corpus(tmp_path)


async def test_a_build_that_reads_no_leaf_fails_on_every_source_and_publishes_nothing(
    corpus: Path,
) -> None:
    # Arrange
    store = _BlindToSources()

    # Act
    result = await index(store, corpus)

    # Assert
    assert [(f.layer, f.failed, f.of) for f in result.layers_failed] == [(LAYER, LEAVES, LEAVES)]
    (failure,) = result.layers_failed
    assert f"read no leaf from {LEAVES} sources" in failure.reason
    assert published(store) == []
    assert ScriptedModel.calls == []


async def test_a_rebuild_that_reads_no_leaf_keeps_the_tree_it_would_have_replaced(
    corpus: Path,
) -> None:
    # Arrange — a whole tree, then a re-parse that stales it, then a store gone blind.
    store = GenerationStore()
    await index(store, corpus)
    (live,) = published(store)
    (corpus / "doc0.txt").write_text("document number 0 now says something else.")
    blind = _BlindToSources(store.state)

    # Act
    result = await index(blind, corpus)

    # Assert
    assert [f.layer for f in result.layers_failed] == [LAYER]
    assert published(store) == [live]


def test_a_filter_naming_sources_is_recognised_inside_a_conjunction() -> None:
    nested = Filter(
        op=FilterOp.AND,
        clauses=(
            Filter(op=FilterOp.EXISTS, field="ext.weft-index.technique"),
            Filter(op=FilterOp.IN, field="lineage.sources", value=("a",)),
        ),
    )

    assert _names_sources(nested)
    assert not _names_sources(Filter(op=FilterOp.EXISTS, field="ext.weft-index.technique"))
