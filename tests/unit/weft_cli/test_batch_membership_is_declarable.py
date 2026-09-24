"""A stage can say its output depends on which nodes shared its call — ledger task **17.2**.

`weft_kernel.runner.Runner.run` walks its batches with a plain `async for` and puts each one
through the whole stage list independently. For almost every stage that is invisible: a chunker
splits each document the same way whoever else was in the call, an embedder embeds each node
alone. For a stage that **clusters**, it is the whole meaning of the operation.

`raptor` is that stage, and it is not a hypothetical. `01`:1012 records the measurement: *"the
shipped `raptor` does not cluster corpus-wide — it clusters **batch-wide**, over whatever one
`weft index` invocation was handed, which is neither paper's scope and was nobody's decision"*
(`L10.1`). G15 settled that it reads no store, so what it was handed is all it can see. Index ten
documents in one command and they share a tree; index them in two and the second founds a second
tree.

Today "batch" means "one `weft index` invocation", because `run_index` yields the whole corpus in
one go. Task `17.3` chunks that iterator, which silently redefines the word — and this task is the
fact `17.3`'s refusal is built on.

**Declared, not derived, and that is the exception rather than the rule.** `02` → *Capability is
derived, never declared* is this project's default and the reason nobody writes a flag: a computed
capability cannot be a false one. This property is not computable from a class's shape — whether
an output depends on batch membership is a fact only the author of the algorithm knows — so it
joins `requires`, `provides` and `lifetime`, which `weft_kernel.runner`'s own docstring calls
*"conventions a plugin may set, read defensively off the constructed instance"*.

**Silence means no, and that is a deliberate asymmetry with `destroys`.** A contract publishing a
property vocabulary *refuses* a plugin that states no `destroys`, because there the safe default
would hide a real conflict. Here the population is every stage ever written by anybody, almost all
of which are batch-invariant and none of which can be made to declare anything retroactively — so
an absent declaration reads as `False` and a pack that clusters has to say so. What the refusal in
`17.3` protects is the shipped ladder, where the one such stage is known by name.
"""

from collections.abc import Sequence

from weft_cli.ingest import batch_membership_dependent_stages
from weft_index import Expander
from weft_index.raptor import RaptorSummarizer
from weft_kernel.context import Context
from weft_kernel.payload import Node, Outcome, Produced
from weft_kernel.registry import Registry
from weft_kernel.runner import RunnablePipeline, Runner, StageSpec


class _Ordinary:
    """A stage that declares nothing — every third-party plugin in existence, and the control."""

    destroys: tuple[type, ...] = ()

    def __init__(self, config: object) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        return Produced(value=payload)


class _Clusters(_Ordinary):
    """A stranger's stage that does depend on batch membership, and says so."""

    depends_on_batch_membership = True


class _SaysNo(_Ordinary):
    """A stage that declares the property `False` explicitly.

    Its own test below is what separates *reading the value* from *checking the attribute is
    present* — two implementations that agree on every other input in this file.
    """

    depends_on_batch_membership = False


def _runnable(*stages: tuple[str, type[_Ordinary]]) -> RunnablePipeline:
    registry = Registry()
    specs: list[StageSpec] = []
    for name, plugin in stages:
        registry.add(Expander, name, plugin, distribution="acme-pack")
        specs.append(StageSpec(id=name, contract=Expander, name=name))
    return Runner(registry).resolve(tuple(specs), tenant_id="tenant-a")


def test_raptor_says_its_output_depends_on_who_else_was_in_the_call() -> None:
    """The fact this task exists to write down, asserted on the shipped plugin.

    Not on a double: the whole point is that *this* class, the one `index-with-raptor.yaml`
    places, carries the declaration. A double declaring it would prove only that the reader works.
    """
    assert RaptorSummarizer.depends_on_batch_membership is True


def test_a_pipeline_holding_such_a_stage_names_it() -> None:
    """The happy path, and it answers with the **plugin** name rather than the stage id.

    `17.3`'s refusal has to tell an operator which plugin cannot survive being split, and a stage
    id is whatever the document's author called the position — `expand`, `summarise`, `step-2`.
    The plugin name is the thing they can look up in `10`'s catalogue.
    """
    # Arrange
    runnable = _runnable(("plain", _Ordinary), ("clusterer", _Clusters))

    # Act / Assert
    assert batch_membership_dependent_stages(runnable) == ("clusterer",)


def test_a_pipeline_of_ordinary_stages_names_none() -> None:
    """The control. A reader that answered with every stage would satisfy the test above."""
    runnable = _runnable(("one", _Ordinary), ("two", _Ordinary))
    assert batch_membership_dependent_stages(runnable) == ()


def test_a_stage_that_declares_false_is_not_reported() -> None:
    """The edge case: the value is read, not the attribute's presence.

    `hasattr` and a truthiness read agree on every other case in this file, so without this the
    two are indistinguishable — and a plugin that says `False` on purpose would be refused by
    `17.3` for a property it explicitly disclaimed.
    """
    runnable = _runnable(("declines", _SaysNo))
    assert batch_membership_dependent_stages(runnable) == ()


def test_every_such_stage_is_named_in_pipeline_order() -> None:
    """Every stage that declares batch membership is named, in pipeline order.

    Two of them, because one entry cannot show ordering, separators or whether two entries are
    distinguishable at all — `docs/internal/lessons.md` `L12.6`, where six tests of an
    operator-facing message each held one row and the shipped binary printed seven identical ones.
    """
    runnable = _runnable(("first", _Clusters), ("middle", _Ordinary), ("last", _Clusters))
    assert batch_membership_dependent_stages(runnable) == ("first", "last")
