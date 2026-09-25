"""Task 43.30: a corpus layer `STALE` on any source is hidden from every read until republished.

Going `STALE` rewrote only the source records; the generation stayed `PUBLISHED`, so every read
still returned its summaries, and after `weft delete` a summary of the deleted document was still
quoted (Phase 43e's opening hand-run). Settled by the owner at the opening (Q2): hide the layer
until a rebuild or an adRAP join republishes it. Asserted where a reader sees it: a fresh handle's
summaries, over a re-parse and over a delete, on a store that withdraws and on one that cannot.
"""

from pathlib import Path

import pytest
from pydantic import BaseModel

from tests.unit.weft_cli.corpus_build_doubles import (
    LAYER,
    ClosingPassStore,
    GenerationStore,
    ScriptedModel,
    llm_section,
    make_ctx,
    registry_for,
    visible_summaries,
    write_corpus,
    write_layer,
)
from weft_cli import commands, render
from weft_cli.exit_codes import ExitCode
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_kernel.discovery import PackReport, PackStatus

_STORES = pytest.mark.parametrize(
    "store_class", [ClosingPassStore, GenerationStore], ids=["withdraws", "cannot-withdraw"]
)


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    ScriptedModel.reset()
    write_layer(tmp_path)
    return write_corpus(tmp_path)


def _deps(store: GenerationStore) -> Dependencies:
    return Dependencies(
        registry=registry_for(store),
        reports=tuple(
            PackReport(pack=p, distribution=f"weft-{p}", status=PackStatus.ACTIVE)
            for p in ("extract", "chunk", "embed", "store", "index", "llm")
        ),
        services=ServiceSelection(store="pgvector"),
        llm=llm_section("m1"),
    )


async def _run(
    store: GenerationStore,
    command: commands.IndexCommand | commands.DeleteCommand,
    args: BaseModel,
) -> render.Rendered:
    ctx = make_ctx()
    ctx.services.add(Dependencies, _deps(store))
    outcome = await command.run(args, ctx)
    rendered = render.render_outcome(outcome)
    assert rendered.exit_code is ExitCode.SUCCESS, rendered.stderr
    return rendered


async def _index(store: GenerationStore, corpus: Path, layers: str) -> render.Rendered:
    args = commands.IndexArgs.model_validate({"path": str(corpus), "layers": layers})
    return await _run(store, commands.IndexCommand(), args)


@_STORES
async def test_a_re_parse_hides_the_corpus_layer_until_it_is_rebuilt(
    corpus: Path, store_class: type[GenerationStore]
) -> None:
    # Arrange
    store = store_class()
    await _index(store, corpus, LAYER)
    assert visible_summaries(store)
    (corpus / "doc0.txt").write_text("document number 0 now says something else entirely.")

    # Act
    await _index(store, corpus, "none")
    hidden = visible_summaries(store)
    await _index(store, corpus, LAYER)

    # Assert
    assert hidden == []
    assert visible_summaries(store)


@_STORES
async def test_a_delete_hides_the_corpus_layer_so_no_summary_of_it_is_read(
    corpus: Path, store_class: type[GenerationStore]
) -> None:
    # Arrange
    store = store_class()
    await _index(store, corpus, LAYER)
    victim = str((corpus / "doc3.txt").resolve())

    # Act
    await _run(store, commands.DeleteCommand(), commands.DeleteArgs(source_id=victim))

    # Assert
    assert visible_summaries(store) == []
