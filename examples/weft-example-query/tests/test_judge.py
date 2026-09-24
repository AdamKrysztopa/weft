"""This pack's own tests for `ExampleLlmJudge` — a stranger's model role under its own name.

Repair **R43.35**: the field is `judge_role`, a name no first-party plugin uses, declared with
`weft_llm.LLMRole` so a routed ask sees it before any model call rather than refusing after one.
"""

from collections.abc import Mapping

import pytest
from weft_example_query import Settings, register
from weft_example_query.judge import NAME, ExampleJudgeConfig, ExampleLlmJudge

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import MediaType, Node, Outcome, Produced
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry, unwrap_factory
from weft_kernel.resolution import resolve
from weft_kernel.seam import wrap
from weft_llm import LLMRole
from weft_llm.contract import LLM
from weft_llm.payload import Completion, Rendered
from weft_retrieve.contract import Reranker
from weft_retrieve.engine import roles_needed, route_catalogue
from weft_retrieve.payload import Passage, Query, Ranking
from weft_store.contract import Scored

_JUDGE_RUNG = "judge-rung"
_PLAIN_RUNG = "plain-rung"


class _StubLLM:
    """An `LLM` answering `yes` for the passage about a rag engine and `no` otherwise."""

    def __init__(self) -> None:
        self.roles: list[str] = []
        self.prompts: list[str] = []

    async def native_structured_available(self, role: str) -> bool:
        del role
        return False

    async def complete_structured(
        self, rendered: Rendered, schema: Mapping[str, object], *, role: str, ctx: Context
    ) -> Outcome[Completion]:
        raise AssertionError("the judge asks for plain text")

    async def complete(self, rendered: Rendered, *, role: str, ctx: Context) -> Outcome[Completion]:
        del ctx
        prompt = rendered.conversation.messages[-1].content
        self.roles.append(role)
        self.prompts.append(prompt)
        reply = "Yes." if "rag engine" in prompt else "No."
        return Produced(value=Completion(text=reply, model="stub-model"))

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


def _ctx(llm: _StubLLM) -> Context:
    services = ServiceRegistry()
    services.add(LLM, llm)
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _passage(text: str, rank: int) -> Passage:
    node = Node.synthetic(content=text, media_type=MediaType.TEXT, reason="fixture", ordinal=rank)
    return Passage(scored=Scored(value=node, score=0.5), rank=rank, retrieved_by="fixture")


def test_the_judge_is_registered_with_its_role_field_declared_as_a_role() -> None:
    # Act
    entry = _registry().entry(Reranker, NAME)

    # Assert
    plugin = unwrap_factory(entry.factory)
    assert plugin is ExampleLlmJudge
    assert plugin.config_model is ExampleJudgeConfig
    info = ExampleJudgeConfig.model_fields["judge_role"]
    assert any(isinstance(item, LLMRole) for item in info.metadata)
    assert ExampleJudgeConfig().judge_role == "judge"


@pytest.mark.parametrize(
    ("config", "expected"),
    [({}, frozenset({"judge"})), ({"judge_role": "critic"}, frozenset({"critic"}))],
)
def test_the_role_walk_reads_the_judge_role_a_rung_configures(
    config: Mapping[str, object], expected: frozenset[str]
) -> None:
    # Arrange
    registry = _registry()

    # Act
    roles = _roles(_rung(_JUDGE_RUNG, NAME, config), registry)

    # Assert
    assert roles == expected


def test_a_rung_whose_judge_role_is_unmapped_is_not_offered_to_the_router() -> None:
    # Arrange
    registry = _registry()
    catalogue = {
        _JUDGE_RUNG: _rung(_JUDGE_RUNG, NAME),
        _PLAIN_RUNG: _rung(_PLAIN_RUNG, "example-overlap-rerank"),
    }
    rung_roles = {name: _roles(pipeline, registry) for name, pipeline in catalogue.items()}

    # Act
    offered = route_catalogue(
        catalogue, rung_roles=rung_roles, mapped_roles=frozenset({"route", "generate"})
    )

    # Assert
    assert offered.names() == frozenset({_PLAIN_RUNG})
    assert offered.missing_roles() == {_JUDGE_RUNG: ("judge",)}


async def test_the_judge_asks_under_its_configured_role_and_keeps_what_it_accepts() -> None:
    # Arrange
    llm = _StubLLM()
    judge = ExampleLlmJudge(ExampleJudgeConfig(judge_role="critic"))
    wrapped = wrap(judge.run, distribution="weft-example-query", contract="Reranker", plugin=NAME)
    off_topic = _passage("completely unrelated words", 0)
    on_topic = _passage("weft is a rag engine", 1)
    payload = Ranking(origin=Query(text="what is this engine"), hits=(off_topic, on_topic))

    # Act
    outcome = await wrapped(payload, _ctx(llm))

    # Assert
    assert isinstance(outcome, Produced)
    assert llm.roles == ["critic", "critic"]
    assert all("what is this engine" in prompt for prompt in llm.prompts)
    assert [hit.node.id for hit in outcome.value.hits] == [on_topic.node.id]
    assert outcome.value.hits[0].rank == 0
    assert outcome.value.origin == payload.origin
