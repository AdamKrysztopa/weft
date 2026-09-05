"""Unit tests for `weft_openai.embedder`.

Mirrors `packages/weft-openai/src/weft_openai/embedder.py`. Covers the happy
path (every node comes back carrying the vector the API returned for its own
content, in order), the edge cases that matter for a metered API (an empty
batch never becomes a request; a batch larger than `batch_size` becomes
several), and the error cases: no credential, a node with nothing to embed,
and the API refusing the call.

**No request leaves this file.** The embedder is driven through an injected
stub client — see `OpenAIEmbedder`'s own docstring for why that seam exists
and why nothing in a pipeline document can reach it. The live half of this
pack, the half that proves a vector carries semantic meaning at all, is
`tests/integration/test_openai_embedder.py`, which skips with a reason when
no credential is present. That split is what keeps `poe ci-checks` runnable
with no key and no network.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest
from openai import AsyncOpenAI, Omit, omit
from pydantic import SecretStr, ValidationError

from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Outcome, Produced
from weft_openai import Settings
from weft_openai.embedder import (
    VENDOR_BASE_URL,
    EmbeddingRequestFailedError,
    MissingApiKeyError,
    OpenAIEmbedder,
    OpenAIEmbedderConfig,
    UnembeddableNodeError,
    build_client,
)


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _node(content: str) -> Node:
    return Node.synthetic(content=content, media_type=MediaType.TEXT, reason="test fixture")


def _settings(api_key: str = "sk-test") -> Settings:
    return Settings(api_key=SecretStr(api_key))


@dataclass
class _Item:
    """One element of the API's `data` array — the two fields this pack reads."""

    index: int
    embedding: Sequence[float]


@dataclass
class _Response:
    data: Sequence[_Item]


@dataclass
class _Call:
    """One request this stand-in was handed, kept so a test can assert on what was sent."""

    input: list[str]
    model: str
    dimensions: int | Omit


@dataclass
class _Embeddings:
    """A stand-in for `AsyncOpenAI.embeddings` — the shape `EmbeddingsResource` declares.

    Typed against that Protocol rather than accepting `**kwargs`, so a change
    to what this pack sends fails here at the type check rather than passing a
    test that records whatever it was given.
    """

    width: int = 4
    calls: list[_Call] = field(default_factory=lambda: [])
    error: Exception | None = None
    shuffled: bool = False

    async def create(
        self, *, input: list[str], model: str, dimensions: int | Omit = omit
    ) -> _Response:
        self.calls.append(_Call(input=list(input), model=model, dimensions=dimensions))
        if self.error is not None:
            raise self.error
        items = [
            _Item(index=position, embedding=[float(len(text)) + position] * self.width)
            for position, text in enumerate(input)
        ]
        return _Response(data=list(reversed(items)) if self.shuffled else items)


@dataclass
class _Client:
    embeddings: _Embeddings = field(default_factory=_Embeddings)
    closed: bool = False

    async def close(self) -> None:
        self.closed = True


