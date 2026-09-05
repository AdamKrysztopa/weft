"""Unit tests for `weft_retrieve.engine`.

Mirrors `packages/weft-rag/src/weft_retrieve/engine.py`. Ledger **2.8**:
`weft_retrieve.contract.StageLookup` and `weft_retrieve.contract.RouteCatalogue` are
published as services (task 2.4) and used through fakes by every technique's own test
module (`weft_retrieve.contract.RouteCatalogue`'s own docstring: "populated by the same
eager discovery pass that builds the registry"), but nothing in the tree built the real
thing until this task. Two classes, covered in turn:

1. `RegistryStageLookup` — `names()` reads straight off the registry; `build()` resolves,
   constructs and returns a callable already through `weft_kernel.seam.wrap` (driven
   through the seam directly: a stage that raises is reported with the seam's own
   attribution, not a bare exception); `build_capability()` resolves and constructs with
   no wrap, matching `weft_retrieve.routing`'s own `_StubLookup` double, which answers
   `build_capability` unwrapped — the shape this module's real implementation takes.
2. `PipelineRouteCatalogue` — every pipeline whose own `vars:` block carries
   `route.summary` becomes a `RouteCandidate`; one that does not is invisible to it, the
   same "not every pipeline is routable" property `.phase2-design.md` §5 states.
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from pydantic import BaseModel, ConfigDict

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.errors import WeftError
from weft_kernel.payload import Outcome, Produced
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry, UnknownPluginError
from weft_retrieve.engine import PipelineRouteCatalogue, RegistryStageLookup


class _EchoConfig(BaseModel):
    prefix: str = ""


class _Echo:
    """A trivial `Stage[str, str]` — enough to prove `build()` resolves, constructs, and
    wraps, with no dependency on any real query-path contract."""

    config_model: ClassVar[type[_EchoConfig]] = _EchoConfig

    def __init__(self, config: _EchoConfig | None = None) -> None:
        self._prefix = config.prefix if config is not None else ""

    async def run(self, payload: str, ctx: Context) -> Outcome[str]:
        del ctx
        return Produced(value=f"{self._prefix}{payload}")


class _Boom:
    """A `Stage[str, str]` that always raises — proves `build()`'s callable runs through
    the seam rather than around it: the seam is what turns a bare exception into a
    `WeftError` carrying attribution."""

    config_model: ClassVar[type[_EchoConfig]] = _EchoConfig

    def __init__(self, config: _EchoConfig | None = None) -> None:
        del config

    async def run(self, payload: str, ctx: Context) -> Outcome[str]:
        del payload, ctx
        raise RuntimeError("boom")


class _Capability:
    """A named capability with no `run` at all — `build_capability`'s own subject, the
    same shape `weft_retrieve.contract.Prompt` takes."""

    def __init__(self, config: object = None) -> None:
        self.config = config


def _echo_factory(config: object) -> _Echo:
    return _Echo(config if isinstance(config, _EchoConfig) else None)


def _boom_factory(config: object) -> _Boom:
    del config
    return _Boom()


def _capability_factory(config: object) -> _Capability:
    return _Capability(config)


def _ctx() -> Context:
    return Context(
        tenant_id="t", run_id="r", trace_id="tr", locale="en", services=ServiceRegistry()
    )


async def test_stage_lookup_build_resolves_constructs_and_wraps_through_the_seam() -> None:
    # Arrange
    registry = Registry()
    registry.add_many([(_Echo, "echo", _echo_factory)], distribution="weft-happy")
    lookup = RegistryStageLookup(registry)

    # Act
    run = await lookup.build(_Echo, "echo", _EchoConfig(prefix=">> "))
    outcome = await run("hi", _ctx())

    # Assert
    assert outcome == Produced(value=">> hi")


async def test_stage_lookup_build_runs_through_the_seam_which_attributes_a_raised_exception() -> (
    None
):
    # Arrange
    registry = Registry()
    registry.add_many([(_Boom, "boom", _boom_factory)], distribution="weft-broken")
    lookup = RegistryStageLookup(registry)

    # Act
    run = await lookup.build(_Boom, "boom")
    with pytest.raises(WeftError) as excinfo:
        await run("hi", _ctx())

    # Assert — the seam's own attribution, not a bare RuntimeError.
    assert excinfo.value.pack == "weft-broken"
    assert excinfo.value.plugin == "boom"


async def test_stage_lookup_build_capability_resolves_and_constructs_with_no_wrap() -> None:
    # Arrange
    registry = Registry()
    registry.add_many([(_Capability, "cap", _capability_factory)], distribution="weft-happy")
    lookup = RegistryStageLookup(registry)

    # Act
    capability = await lookup.build_capability(_Capability, "cap", "config-value")

    # Assert — the raw instance, not a wrapped callable: `_Capability` has no `run` at all.
    assert isinstance(capability, _Capability)
    assert capability.config == "config-value"


def test_stage_lookup_names_reads_straight_off_the_registry() -> None:
    # Arrange
    registry = Registry()
    registry.add_many([(_Echo, "echo", _echo_factory)], distribution="weft-happy")
    lookup = RegistryStageLookup(registry)

    # Act / Assert
    assert lookup.names(_Echo) == frozenset({"echo"})


async def test_stage_lookup_build_names_the_unregistered_plugin() -> None:
    # Arrange
    registry = Registry()
    lookup = RegistryStageLookup(registry)

    # Act / Assert
    with pytest.raises(UnknownPluginError, match="ghost"):
        await lookup.build(_Echo, "ghost")


def test_route_catalogue_offers_only_pipelines_carrying_route_summary() -> None:
    # Arrange
    routable = Pipeline(
        name="retrieve-then-generate",
        vars={"route.summary": "one search, one answer", "route.cost": "cheap"},
        stages=(StageDeclaration(id="s", use="no-retrieval"),),
    )
    not_routable = Pipeline(
        name="internal-only", stages=(StageDeclaration(id="s", use="no-retrieval"),)
    )
    catalogue = PipelineRouteCatalogue(
        {"internal-only": not_routable, "retrieve-then-generate": routable}
    )

    # Act
    candidates = catalogue.candidates()

    # Assert
    assert [c.name for c in candidates] == ["retrieve-then-generate"]
    assert candidates[0].summary == "one search, one answer"
    assert candidates[0].cost == "cheap"
    assert catalogue.names() == frozenset({"retrieve-then-generate"})


def test_route_catalogue_defaults_cost_to_empty_when_the_pipeline_names_none() -> None:
    # Arrange
    pipeline = Pipeline(
        name="no-retrieval",
        vars={"route.summary": "answers from memory alone"},
        stages=(StageDeclaration(id="s", use="no-retrieval"),),
    )
    catalogue = PipelineRouteCatalogue({"no-retrieval": pipeline})

    # Act / Assert
    [candidate] = catalogue.candidates()
    assert candidate.cost == ""


# --- task 8.11: a sub-plugin's config block is validated before its factory sees it --------
#
# Found by running `weft ask --pipeline corrective-retrieve` at task 8.10. `corrective`,
# `iterative-retrieval` and `refine-on-uncertainty` each resolve a sibling by name through
# `StageLookup` and each publishes a `*_config` field typed `Mapping[str, object] | None` —
# seven such fields between them, every one documented as the way a document retunes the
# sibling. `build` passed that mapping to `entry.factory` untouched, so the plugin received a
# raw `dict` where its own config object was expected and died inside its own `run` with
# `'dict' object has no attribute 'channels'`. Seven documented configuration surfaces, none
# of which worked, and no test noticed because every test that exercised these plugins left
# the sibling's config at `None`.


class _SubConfig(BaseModel):
    """Declared the way every real Weft plugin config is — frozen, `extra="forbid"` — so an
    unknown field is rejected here for the same reason it would be in production. A plain
    `BaseModel` silently ignores extras, and a test using one would have proved that
    validation ran without proving it refuses anything."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    top_k: int = 20


