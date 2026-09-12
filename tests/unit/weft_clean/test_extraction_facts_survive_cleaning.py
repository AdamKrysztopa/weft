"""Carried repair `R9.1`: a `TEXT` node's extraction-time `ext` facts survive every cleaner.

**The defect this file exists for, measured 2026-09-11 across nine real papers.** Every cleaner
in this pack rebuilds its node with `Node.derive`, which drops `ext` by design — "later stages
attach their own" — and none of them put back what extraction attached. So a page fact died at the
**first** cleaner (`ext = ['weft-kernel', 'weft-pdf']` → `ext = []` after `unicode-normalize`),
`weft_generate.page.page_for` answered `None`, and a citation lost its page number on every text
pipeline. `TABLE` and `IMAGE` nodes kept theirs only because task `9.8`'s `applies_to` routes them
past the cleaners entirely — they were not repaired, they were excused.

**G17, settled 2026-09-12, is what makes carrying safe rather than misleading.** Carrying `ext`
verbatim was refused until then, because the page was stored as a table of offsets into the
document's *extracted* text and a cleaner rewrites that text: carried across the rewrite, the fact
still resolved and named the wrong page on **72 of 1024 chunks**. Position 5 removed the
coordinate system — the page is now a scalar fact about the node — so there is nothing left for a
rewrite to invalidate and the verbatim carry is correct.

**The population is read from `register()`, not listed here.** A seventh cleaner added later is
covered by this file the day it is registered, which is the only way this property stays true of
the pack rather than of the six plugins somebody remembered.

**Two nodes, carrying different facts.** A one-node payload cannot tell *each node keeps its own
fact* from *every node gets the first node's fact*, and the second is what a wrong fix produces.
"""

from collections.abc import Sequence
from typing import cast

import pytest

from weft_clean import Settings, register
from weft_clean.contract import Cleaner
from weft_extract.payload import PageSpan
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import MediaType, Node, Produced, SourceId
from weft_kernel.registry import Registry


def _registered_cleaners() -> tuple[tuple[str, type[Cleaner]], ...]:
    """Every `Cleaner` this pack registers, as `register()` itself declares them."""
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-clean")
    register(registrar, Settings())
    registrar.commit()
    return tuple(
        (name, cast("type[Cleaner]", registry.entry(Cleaner, name).factory))
        for name in sorted(registry.names_for(Cleaner))
    )


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _page(number: int, text: str) -> Node:
    return Node.synthetic(
        content=text,
        media_type=MediaType.TEXT,
        reason=f"extracted from 'file:///paper.pdf' page {number} by stand-in",
        sources=frozenset({SourceId("paper")}),
        ordinal=number,
    ).with_ext(PageSpan(page=number, ordinal=0))


@pytest.mark.parametrize("name,factory", _registered_cleaners())
async def test_a_cleaner_carries_every_extraction_fact_onto_the_node_it_rebuilds(
    name: str, factory: type[Cleaner]
) -> None:
    # Arrange — two pages, each with its own page fact, so a cleaner that carried one
    # node's ext onto every output cannot pass.
    del name
    payload: Sequence[Node] = (
        _page(4, "a  page of   prose with a bro-\nken word"),
        _page(9, "another  page of   prose"),
    )

    # Act
    outcome = await factory().run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced), outcome
    assert [node.ext_as(PageSpan) for node in outcome.value] == [
        PageSpan(page=4, ordinal=0),
        PageSpan(page=9, ordinal=0),
    ]


@pytest.mark.parametrize("name,factory", _registered_cleaners())
async def test_a_cleaner_does_not_carry_forward_the_claim_that_a_node_has_no_lineage(
    name: str, factory: type[Cleaner]
) -> None:
    # Arrange — `SyntheticOrigin` is the one fact that must not travel: `derive` has just
    # given this node a real parent, so carrying it would attach a claim that is false.
    del name
    payload: Sequence[Node] = (_page(4, "a page of prose"),)

    # Act
    outcome = await factory().run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced), outcome
    [cleaned] = outcome.value
    assert "weft-kernel" not in cleaned.ext
    assert cleaned.lineage.parents == (payload[0].id,)
