"""`iterative-retrieve` fuses the rounds it searched — carried repair **R44.10**.

The iterative retriever returns one ranked list per round, and the document extended
`retrieve-then-generate` without replacing its `single-list` fuser, which refuses more than one
list. So the rung failed on exactly the questions it iterated on: 263 of E2's 600, leaving an
`answer_correctness` over the 334 easy ones that read as a win. The shipped document's own fuse
stage, resolved as `weft ask` resolves it, must fuse several lists.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from weft_cli.compile import to_specs
from weft_cli.pipeline_catalogue import full_catalogue
from weft_cli.route_ask import resolve_in_catalogue
from weft_engine import registry_bootstrap
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, Produced
from weft_retrieve import Fuser
from weft_retrieve.payload import Candidates, Channel, Passage, Query, RankedList
from weft_store.contract import Scored


def _list(asked: Query, round_: int) -> RankedList:
    node = Node.synthetic(content=f"round {round_}", media_type=MediaType.TEXT, reason="fixture")
    hit = Passage(scored=Scored(value=node, score=1.0), rank=0, retrieved_by="vector-top-k")
    return RankedList(
        query=asked, retriever="vector-top-k", channel=Channel.VECTOR.value, hits=(hit,)
    )


async def test_the_shipped_iterative_document_fuses_every_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "weft.toml"
    config.write_text("", encoding="utf-8")
    deps = registry_bootstrap.build_dependencies(config_path=config)
    catalogue = full_catalogue(reports=deps.reports)
    resolved = resolve_in_catalogue(
        catalogue["iterative-retrieve"],
        registry=deps.registry,
        catalogue=catalogue,
        reports=deps.reports,
        contributions=deps.contributions,
    )
    [fuse] = [
        spec
        for spec in to_specs(resolved, registry=deps.registry, reports=deps.reports)
        if spec.id == "fuse"
    ]
    fuser = cast("Fuser", deps.registry.entry(Fuser, fuse.name).factory(fuse.config))
    asked = Query(text="which composer taught the teacher of the author of the opera?")
    rounds = Candidates(origin=asked, lists=tuple(_list(asked, round_) for round_ in range(3)))

    # Act
    outcome = await fuser.run(rounds, Context(tenant_id="t", run_id="r", trace_id="x", locale="en"))

    # Assert
    assert isinstance(outcome, Produced)
    assert {passage.scored.value.content for passage in outcome.value.hits} == {
        "round 0",
        "round 1",
        "round 2",
    }
