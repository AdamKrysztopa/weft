"""Task 43.32: `weft index <dir>` releases every source recorded under `<dir>` whose file is gone.

The walk compared only the files it found with their records (`weft_cli/ingest.py`
`changes_against_records`, keyed `for doc in docs`), so a document deleted from disk kept its
source record and its nodes, and kept being retrieved. Settled by the owner at Phase 43e's opening
(Q3): such a source is released through `weft delete`'s own fan-out, so a corpus layer covering it
goes `STALE` as it does for `weft delete`, and the count reaches the command's output. Nothing is
released when the walk found no file at all, which is an unmounted or mistyped path, and a source
recorded under some other directory is never touched.
"""

from pathlib import Path

import pytest

from tests.unit.weft_cli.corpus_build_doubles import (
    LAYER,
    LEAVES,
    GenerationStore,
    ScriptedModel,
    llm_section,
    make_ctx,
    registry_for,
    write_corpus,
    write_layer,
)
from weft_cli import commands, render
from weft_cli.exit_codes import ExitCode
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_kernel.discovery import PackReport, PackStatus
from weft_store.contract import LayerStatus


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    ScriptedModel.reset()
    write_layer(tmp_path)
    return write_corpus(tmp_path)


async def _index(store: GenerationStore, path: Path, **flags: object) -> render.Rendered:
    deps = Dependencies(
        registry=registry_for(store),
        reports=tuple(
            PackReport(pack=p, distribution=f"weft-{p}", status=PackStatus.ACTIVE)
            for p in ("extract", "chunk", "embed", "store", "index", "llm")
        ),
        services=ServiceSelection(store="pgvector"),
        llm=llm_section("m1"),
    )
    ctx = make_ctx()
    ctx.services.add(Dependencies, deps)
    outcome = await commands.IndexCommand().run(
        commands.IndexArgs.model_validate({"path": str(path), **flags}), ctx
    )
    rendered = render.render_outcome(outcome)
    assert rendered.exit_code is ExitCode.SUCCESS, rendered.stderr
    return rendered


def _gone_id(corpus: Path, name: str) -> str:
    return str((corpus / name).resolve())


async def test_a_file_deleted_from_disk_releases_its_source_and_its_nodes(corpus: Path) -> None:
    # Arrange
    store = GenerationStore()
    await _index(store, corpus, layers="none")
    gone = _gone_id(corpus, "doc3.txt")
    (corpus / "doc3.txt").unlink()

    # Act
    rendered = await _index(store, corpus, layers="none")

    # Assert
    assert gone not in {str(record) for record in store.state.records}
    assert not any(gone in {str(s) for s in n.lineage.sources} for n in store.state.nodes.values())
    assert len(store.state.records) == LEAVES - 1
    assert "released 1 source no longer on disk." in (rendered.stdout or "")


async def test_releasing_a_gone_file_marks_a_corpus_layer_stale_on_the_rest(corpus: Path) -> None:
    # Arrange
    store = GenerationStore()
    await _index(store, corpus, layers=LAYER)
    (corpus / "doc3.txt").unlink()

    # Act
    await _index(store, corpus, layers="none")

    # Assert
    statuses = {
        entry.status
        for record in store.state.records.values()
        for entry in record.layers
        if entry.name == LAYER
    }
    assert statuses == {LayerStatus.STALE}


async def test_a_walk_that_finds_no_file_releases_nothing(corpus: Path) -> None:
    # Arrange
    store = GenerationStore()
    await _index(store, corpus, layers="none")
    for document in corpus.iterdir():
        document.unlink()

    # Act
    rendered = await _index(store, corpus, layers="none")

    # Assert
    assert len(store.state.records) == LEAVES
    assert "no longer on disk" not in (rendered.stdout or "")


async def test_a_source_recorded_under_another_directory_is_never_released(
    corpus: Path, tmp_path: Path
) -> None:
    # Arrange
    other = tmp_path / "other"
    other.mkdir()
    (other / "elsewhere.txt").write_text("a document indexed from another directory.")
    store = GenerationStore()
    await _index(store, corpus, layers="none")
    await _index(store, other, layers="none")

    # Act
    rendered = await _index(store, corpus, layers="none")

    # Assert
    assert _gone_id(other, "elsewhere.txt") in {str(record) for record in store.state.records}
    assert "no longer on disk" not in (rendered.stdout or "")
