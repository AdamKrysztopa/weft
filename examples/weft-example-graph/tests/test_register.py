"""One `register()`, one settings model, six contracts (task 5.4), plus a shipped pipeline and
a slot contribution (task 5.5) — proven structurally against a real `weft_kernel.registry.
Registry` rather than by reading the source and trusting it.
"""

import pytest
import weft_example_graph
from weft_example_graph.commands import GraphShowResult
from weft_example_graph.payload import GraphData
from weft_example_graph.store import GraphStore

from weft_command.contract import Command, Rendered
from weft_enhance.contract import Enhancer
from weft_kernel.discovery import PackRegistrar
from weft_kernel.registry import DuplicateRegistrationError, Registry, unwrap_factory
from weft_retrieve.contract import Retriever
from weft_store.contract import NodeStore, Reconcilable, SourceDeletable


def test_settings_construct_with_zero_arguments() -> None:
    # `tests/architecture/test_ff9_extension_from_outside.py` constructs every example
    # pack's `Settings()` bare, in-process, with no `weft.toml` and no environment — this
    # is that same requirement, checked here rather than only discovered there.
    weft_example_graph.Settings()


def test_register_contributes_five_plugins_across_four_contracts() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-example-graph")

    # Act
    weft_example_graph.register(registrar, weft_example_graph.Settings())
    registrar.commit()

    # Assert — four contracts named directly by an `.add()` call: Enhancer, NodeStore,
    # Retriever, and Command (twice, for "example-graph build"/"example-graph show").
    assert registrar.contributed == 5
    assert set(registry.names_for(Enhancer)) == {"example-graph-entities"}
    assert set(registry.names_for(NodeStore)) == {"example-graph"}
    assert set(registry.names_for(Retriever)) == {"example-graph-walk"}
    assert set(registry.names_for(Command)) == {"example-graph build", "example-graph show"}


def test_source_deletable_and_reconcilable_arrive_with_no_extra_add_call() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-example-graph")
    weft_example_graph.register(registrar, weft_example_graph.Settings())
    registrar.commit()

    # Act — the class registered under NodeStore, unwrapped from its `functools.partial`.
    entry = registry.entry(NodeStore, "example-graph")
    target = unwrap_factory(entry.factory)

    # Assert — capability derived, never declared (docs/02-extension-model.md section 1):
    # nothing registers SourceDeletable or Reconcilable directly, and GraphStore satisfies
    # both by having the methods, the identical shape weft-example-ingest demonstrates for
    # its own "eighth and ninth capability." `_satisfies` is `weft_cli.run_services.
    # class_provides`'s own trick (typed `type[object]`, never the Protocol itself) applied
    # locally, since this pack's own tests must not depend on `weft-cli`.
    assert target is GraphStore
    assert _satisfies(target, SourceDeletable)
    assert _satisfies(target, Reconcilable)


def _satisfies(candidate: type[object], capability: type[object]) -> bool:
    try:
        return issubclass(candidate, capability)
    except TypeError:
        return False


def test_the_ext_model_is_buffered_and_attaches_to_node_ext() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-example-graph")

    # Act
    weft_example_graph.register(registrar, weft_example_graph.Settings())

    # Assert — buffered before commit, per `add_ext_model`'s own docstring; not one of the
    # six contracts (a payload primitive, never a contract), and correct to call because
    # `GraphData` attaches to `Node.ext` (docs/02-extension-model.md section 1's own rule).
    assert registrar.ext_models == (GraphData,)


def test_the_pipeline_resource_is_buffered() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-example-graph")

    # Act
    weft_example_graph.register(registrar, weft_example_graph.Settings())

    # Assert — task 5.5's own row: "a named pipeline... users can extend further"
    # (docs/02-extension-model.md section 4). Buffered like `ext_models`, before `commit()`.
    (resource,) = registrar.pipeline_resources
    assert resource.distribution == "weft-example-graph"
    assert resource.package == "weft_example_graph"
    assert resource.resource == "pipelines/kg.yaml"


def test_the_slot_contribution_is_buffered_and_reuses_the_registered_plugin() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-example-graph")

    # Act
    weft_example_graph.register(registrar, weft_example_graph.Settings())

    # Assert — offering `graph-entities` (already registered under `Enhancer` above) into a
    # slot costs nothing extra to declare, the same shape weft-example-ingest demonstrates.
    (contribution,) = registrar.contributions
    assert contribution.slot == weft_example_graph.ENRICH_SLOT
    assert contribution.distribution == "weft-example-graph"
    assert contribution.stage.id == "entities"
    assert contribution.stage.use == "example-graph-entities"


def test_a_second_pack_colliding_on_every_name_leaves_the_first_untouched() -> None:
    """Registration is transactional — CLAUDE.md: "cross-cutting concerns live at the
    registration seam"; a half-finished pack must contribute exactly zero. A second,
    impostor distribution registering under the identical five names raises
    `DuplicateRegistrationError` from inside `commit()` naming both distributions, and the
    first pack's own registrations are unaffected either way.
    """
    registry = Registry()
    first = PackRegistrar(registry, distribution="weft-example-graph")
    weft_example_graph.register(first, weft_example_graph.Settings())
    first.commit()

    second = PackRegistrar(registry, distribution="weft-example-graph-impostor")
    weft_example_graph.register(second, weft_example_graph.Settings())
    with pytest.raises(DuplicateRegistrationError):
        second.commit()
    assert registry.entry(NodeStore, "example-graph").distribution == "weft-example-graph"


def test_a_renderer_is_offered_for_this_packs_own_result_type() -> None:
    """Task **6.20**, G13's third repair. `docs/03-cli.md` → *Plugin-contributed commands*:
    "a result type nobody outside the CLI can format is only half a contract." Before this,
    `weft example-graph show` printed `{"nodes_with_graph_data":11,...}` at a person while
    eighteen built-in commands printed for one — this pack's own result had no way to reach a
    renderer, and that was the gap, not a missing feature in this pack.

    `add_renderer` is the same call the CLI's own `register()` makes for its own eighteen —
    which is the point: a built-in keeps no private path, so the seam a stranger uses is the
    only seam there is.
    """
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-example-graph")

    # Act
    weft_example_graph.register(registrar, weft_example_graph.Settings())

    # Assert
    offered = {offer.result_type for offer in registrar.renderers}
    assert GraphShowResult in offered


def test_this_packs_result_renders_as_text_a_person_can_read() -> None:
    """And the renderer itself is real: what it returns is prose about the graph, not the
    structured dump the fallback would have produced.
    """
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-example-graph")
    weft_example_graph.register(registrar, weft_example_graph.Settings())
    [offer] = [o for o in registrar.renderers if o.result_type is GraphShowResult]
    result = GraphShowResult(nodes_with_graph_data=11, distinct_entities=4, distinct_relations=2)

    # Act
    rendered = offer.render(result)

    # Assert
    assert isinstance(rendered, Rendered)
    assert rendered.stdout is not None
    assert "11" in rendered.stdout
    assert not rendered.stdout.lstrip().startswith("{")
