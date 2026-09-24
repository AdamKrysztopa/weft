"""This pack's own tests for `ExampleJudgePanel` — a stranger's composer of other rerankers.

Repair **R43.42**: its panelists are reached through `StageLookup`, each named by a field this
pack spells its own way and declares with `weft_retrieve.SubPlugin`, so a routed ask reads every
panelist's role before any model call rather than refusing after one.
"""

from collections.abc import Mapping

from weft_example_query import Settings, register
from weft_example_query.judge import NAME as JUDGE_NAME
from weft_example_query.panel import NAME, ExampleJudgePanel, ExamplePanelConfig, ExamplePanelist

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import MediaType, Node, Outcome, Produced
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry, unwrap_factory
from weft_kernel.resolution import resolve
from weft_kernel.seam import wrap
from weft_llm.contract import LLM
from weft_llm.payload import Completion, Rendered
from weft_retrieve import SubPlugin
from weft_retrieve.contract import Reranker, StageLookup
from weft_retrieve.engine import roles_needed, route_catalogue, stage_lookup
from weft_retrieve.payload import Passage, Query, Ranking
from weft_store.contract import Scored

_PANEL_RUNG = "panel-rung"
_PLAIN_RUNG = "plain-rung"
_PANELISTS: tuple[Mapping[str, object], ...] = (
    {"reranker": JUDGE_NAME, "settings": {"judge_role": "critic"}},
    {"reranker": JUDGE_NAME},
)


class _StubLLM:
    """An `LLM` whose `critic` accepts the rag-engine passage and whose `judge` the vector one."""

    def __init__(self) -> None:
        self.roles: list[str] = []

    async def native_structured_available(self, role: str) -> bool:
        del role
        return False

    async def complete_structured(
        self, rendered: Rendered, schema: Mapping[str, object], *, role: str, ctx: Context
    ) -> Outcome[Completion]:
        raise AssertionError("the judges ask for plain text")

    async def complete(self, rendered: Rendered, *, role: str, ctx: Context) -> Outcome[Completion]:
        del ctx
        prompt = rendered.conversation.messages[-1].content
        self.roles.append(role)
        accepted = ("rag engine" in prompt and role == "critic") or (
            "vector index" in prompt and role == "judge"
        )
        return Produced(value=Completion(text="Yes." if accepted else "No.", model="stub-model"))

    async def close(self) -> None: ...


def _registry() -> Registry:
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-example-query")
    register(registrar, Settings())
    registrar.commit()
    return registry


def _rung(name: str, use: str, config: Mapping[str, object] | None = None) -> Pipeline:
    stage = StageDeclaration(id="rerank", use=use, config=dict(config or {}))
    return Pipeline(name=name, vars={"route.summary": f"{name} summary"}, stages=(stage,))


def _roles(pipeline: Pipeline, registry: Registry) -> frozenset[str]:
    resolved = resolve(pipeline, registry=registry, contracts={"rerank": Reranker})
    return roles_needed(resolved, registry)


def _passage(text: str, rank: int) -> Passage:
    node = Node.synthetic(content=text, media_type=MediaType.TEXT, reason="fixture", ordinal=rank)
    return Passage(scored=Scored(value=node, score=0.5), rank=rank, retrieved_by="fixture")


def test_the_panel_is_registered_with_its_panelist_reference_declared() -> None:
    # Act
    entry = _registry().entry(Reranker, NAME)

    # Assert
    plugin = unwrap_factory(entry.factory)
    assert plugin is ExampleJudgePanel
    assert plugin.config_model is ExamplePanelConfig
    markers = [
        item
        for item in ExamplePanelist.model_fields["reranker"].metadata
        if isinstance(item, SubPlugin)
    ]
    assert [marker.config for marker in markers] == ["settings"]


def test_the_role_walk_reads_every_panelist_with_its_own_settings() -> None:
    # Arrange
    registry = _registry()

    # Act
    roles = _roles(_rung(_PANEL_RUNG, NAME, {"panelists": list(_PANELISTS)}), registry)

    # Assert
    assert roles == frozenset({"critic", "judge"})


def test_a_rung_whose_panelist_role_is_unmapped_is_not_offered_to_the_router() -> None:
    # Arrange
    registry = _registry()
    catalogue = {
        _PANEL_RUNG: _rung(_PANEL_RUNG, NAME, {"panelists": list(_PANELISTS)}),
        _PLAIN_RUNG: _rung(_PLAIN_RUNG, "example-overlap-rerank"),
    }
    rung_roles = {name: _roles(pipeline, registry) for name, pipeline in catalogue.items()}

    # Act
    offered = route_catalogue(
        catalogue, rung_roles=rung_roles, mapped_roles=frozenset({"route", "generate", "judge"})
    )

    # Assert
    assert offered.names() == frozenset({_PLAIN_RUNG})
    assert offered.missing_roles() == {_PANEL_RUNG: ("critic",)}


async def test_the_panel_keeps_each_passage_any_panelist_keeps_in_its_original_order() -> None:
    # Arrange
    registry = _registry()
    llm = _StubLLM()
    services = ServiceRegistry()
    services.add(LLM, llm)
    services.add(StageLookup, stage_lookup(registry))
    ctx = Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )
    panel = ExampleJudgePanel(ExamplePanelConfig.model_validate({"panelists": _PANELISTS}))
    wrapped = wrap(panel.run, distribution="weft-example-query", contract="Reranker", plugin=NAME)
    vector = _passage("a vector index answers it", 0)
    off_topic = _passage("completely unrelated words", 1)
    engine = _passage("weft is a rag engine", 2)
    payload = Ranking(origin=Query(text="what is this engine"), hits=(vector, off_topic, engine))

    # Act
    outcome = await wrapped(payload, ctx)

    # Assert
    assert isinstance(outcome, Produced)
    assert sorted(set(llm.roles)) == ["critic", "judge"]
    assert [hit.node.id for hit in outcome.value.hits] == [vector.node.id, engine.node.id]
    assert [hit.rank for hit in outcome.value.hits] == [0, 1]
    assert outcome.value.origin == payload.origin
