"""`weft index` reports the payload indexes the store ensured — ledger task **31.14**.

**Why this task exists at all.** `31.13`'s Exit asks that `weft index` over a real corpus "reports
its payload index", and on 2026-09-16 that clause was found **unsatisfiable**: nothing in the binary
reports one. `weft_qdrant.store._reconcile_payload_indexes` creates every declared index silently,
`IndexCommandResult` carries no such field, and a search for `payload_indexes` outside the store
finds only `weft_qdrant/settings.py` and tests. So `31.1`'s guarantee — that every filter Weft
issues is served by an index created *before the first point is written* — was true and invisible.

**The shape, settled by the owner.** The count is read off the built store instance as a
**declared-never-required** attribute through the registry's public factory, exactly as `31.8`
reads index kind and precision: no `NodeStore` Protocol member and no `STORE_CONTRACT_VERSION`
move, so a third-party store declaring nothing renders as a stated absence rather than being
refused over a reporting question.

That is why the default here is silence rather than "none". A store that declares nothing has not
said it ensured zero indexes; it has said nothing, and printing `payload indexes: none` for
pgvector — which ensures none and never claimed otherwise — would be inventing an answer the store
never gave. The distinction is the same one `IndexResult.stored_count` already draws with `None`.
"""

from weft_cli import render
from weft_cli.commands import IndexCommandResult
from weft_cli.exit_codes import ExitCode
from weft_kernel.payload import Produced
from weft_kernel.runner import RunSummary


def _summary() -> RunSummary:
    return RunSummary(produced=1, nothing_to_produce=0, failed=0)


def test_a_store_that_ensured_payload_indexes_names_them() -> None:
    # Arrange — what a Qdrant run looks like: `lineage.sources` is the one key Weft itself filters
    # on, and `31.1` has it created before the first point. The operator has never been able to see
    # that from the binary.
    result = IndexCommandResult(
        summary=_summary(),
        stored_count=2,
        documents_discovered=1,
        documents_indexed=1,
        payload_indexes=("lineage.sources",),
    )

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert — the count line is untouched and the indexes are named beside it.
    # `Rendered.stdout` is `str | None`, so the emptiness is made explicit rather than asserted
    # through an `in` that would be unsound when nothing was rendered at all.
    stdout = rendered.stdout or ""
    assert "nodes now stored: 2." in stdout
    assert "lineage.sources" in stdout
    assert rendered.exit_code is ExitCode.SUCCESS


def test_every_ensured_index_is_named_not_just_counted() -> None:
    # A number would satisfy "reports its payload index" while telling an operator nothing they
    # could check against `[packs.qdrant] payload_indexes`. Names are the checkable form.
    result = IndexCommandResult(
        summary=_summary(),
        stored_count=2,
        documents_discovered=1,
        documents_indexed=1,
        payload_indexes=("lineage.sources", "ext.weft-pdf.page"),
    )

    rendered = render.render_outcome(Produced(value=result))

    stdout = rendered.stdout or ""
    assert "lineage.sources" in stdout
    assert "ext.weft-pdf.page" in stdout


def test_a_store_that_declared_nothing_says_nothing() -> None:
    # The declared-never-required half, and a guard rather than a claim about today: pgvector
    # ensures no payload indexes and declares no such attribute, so the happy-path line must stay
    # byte-identical. A store's silence is not the same as a store reporting zero.
    result = IndexCommandResult(
        summary=_summary(), stored_count=2, documents_discovered=2, documents_indexed=1
    )

    rendered = render.render_outcome(Produced(value=result))

    assert rendered.stdout == "2 documents: 1 indexed, 1 unchanged. nodes now stored: 2."
    assert rendered.stderr is None
