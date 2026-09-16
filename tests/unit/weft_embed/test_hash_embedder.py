"""Unit tests for `weft_embed.hash_embedder`.

Mirrors `packages/weft-rag/src/weft_embed/hash_embedder.py`. Covers the
happy path (a batch of nodes each gets a deterministic, fixed-dimension
vector), the edge case of an empty batch (`NothingToProduce`, never an empty
`Produced([])`), and the error case of a non-positive configured dimension.

**`test_resolving_a_pipeline_naming_hash_with_a_dimension_actually_validates_it`
is a repair test — `R31.2`.** `HashEmbedder` shipped with no `config_model`, so
`weft_kernel.resolution.resolve` refused *any* `with: {dimension: N}` block with
`StageNotConfigurableError`, claiming falsely that the stage "cannot be
parameterised at all" — while `HashEmbedderConfig`, directly above it in the
module, is exactly the model task 1.5's mechanism was built to validate against.
The direct `HashEmbedderConfig(...)` construction every test above uses never
goes through `resolve()`, which is why none of them could catch it. This is the
third instance of one defect: `FixedSizeChunker` and `TableLinearizer` each
needed the identical one-line repair, and each kept a paragraph saying so.

It was found by running the binary, not by any test: `weft pipeline estimate
index-text` refuses because it cannot read a width, and the remedy its own error
message offers — name the dimension in that stage's `with:` block — exits 4.
`L22.26` had recorded the underlying fact at Phase 29's close; nobody filed the
repair, because until `weft pipeline estimate` shipped nothing needed the width
to be *readable*.
"""

from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from weft_embed.contract import Embedder
from weft_embed.hash_embedder import HashEmbedder, HashEmbedderConfig
from weft_kernel import resolution
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Outcome, Produced
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _node(content: str) -> Node:
    return Node.synthetic(content=content, media_type=MediaType.TEXT, reason="test fixture")


async def test_run_attaches_a_deterministic_fixed_dimension_vector_to_every_node() -> None:
    # Arrange
    embedder = HashEmbedder(config=HashEmbedderConfig(dimension=8))
    first = _node("hello world")
    second = _node("goodbye world")

    # Act
    outcome: Outcome[Sequence[Node]] = await embedder.run([first, second], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    embedded = outcome.value
    assert [node.embedding for node in embedded if node.embedding is not None]
    for node in embedded:
        assert node.embedding is not None
        assert node.embedding.dimension == 8
    # Same content, same vector — required for re-index idempotency to hold through storage.
    again = await embedder.run([_node("hello world")], _ctx())
    assert isinstance(again, Produced)
    assert again.value[0].embedding == embedded[0].embedding
    # Different content, different vector.
    assert embedded[0].embedding != embedded[1].embedding


async def test_run_answers_nothing_to_produce_for_an_empty_batch() -> None:
    # Arrange
    embedder = HashEmbedder()

    # Act
    outcome = await embedder.run([], _ctx())

    # Assert
    assert outcome == NothingToProduce(reason="no nodes to embed")


def test_config_refuses_a_non_positive_dimension() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        HashEmbedderConfig(dimension=0)


def test_the_plugin_declares_the_config_model_resolution_reads() -> None:
    # `resolve` reads this with `getattr(declared, "config_model", None)`; absent, every `with:`
    # block on a hash stage is refused as unconfigurable.
    assert HashEmbedder.config_model is HashEmbedderConfig


def test_resolving_a_pipeline_naming_hash_with_a_dimension_actually_validates_it() -> None:
    # Arrange — the width a document asks for, which `weft pipeline estimate` has to be able to
    # read back off the resolved stage.
    registry = Registry()
    registry.add(Embedder, "hash", HashEmbedder, distribution="weft-embed")
    pipeline = Pipeline(
        name="index",
        stages=(StageDeclaration(id="embed", use="hash", config={"dimension": 1536}),),
    )

    # Act
    resolved = resolution.resolve(pipeline, registry=registry, contracts={"embed": Embedder})

    # Assert — the block reached and validated against `HashEmbedderConfig`, never silently
    # dropped and never refused as "not configurable".
    assert resolved.stages[0].config == HashEmbedderConfig(dimension=1536)


def test_a_stage_naming_no_dimension_still_resolves_to_the_declared_default() -> None:
    # The case `weft pipeline estimate index-text` actually meets: no `with:` block at all, and a
    # width that is nonetheless knowable, because the model declares one.
    registry = Registry()
    registry.add(Embedder, "hash", HashEmbedder, distribution="weft-embed")
    pipeline = Pipeline(name="index", stages=(StageDeclaration(id="embed", use="hash"),))

    # Act
    resolved = resolution.resolve(pipeline, registry=registry, contracts={"embed": Embedder})

    # Assert
    assert resolved.stages[0].config == HashEmbedderConfig()
    assert getattr(resolved.stages[0].config, "dimension", None) == 64
