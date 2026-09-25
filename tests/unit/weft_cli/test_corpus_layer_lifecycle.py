"""Task 43.26: a unit test of a corpus build fails the way a store does.

Every unit test of a corpus-scoped layer ran against doubles that answer without suspending and
pinned `max_concurrent_summaries: 1`, so two summaries never interleaved (`L28.48`), and against a
store registered through a plain function, which `participants_for` cannot see, so no `IndexCommand`
reached its closing reconcile (`R43.47` slipped past `R43.38`'s and `R43.43`'s tests that way). The
join's reclaim counts were seeded by hand.

Here the store is `examples/weft-example-ingest`'s `InMemoryNodeStore` — the in-process store the
published kit holds to what pgvector and Qdrant owe (FF9(c)) — made to suspend at every call and
registered by its class, so each run opens its own handle over one catalogue, as a real store does.
The model suspends too, and the build runs at the shipped `max_concurrent_summaries`. Build, add,
join through `adrap`, then a run whose closing pass reclaims the tree the join withdrew: the count
it prints is what `adrap` replaced, read from the store, never typed.
"""

from __future__ import annotations

import asyncio
import importlib
import sys
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any, cast

import pytest

from tests.unit.weft_cli.corpus_build_doubles import (
    LAYER,
    CountingEmbedder,
    ScriptedModel,
    llm_section,
    make_ctx,
    suspending,
    write_corpus,
)
from weft_chunk import Chunker
from weft_chunk.fixed_size import FixedSizeChunker
from weft_cli import commands, render
from weft_cli.exit_codes import ExitCode
from weft_embed import Embedder
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_extract import Extractor
from weft_extract.text import TextExtractor
from weft_index import Expander, Revisable
from weft_index.adrap import AdrapJoiner
from weft_index.payload import RaptorFacts
from weft_index.prompts import SUMMARIZE_CLUSTER_NAME, SummarizeClusterPrompt
from weft_index.raptor import RaptorSummarizer
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import NodeId
from weft_kernel.registry import Registry
from weft_llm.contract import LLMProvider
from weft_prompts.contract import Prompt
from weft_store import NodeStore
from weft_store.contract import Filter, FilterOp, MetadataFilter

_EXAMPLE_SRC = Path(__file__).resolve().parents[3] / "examples/weft-example-ingest/src"
_SUMMARIES = Filter(op=FilterOp.EXISTS, field=f"ext.{RaptorFacts.__namespace__}.clusters_found")


@pytest.fixture
def opens(monkeypatch: pytest.MonkeyPatch) -> Callable[[object], object]:
    """A factory opening a fresh, suspending handle onto one shared example store per call."""
    monkeypatch.setattr(sys, "path", [str(_EXAMPLE_SRC), *sys.path])
    module = importlib.import_module("weft_example_ingest.store")
    first: Any = module.InMemoryNodeStore()
    return partial(suspending(module.InMemoryNodeStore), _catalogue=first._catalogue)


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    ScriptedModel.reset()
    (tmp_path / "pipelines").mkdir()
    (tmp_path / "pipelines" / f"{LAYER}.yaml").write_text(
        f"name: {LAYER}\n"
        "vars:\n  layer.scope: corpus\n  layer.incremental: join\n"
        "stages:\n"
        "  - {id: raptor, use: raptor, with: {cluster_size: 2, similarity_threshold: -1.0}}\n"
        "  - {id: join, use: adrap, with: {cluster_size: 50, similarity_threshold: -1.0}}\n"
    )
    return write_corpus(tmp_path)


def _registry(opens: Callable[[object], object]) -> Registry:
    registry = Registry()
    registry.add(Extractor, "text", TextExtractor, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", FixedSizeChunker, distribution="weft-chunk")
    registry.add(Embedder, "hash", CountingEmbedder, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", opens, distribution="weft-store")
    registry.add(Expander, "raptor", RaptorSummarizer, distribution="weft-index")
    registry.add(Prompt, SUMMARIZE_CLUSTER_NAME, SummarizeClusterPrompt, distribution="weft-index")
    registry.add(LLMProvider, "scripted", ScriptedModel, distribution="weft-llm")
    registry.add(Revisable, "adrap", AdrapJoiner, distribution="weft-index")
    return registry


async def _index(opens: Callable[[object], object], corpus: Path) -> render.Rendered:
    ctx = make_ctx()
    ctx.services.add(
        Dependencies,
        Dependencies(
            registry=_registry(opens),
            reports=tuple(
                PackReport(pack=p, distribution=f"weft-{p}", status=PackStatus.ACTIVE)
                for p in ("extract", "chunk", "embed", "store", "index", "llm")
            ),
            services=ServiceSelection(store="pgvector"),
            llm=llm_section("m1"),
        ),
    )
    outcome = await commands.IndexCommand().run(
        commands.IndexArgs.model_validate({"path": str(corpus), "layers": LAYER}), ctx
    )
    rendered = render.render_outcome(outcome)
    assert rendered.exit_code is ExitCode.SUCCESS, rendered.stderr
    return rendered


async def _summaries(handle: object) -> frozenset[NodeId]:
    reader = cast(MetadataFilter, handle)
    page = await reader.matching(_SUMMARIES)
    seen = {node.id for node in page.items}
    while page.next_cursor is not None:
        page = await reader.matching(_SUMMARIES, page.next_cursor)
        seen |= {node.id for node in page.items}
    return frozenset(seen)


async def _count(handle: object) -> int:
    return await cast(NodeStore, handle).count()


def _closing_pass_lines(rendered: render.Rendered) -> list[str]:
    return [
        line for line in (rendered.stdout or "").splitlines() if line.startswith("  pgvector (")
    ]


async def test_a_join_s_withdrawn_tree_is_reclaimed_by_the_next_closing_pass_as_counted(
    opens: Callable[[object], object], corpus: Path
) -> None:
    # Arrange — build, then add one document and join it.
    await _index(opens, corpus)
    before_join = await _summaries(opens(None))
    (corpus / "late.txt").write_text("a document that arrived after the tree was built.")
    joined = await _index(opens, corpus)
    after_join = await _summaries(opens(None))
    replaced = before_join - after_join
    stored = await _count(opens(None))

    # Act — a run with nothing new; its closing pass reclaims what the join withdrew.
    rendered = await _index(opens, corpus)

    # Assert
    assert f"layer '{LAYER}': joined 1 leaves, 0 unassigned" in (joined.stdout or "")
    assert replaced, "the join replaced no summary, so nothing below is exercised"
    assert _closing_pass_lines(rendered) == [
        f"  pgvector (weft-store): examined 0, removed 0, backfilled 0, reclaimed {len(replaced)}"
    ]
    assert await _count(opens(None)) == stored - len(replaced)
    assert await _summaries(opens(None)) == after_join


async def test_the_build_s_summaries_are_in_flight_together_at_the_shipped_concurrency(
    opens: Callable[[object], object], corpus: Path
) -> None:
    # Act
    await _index(opens, corpus)

    # Assert
    assert ScriptedModel.peak_in_flight > 1
    assert len(await _summaries(opens(None))) >= 4


async def test_a_suspending_store_yields_to_the_loop_at_every_call(
    opens: Callable[[object], object],
) -> None:
    # Arrange
    order: list[str] = []

    async def other() -> None:
        order.append("other")

    pending = asyncio.ensure_future(other())

    # Act
    await _count(opens(None))
    order.append("store")
    await pending

    # Assert
    assert order == ["other", "store"]