async def test_run_attaches_the_vector_the_api_returned_for_each_node() -> None:
    # Arrange
    client = _Client()
    embedder = OpenAIEmbedder(_settings(), client=client)
    nodes = [_node("hello"), _node("a longer passage")]

    # Act
    outcome: Outcome[Sequence[Node]] = await embedder.run(nodes, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    embedded = outcome.value
    assert [node.content for node in embedded] == [node.content for node in nodes]
    assert [node.id for node in embedded] == [node.id for node in nodes]
    for node in embedded:
        assert node.embedding is not None
        assert node.embedding.dimension == 4
    assert embedded[0].embedding != embedded[1].embedding
    # One request, carrying the default model and every node's content in order.
    (call,) = client.embeddings.calls
    assert call.model == "text-embedding-3-small"
    assert call.input == ["hello", "a longer passage"]
    # Unset `dimensions` sends the SDK's own "absent" sentinel, never a `None` the API
    # would refuse — the model's native width is what an unconfigured stage asks for.
    assert call.dimensions is omit


async def test_run_pairs_each_vector_with_its_own_node_by_index_not_by_arrival() -> None:
    # Arrange — the API documents `data` as an array of objects each carrying its own
    # `index`; nothing promises arrival order, and a pack that zipped would silently
    # attach one node's meaning to another's text.
    client = _Client(embeddings=_Embeddings(shuffled=True))
    embedder = OpenAIEmbedder(_settings(), client=client)
    ordered = await OpenAIEmbedder(_settings(), client=_Client()).run(
        [_node("first"), _node("second")], _ctx()
    )

    # Act
    outcome = await embedder.run([_node("first"), _node("second")], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert isinstance(ordered, Produced)
    assert [node.embedding for node in outcome.value] == [node.embedding for node in ordered.value]


async def test_run_splits_a_batch_larger_than_the_configured_batch_size() -> None:
    # Arrange
    client = _Client()
    embedder = OpenAIEmbedder(_settings(), OpenAIEmbedderConfig(batch_size=2), client=client)
    nodes = [_node(f"passage {position}") for position in range(5)]

    # Act
    outcome = await embedder.run(nodes, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert len(outcome.value) == 5
    assert [len(call.input) for call in client.embeddings.calls] == [2, 2, 1]


async def test_run_sends_the_configured_dimensions_when_one_is_set() -> None:
    # Arrange
    client = _Client(embeddings=_Embeddings(width=256))
    embedder = OpenAIEmbedder(_settings(), OpenAIEmbedderConfig(dimensions=256), client=client)

    # Act
    outcome = await embedder.run([_node("hello")], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    (call,) = client.embeddings.calls
    assert call.dimensions == 256


async def test_run_answers_nothing_to_produce_for_an_empty_batch_without_calling_the_api() -> None:
    # Arrange
    client = _Client()
    embedder = OpenAIEmbedder(_settings(), client=client)

    # Act
    outcome = await embedder.run([], _ctx())

    # Assert
    assert outcome == NothingToProduce(reason="no nodes to embed")
    assert client.embeddings.calls == []


async def test_run_without_a_credential_names_the_configuration_line_that_supplies_one() -> None:
    # Arrange — the pack registers cleanly with no key (every settings field has a default,
    # so `register()` cannot raise and the plugin cannot vanish from the registry); the
    # refusal belongs here, at use.
    embedder = OpenAIEmbedder(Settings())

    # Act / Assert
    with pytest.raises(MissingApiKeyError) as raised:
        await embedder.run([_node("hello")], _ctx())
    assert "[packs.openai] api_key" in str(raised.value)


async def test_a_node_with_nothing_to_embed_is_refused_by_id() -> None:
    # Arrange
    client = _Client()
    embedder = OpenAIEmbedder(_settings(), client=client)
    blank = _node("   ")

    # Act / Assert
    with pytest.raises(UnembeddableNodeError) as raised:
        await embedder.run([_node("hello"), blank], _ctx())
    assert str(blank.id) in str(raised.value)
    assert client.embeddings.calls == []


async def test_an_api_refusal_is_raised_as_a_weft_error_naming_the_model() -> None:
    # Arrange
    import httpx2
    from openai import APIStatusError

    request = httpx2.Request("POST", "https://api.openai.com/v1/embeddings")
    response = httpx2.Response(400, request=request)
    client = _Client(
        embeddings=_Embeddings(
            error=APIStatusError("input is invalid", response=response, body=None)
        )
    )
    embedder = OpenAIEmbedder(_settings(), client=client)

    # Act / Assert
    with pytest.raises(EmbeddingRequestFailedError) as raised:
        await embedder.run([_node("hello")], _ctx())
    assert "text-embedding-3-small" in str(raised.value)
    assert raised.value.transient is False


async def test_a_connection_failure_is_marked_transient() -> None:
    # Arrange — the kernel runs no retry engine, so "worth retrying" is this pack's to say.
    import httpx2
    from openai import APIConnectionError

    request = httpx2.Request("POST", "https://api.openai.com/v1/embeddings")
    client = _Client(embeddings=_Embeddings(error=APIConnectionError(request=request)))
    embedder = OpenAIEmbedder(_settings(), client=client)

    # Act / Assert
    with pytest.raises(EmbeddingRequestFailedError) as raised:
        await embedder.run([_node("hello")], _ctx())
    assert raised.value.transient is True


async def test_a_response_missing_a_vector_is_refused_rather_than_paired_by_position() -> None:
    # Arrange — a stand-in that answers one item short. Pairing what arrived onto the first
    # nodes would attach the wrong meaning to every node after the gap and lose the last
    # one's embedding entirely, which nothing downstream could detect.
    class _ShortEmbeddings(_Embeddings):
        async def create(
            self, *, input: list[str], model: str, dimensions: int | Omit = omit
        ) -> _Response:
            full = await super().create(input=input, model=model, dimensions=dimensions)
            return _Response(data=list(full.data)[:-1])

    client = _Client(embeddings=_ShortEmbeddings())
    embedder = OpenAIEmbedder(_settings(), client=client)

    # Act / Assert
    with pytest.raises(EmbeddingRequestFailedError) as raised:
        await embedder.run([_node("first"), _node("second")], _ctx())
    assert "1 vector(s) for 2 input(s)" in str(raised.value)


async def test_aclose_closes_the_client_it_built() -> None:
    # Arrange
    client = _Client()
    embedder = OpenAIEmbedder(_settings(), client=client)
    await embedder.run([_node("hello")], _ctx())

    # Act
    await embedder.aclose()

    # Assert
    assert client.closed is True


def test_build_client_ignores_the_vendor_sdks_own_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — the three variables `AsyncOpenAI` reads for itself when the corresponding
    # argument is `None`. Set here deliberately: passing `None` through is *not* the same as
    # not configuring the endpoint, and an exported `OPENAI_BASE_URL` silently pointing every
    # embedding call at a different server is the one failure this pack cannot detect —
    # vectors of the right width from the wrong space rank confidently against each other.
    monkeypatch.setenv("OPENAI_BASE_URL", "http://someone-elses-server.invalid/v1")
    monkeypatch.setenv("OPENAI_ORG_ID", "org-from-the-shell")
    monkeypatch.setenv("OPENAI_PROJECT_ID", "proj-from-the-shell")

    # Act
    client = build_client(_settings())

    # Assert — `isinstance` first because `build_client` is declared as the narrow
    # `EmbeddingsClient` protocol this pack calls through, and these are SDK attributes.
    assert isinstance(client, AsyncOpenAI)
    assert str(client.base_url).rstrip("/") == VENDOR_BASE_URL.rstrip("/")
    assert client.organization is None
    assert client.project is None
    assert isinstance(client.default_headers["OpenAI-Organization"], Omit)


def test_build_client_uses_the_endpoint_and_account_the_settings_name() -> None:
    # Arrange
    settings = Settings(
        api_key=SecretStr("sk-test"),
        base_url="http://gateway.invalid/v1",
        organization="org-from-the-file",
        project="proj-from-the-file",
    )

    # Act
    client = build_client(settings)

    # Assert
    assert isinstance(client, AsyncOpenAI)
    assert str(client.base_url).rstrip("/") == "http://gateway.invalid/v1"
    assert client.organization == "org-from-the-file"
    assert client.project == "proj-from-the-file"


def test_build_client_leaves_the_sdks_own_timeout_alone_when_none_is_configured() -> None:
    # Arrange — `timeout_seconds` is unset, which must mean "whatever the SDK does", not
    # "no timeout". An explicit `None` *is* honoured by the SDK and httpx reads it as "wait
    # forever", so a stalled connection during `weft index` would hang the run with nothing
    # in a log — and `APITimeoutError`, which `_TRANSIENT` classifies, could never be raised.
    settings = _settings()

    # Act
    client = build_client(settings)

    # Assert
    assert isinstance(client, AsyncOpenAI)
    assert client.timeout is not None


def test_build_client_uses_a_configured_timeout() -> None:
    # Arrange
    settings = Settings(api_key=SecretStr("sk-test"), timeout_seconds=12.5)

    # Act
    client = build_client(settings)

    # Assert
    assert isinstance(client, AsyncOpenAI)
    assert client.timeout == 12.5


def test_config_refuses_a_non_positive_dimension() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        OpenAIEmbedderConfig(dimensions=0)


def test_config_refuses_a_non_positive_batch_size() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        OpenAIEmbedderConfig(batch_size=0)


def test_config_refuses_an_unknown_field() -> None:
    # Act / Assert — a knob this pack does not have must not read as one it silently ignores.
    with pytest.raises(ValidationError):
        OpenAIEmbedderConfig.model_validate({"temperature": 0.5})