class _ConfigurableSub:
    config_model: ClassVar[type[_SubConfig]] = _SubConfig

    def __init__(self, config: _SubConfig | None = None) -> None:
        self.config = config

    async def run(self, payload: object, ctx: Context) -> Outcome[object]:
        del ctx
        return Produced(value=payload)


class _UnconfigurableSub:
    def __init__(self, config: object = None) -> None:
        self.config = config

    async def run(self, payload: object, ctx: Context) -> Outcome[object]:
        del ctx
        return Produced(value=payload)


def _sub_registry(contract: type, name: str, plugin: type) -> Registry:
    registry = Registry()
    registry.add(contract, name, plugin, distribution="acme-sub")
    return registry


async def test_build_validates_a_mapping_into_the_plugins_own_config_model() -> None:
    # Arrange — the exact shape a `with:` block reaches a sibling through.
    built: list[object] = []

    class _Recording(_ConfigurableSub):
        def __init__(self, config: _SubConfig | None = None) -> None:
            super().__init__(config)
            built.append(config)

    lookup = RegistryStageLookup(_sub_registry(_ConfigurableSub, "sub", _Recording))

    # Act
    await lookup.build(_ConfigurableSub, "sub", {"top_k": 5})

    # Assert — a validated model, never the raw mapping.
    assert built == [_SubConfig(top_k=5)]


