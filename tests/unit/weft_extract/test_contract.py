"""Unit tests for `weft_extract.contract`.

Mirrors `packages/weft-extract/src/weft_extract/contract.py`. Covers a full
resolve-then-run of `Extractor` through `weft_kernel.runner` with a plugin
that satisfies the contract structurally (no inheritance, exactly the path
`docs/02-extension-model.md` describes), capability being derived by
`isinstance` rather than declared (G4's property, restated for this
contract by `@runtime_checkable`), `SourceDoc` refusing an unknown field the
way every frozen payload model in this project does, and the version
constant fitness function 6 will eventually check.
"""

from collections.abc import AsyncIterator, Sequence

import pytest
from pydantic import ValidationError

from weft_extract.contract import EXTRACTOR_CONTRACT_VERSION, Extractor, SourceDoc
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, Outcome, Produced, SourceId
from weft_kernel.registry import Registry
from weft_kernel.runner import Lifetime, Runner, StageSpec


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


class _TextExtractor:
    """Satisfies `Extractor` structurally — no inheritance, matching every protocol member."""

    version = EXTRACTOR_CONTRACT_VERSION
    lifetime = Lifetime.RUN
    requires: tuple[type, ...] = ()
    provides: tuple[type, ...] = ()

    def __init__(self, config: object) -> None:
        self.config = config

    async def run(self, payload: Sequence[SourceDoc], ctx: Context) -> Outcome[Sequence[Node]]:
        nodes = [
            Node.synthetic(
                content=doc.content.decode("utf-8"),
                media_type=MediaType.TEXT,
                reason="extracted from a source document",
                sources=frozenset({doc.source_id}),
            )
            for doc in payload
        ]
        return Produced(value=nodes)


async def test_extractor_composes_through_the_runner_end_to_end() -> None:
    # Arrange
    registry = Registry()
    registry.add(Extractor, "text", _TextExtractor, distribution="weft-test-pack")
    engine = Runner(registry)
    specs = (StageSpec(id="extract", contract=Extractor, name="text"),)
    doc = SourceDoc(source_id=SourceId("doc-1"), uri="file:///a.txt", content=b"hello")

    async def batches() -> AsyncIterator[list[SourceDoc]]:
        yield [doc]

    # Act
    pipeline = engine.resolve(specs, tenant_id="tenant-a")
    summary = await engine.run(pipeline, batches(), _ctx())

    # Assert
    assert summary.produced == 1


def test_extractor_capability_is_derived_by_isinstance_not_declared() -> None:
    # Arrange
    class _MissingRun:
        """Everything `Extractor` needs except `run` — never satisfies the contract."""

        version = EXTRACTOR_CONTRACT_VERSION
        lifetime = Lifetime.RUN
        requires: tuple[type, ...] = ()
        provides: tuple[type, ...] = ()

    class _OnlyRun:
        """`run` and nothing else — no `version`, `lifetime`, `requires` or `provides`."""

        async def run(self, payload: Sequence[SourceDoc], ctx: Context) -> Outcome[Sequence[Node]]:
            return Produced(value=[])

    # Act / Assert — declaring the metadata neither helps (`_MissingRun`) nor is required
    # (`_OnlyRun`): capability comes from implementing `run`, nothing else.
    assert isinstance(_TextExtractor(config=None), Extractor)
    assert not isinstance(_MissingRun(), Extractor)
    assert isinstance(_OnlyRun(), Extractor)


def test_source_doc_refuses_an_unknown_field() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        SourceDoc.model_validate(
            {"source_id": "doc-1", "uri": "file:///a.txt", "content": b"hi", "bogus": "x"}
        )


def test_extractor_version_is_declared_on_the_contract_itself() -> None:
    # Act / Assert
    assert Extractor.version == EXTRACTOR_CONTRACT_VERSION
