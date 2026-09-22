"""Task 43.3: the OpenAI embedder's requests run concurrently, bounded by an account setting.

The bound lives on `weft_openai.Settings` (`[packs.openai] max_concurrent_requests`), never on
`OpenAIEmbedderConfig`: a `with:` field enters pipeline identity with its default, so a new one
would have made every OpenAI index re-embed (`fix-plans/22` → *Settled 2026-09-22*).

The double is `test_embedder.py`'s `_Embeddings`, extended with a per-request delay and an
in-flight counter. Requests are told apart by their first text, `t000`–`t639`, 128 per request.
"""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field

import httpx2
import pytest
from openai import APIStatusError, Omit, omit
from pydantic import SecretStr

from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, Produced
from weft_llm.usage import recording_usage
from weft_openai import Settings
from weft_openai.embedder import EmbeddingRequestFailedError, OpenAIEmbedder, OpenAIEmbedderConfig

_TEXTS = 640
_BATCH = 128


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _nodes() -> list[Node]:
    return [
        Node.synthetic(content=f"t{i:03d}", media_type=MediaType.TEXT, reason="test fixture")
        for i in range(_TEXTS)
    ]


def _request_of(texts: Sequence[str]) -> int:
    return int(texts[0][1:]) // _BATCH


@dataclass
class _Item:
    index: int
    embedding: Sequence[float]


@dataclass
class _Usage:
    prompt_tokens: int


@dataclass
class _Response:
    data: Sequence[_Item]
    usage: _Usage | None = None


@dataclass
class _Embeddings:
    """Request `slow` sleeps longest; request `failing` raises after `fail_after` seconds."""

    slow: int = 2
    failing: int | None = None
    fail_after: float = 0.02
    in_flight: int = 0
    max_in_flight: int = 0
    started: list[int] = field(default_factory=lambda: [])
    finished: list[int] = field(default_factory=lambda: [])
    cancelled: list[int] = field(default_factory=lambda: [])

    async def create(
        self, *, input: list[str], model: str, dimensions: int | Omit = omit
    ) -> _Response:
        del model, dimensions
        request = _request_of(input)
        self.started.append(request)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if request == self.failing:
                await asyncio.sleep(self.fail_after)
                http_request = httpx2.Request("POST", "https://api.openai.com/v1/embeddings")
                response = httpx2.Response(400, request=http_request)
                raise APIStatusError("input is invalid", response=response, body=None)
            await asyncio.sleep(0.05 if request == self.slow else 0.01)
            if self.failing is not None:
                await asyncio.sleep(10)
        except asyncio.CancelledError:
            self.cancelled.append(request)
            raise
        finally:
            self.in_flight -= 1
        self.finished.append(request)
        return _Response(
            data=[_Item(index=p, embedding=[float(int(t[1:]))] * 4) for p, t in enumerate(input)],
            usage=_Usage(prompt_tokens=len(input)),
        )


@dataclass
class _Client:
    embeddings: _Embeddings = field(default_factory=_Embeddings)
    closed: bool = False

    async def close(self) -> None:
        self.closed = True


def _embedder(client: _Client, *, bound: int) -> OpenAIEmbedder:
    settings = Settings(api_key=SecretStr("sk-test"), max_concurrent_requests=bound)
    return OpenAIEmbedder(settings, OpenAIEmbedderConfig(batch_size=_BATCH), client=client)


@pytest.mark.parametrize("bound", [1, 2, 3])
async def test_requests_in_flight_never_exceed_the_account_bound_and_reach_it(bound: int) -> None:
    # Arrange
    client = _Client()

    # Act
    outcome = await _embedder(client, bound=bound).run(_nodes(), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert sorted(client.embeddings.started) == [0, 1, 2, 3, 4]
    assert client.embeddings.max_in_flight == bound


async def test_vectors_return_in_node_order_though_a_middle_request_finishes_last() -> None:
    # Arrange
    client = _Client(embeddings=_Embeddings(slow=2))
    nodes = _nodes()

    # Act
    outcome = await _embedder(client, bound=5).run(nodes, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert client.embeddings.finished[-1] == 2
    assert [n.id for n in outcome.value] == [n.id for n in nodes]
    assert all(
        n.embedding is not None and n.embedding.values[0] == float(i)
        for i, n in enumerate(outcome.value)
    )


async def test_every_request_records_its_usage_once() -> None:
    # Arrange
    client = _Client()

    # Act
    with recording_usage() as tally:
        await _embedder(client, bound=3).run(_nodes(), _ctx())

    # Assert
    assert len(tally.entries) == 5
    assert (
        sorted(e.usage.prompt_tokens for e in tally.entries if e.usage is not None) == [_BATCH] * 5
    )


async def test_a_failed_request_cancels_its_in_flight_siblings_and_raises_the_leaf_error() -> None:
    """The leaf `EmbeddingRequestFailedError`, never an `ExceptionGroup`: `run_index` catches
    `WeftError` per batch
    (`weft_cli/ingest.py:740 "except WeftError as exc:"`), and a group would escape that handler."""
    # Arrange
    client = _Client(embeddings=_Embeddings(failing=2))

    # Act
    with pytest.raises(EmbeddingRequestFailedError):
        await _embedder(client, bound=3).run(_nodes(), _ctx())

    # Assert
    embeddings = client.embeddings
    unfinished = set(embeddings.started) - set(embeddings.finished) - {2}
    assert unfinished
    assert set(embeddings.cancelled) == unfinished
    assert embeddings.in_flight == 0


async def test_cancelling_the_stage_cancels_every_request_and_propagates() -> None:
    # Arrange
    client = _Client(embeddings=_Embeddings(failing=4, fail_after=10))
    task = asyncio.create_task(_embedder(client, bound=5).run(_nodes(), _ctx()))
    await asyncio.sleep(0.03)

    # Act
    task.cancel()

    # Assert
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.embeddings.in_flight == 0
    assert client.embeddings.cancelled


def test_the_bound_is_an_account_setting_and_enters_no_pipeline_identity() -> None:
    # Arrange / Act
    identity_fields = set(OpenAIEmbedderConfig.model_fields)

    # Assert
    assert "max_concurrent_requests" in Settings.model_fields
    assert identity_fields == {"model", "dimensions", "batch_size"}


def test_a_bound_below_one_is_refused() -> None:
    with pytest.raises(ValueError, match="greater than or equal to 1"):
        Settings(api_key=SecretStr("sk-test"), max_concurrent_requests=0)