async def test_build_leaves_an_already_built_config_object_alone() -> None:
    """The other caller shape, which must keep working: a plugin that has already
    constructed its sibling's config and hands it over typed."""
    # Arrange
    built: list[object] = []

    class _Recording(_ConfigurableSub):
        def __init__(self, config: _SubConfig | None = None) -> None:
            super().__init__(config)
            built.append(config)

    lookup = RegistryStageLookup(_sub_registry(_ConfigurableSub, "sub", _Recording))
    already = _SubConfig(top_k=7)

    # Act
    await lookup.build(_ConfigurableSub, "sub", already)

    # Assert
    assert built == [already]


async def test_build_refuses_a_mapping_the_config_model_rejects_naming_the_fields() -> None:
    # Arrange
    lookup = RegistryStageLookup(_sub_registry(_ConfigurableSub, "sub", _ConfigurableSub))

    # Act / Assert — loud, at construction, naming what the model accepts (requirement 5).
    with pytest.raises(WeftError) as raised:
        await lookup.build(_ConfigurableSub, "sub", {"nosuchfield": 1})
    message = str(raised.value)
    assert "sub" in message
    assert "top_k" in message


async def test_build_refuses_a_mapping_for_a_plugin_that_publishes_no_config_model() -> None:
    """A block with nowhere checked to land must never be silently accepted and dropped —
    `weft_kernel.resolution.StageNotConfigurableError`'s own rule, applied one seam over."""
    # Arrange
    lookup = RegistryStageLookup(_sub_registry(_UnconfigurableSub, "sub", _UnconfigurableSub))

    # Act / Assert
    with pytest.raises(WeftError) as raised:
        await lookup.build(_UnconfigurableSub, "sub", {"top_k": 5})
    message = str(raised.value)
    assert "sub" in message
    # Not `UnknownPluginError` by accident — the plugin resolves; it is the block that has
    # nowhere to land, which is a different fact and needs a different sentence.
    assert "config" in message.lower()


async def test_build_capability_validates_the_same_way() -> None:
    """`Sufficiency` is reached through `build_capability`, and `iterative-retrieval`'s
    `sufficiency_config` is one of the seven fields — so the same repair has to cover it."""
    # Arrange
    built: list[object] = []

    class _Recording(_ConfigurableSub):
        def __init__(self, config: _SubConfig | None = None) -> None:
            super().__init__(config)
            built.append(config)

    lookup = RegistryStageLookup(_sub_registry(_ConfigurableSub, "sub", _Recording))

    # Act
    await lookup.build_capability(_ConfigurableSub, "sub", {"top_k": 3})

    # Assert
    assert built == [_SubConfig(top_k=3)]
