"""`weft ask --explain` says where the time went — ledger tasks **33.4** and **33.5**.

`--explain` already answers *why this ranking*; it now also answers *what ran, for how long, over
how many items*. The ask command opens a `weft_kernel.seam.recording()` scope around its own work
only when the flag is set (the owner's Q5, 2026-09-15), so every transcript and every `--json` dump
without it is byte-identical, and the records travel on `AskCommandResult.stages`.

**Two concurrent explained asks must not mix** (33.4). A `ContextVar` scope is per task, so each
call's records are its own. The fixture is identical in both calls on purpose: if the lists mixed,
each would hold two `ask:embed` records rather than one, which is a count the assertion can see.

The doubles are `tests/unit/weft_cli/test_ask.py`'s (`L11.17`).
"""

import asyncio
from collections.abc import Sequence

from weft_cli import commands, render
from weft_command.contract import CommandResult
from weft_embed import Embedder
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import MediaType, Node, Outcome, Produced, Vector
from weft_kernel.registry import Registry
from weft_kernel.seam import StageRecord
from weft_store import Filter, NodeStore, Scored


class _FakeEmbedder:
    def __init__(self, config: object) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        await asyncio.sleep(0)
        return Produced(value=[node.with_embedding(Vector(values=(1.0,))) for node in payload])


class _FakeVectorSearchStore:
    def __init__(self, config: object) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        return Produced(value=payload)

    async def search_vector(
        self, vector: Vector, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        del vector, top_k, filter
        found = Node.synthetic(
            content="a stored passage", media_type=MediaType.TEXT, reason="fixture"
        )
        return [Scored(value=found, score=0.9)]

    async def aclose(self) -> None:
        return None


def _ctx() -> Context:
    registry = Registry()
    registry.add(Embedder, "hash", _FakeEmbedder, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", _FakeVectorSearchStore, distribution="weft-store")
    deps = Dependencies(
        registry=registry,
        reports=(),
        services=ServiceSelection(embed="hash", store="pgvector"),
    )
    services = ServiceRegistry()
    services.add(Dependencies, deps)
    return Context(tenant_id="t", run_id="r", trace_id="tr", locale="en", services=services)


async def _ask(*, explain: bool) -> commands.AskCommandResult:
    args = commands.AskArgs(question="what changed?", retrieve_only=True, explain=explain)
    outcome = await commands.AskCommand().run(args, _ctx())
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.AskCommandResult)
    return result


async def test_an_explained_ask_carries_a_record_for_the_embed_it_ran() -> None:
    # Act
    result = await _ask(explain=True)

    # Assert
    embeds = [record for record in result.stages if record.label == "ask:embed"]
    assert len(embeds) == 1
    assert isinstance(embeds[0], StageRecord)
    assert embeds[0].items_in == 1


async def test_an_ask_without_explain_records_nothing() -> None:
    # Act
    result = await _ask(explain=False)

    # Assert
    assert result.stages == ()


async def test_two_concurrent_explained_asks_keep_their_records_apart() -> None:
    # Act
    first, second = await asyncio.gather(_ask(explain=True), _ask(explain=True))

    # Assert
    for result in (first, second):
        assert [record.label for record in result.stages].count("ask:embed") == 1


async def test_the_json_dump_of_an_explained_ask_carries_its_stages() -> None:
    """`R18.3`: `--json` is the result model's dump, so the records reach a machine unchanged."""
    # Act
    result = await _ask(explain=True)

    # Assert
    assert "ask:embed" in result.model_dump_json()


async def test_the_explain_block_names_each_stage_with_its_milliseconds() -> None:
    # Arrange
    result = await _ask(explain=True)
    outcome: Outcome[CommandResult] = Produced(value=result)

    # Act
    stdout = render.render_outcome(outcome).stdout or ""

    # Assert
    lines = stdout.splitlines()
    assert "stages:" in [line.strip() for line in lines]
    (embed_line,) = [line for line in lines if "ask:embed" in line]
    assert embed_line.startswith(" ")
    assert " ms" in embed_line
    assert "in 1" in embed_line


async def test_an_unexplained_ask_renders_no_stage_block() -> None:
    # Arrange
    result = await _ask(explain=False)
    outcome: Outcome[CommandResult] = Produced(value=result)

    # Act
    stdout = render.render_outcome(outcome).stdout or ""

    # Assert
    assert "stages:" not in [line.strip() for line in stdout.splitlines()]
