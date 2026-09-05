"""`openai` — an `Embedder` whose vectors carry meaning, over OpenAI's embeddings API.

The counterpart to `weft_embed.hash_embedder.HashEmbedder`, which is
deterministic and says of itself, plainly, that it carries no semantic
understanding whatsoever. Both are registered under the one `Embedder`
contract `weft-embed` publishes, under two names, so which one runs is the
`use:` field of a pipeline document — or, for `weft index` and `weft ask`
until a document reaches them, `[services] embed` in `weft.toml`. Changing
which embedder a corpus is indexed with is that edit and nothing else: no
edit to a package, no edit to core, no reinstall.

**The difference is measured, not asserted.** Against
`text-embedding-3-small`, "a cat sleeping on a warm windowsill" and "a kitten
napping in the sun" score 0.62 cosine, and either against "quarterly
amortisation of intangible assets" scores 0.07. The same three strings
through `HashEmbedder` at the same width score 0.005 and -0.005 — the same
number to within noise, which is exactly what "not a quality component"
means when you put a number on it. `tests/integration/test_openai_embedder.py`
re-measures that separation against the live API and skips, with a reason,
when no credential is present.

**The credential is a pack setting and it has a default, deliberately.** See
`weft_openai.Settings`: a required field would make `register()` raise on a
machine with no key, the pack would report `failed`, and this plugin would
vanish from the registry and from every check that walks it without one test
going red. So a missing key fails **here**, on the first call that would have
reached the network, naming the `weft.toml` line that supplies one.

**Failure is raised, never returned as `Failed`.** Every other stage in this
tree answers `Failed` for input it could not handle, and `weft_kernel.fallback`
walks to the next backend on exactly that outcome. That is right for a parser
— a PDF one library cannot read another may — and wrong here: a chain that
fell through from a semantic embedder to a deterministic one would write
vectors from two unrelated spaces into one index, and an index like that does
not crash. It answers plausibly, against nonsense, which is the failure this
project exists to remove. An API that refused the call is a fact about the
run, not about the batch, so it leaves as a `WeftError` the seam attributes
and the caller sees.

**The client is built off the event loop, and that is measured too.**
Constructing `AsyncOpenAI` inside the registration seam's blocking guard
raises `BlockingCallError` — it loads a CA bundle through `open()` while
setting up its TLS context. The request itself is clean (the live test drives
a real call inside the guard), so this is one `asyncio.to_thread` at
construction, once per stage instance, and nothing else.
"""

import asyncio
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, ClassVar, Protocol

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    Omit,
    RateLimitError,
    not_given,
    omit,
)
from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import Node, NothingToProduce, Outcome, Produced, Vector

if TYPE_CHECKING:
    from weft_openai.settings import Settings

#: The name this embedder is registered and selected under — see `weft_openai.register`.
NAME = "openai"

#: The default model, and the one every number in this module's docstring was measured
#: against. Small, current, and 1536 components wide without being asked.
DEFAULT_MODEL = "text-embedding-3-small"

#: The vendor's own endpoint, restated here because the SDK's way of asking for it is to be
#: handed `None` — and `None` is also what it takes as licence to read `OPENAI_BASE_URL` from
#: the environment. See `build_client`.
VENDOR_BASE_URL = "https://api.openai.com/v1"

#: How many texts go in one request when nothing says otherwise. The API takes an array;
#: this is only how large an array this pack is willing to build without being told.
_DEFAULT_BATCH_SIZE = 128

#: The API errors worth trying again, as opposed to those that will refuse identically
#: forever. `WeftError.transient` is the kernel's own marker for exactly this distinction
#: and the kernel runs no retry engine, so the judgement has to come from the pack that
#: knows which failures its vendor retries.
_TRANSIENT = (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)


class MissingApiKeyError(WeftError):
    """No credential is configured, and something asked this embedder to embed.

    Raised at use rather than at registration — see the module docstring. The
    message names the `weft.toml` line that fixes it, because "authentication
    failed" from a vendor SDK tells an operator that a key is wrong and
    nothing about where this project reads one from.
    """


class UnembeddableNodeError(WeftError):
    """A node reached this embedder with no text in it, and the API refuses empty input.

    Named by node id rather than relayed: the API's own answer to an empty
    string is `'$.input' is invalid`, which identifies neither the node nor
    the document it came from, and a batch of 128 chunks is a poor place to
    start guessing. `HashEmbedder` hashes an empty string happily, so this is
    a real behavioural difference between two plugins of one contract, stated
    here rather than discovered.
    """


class EmbeddingRequestFailedError(WeftError):
    """The API refused, or could not be reached. `transient` says which.

    Deliberately one class and not a taxonomy: the fourteen-class `LLMError`
    hierarchy is `weft-llm`'s, one task later, and it exists because a
    generation cascade has to *decide* between tiers on the class it caught.
    Nothing decides anything on an embedding failure except whether to try
    again, which is what `transient` already answers.
    """


class OpenAIEmbedderConfig(BaseModel):
    """`OpenAIEmbedder`'s `with:` configuration — the knobs the API has and an operator wants.

    **Every default is the API's own**, so a pipeline that sets nothing gets
    what the vendor's documentation describes rather than this pack's opinion
    of it. `dimensions` unset means the model's native width, which is 1536
    for `text-embedding-3-small`; setting it shortens the vector at the
    model's own hands (the `-3` models are trained so a truncated vector is
    still usable), which is a real trade of recall against index size and
    therefore configuration rather than a decision compiled in here.

    Two parameters the endpoint accepts are **deliberately absent**, so the
    omissions read as decisions:

    - **`encoding_format`** chooses how the vector crosses the wire. The SDK
      decodes both spellings to the same list of floats, so it changes
      nothing an operator can observe about a Weft index.
    - **`user`** identifies an end user to the vendor's abuse monitoring.
      `weft_kernel.context.Context` carries a tenant and a run, neither of
      which is a person, and inventing one to fill this field would be
      claiming something Weft does not know.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str = Field(default=DEFAULT_MODEL, min_length=1)
    #: `None` = whatever the model returns natively. See the class docstring.
    dimensions: int | None = Field(default=None, ge=1)
    batch_size: int = Field(default=_DEFAULT_BATCH_SIZE, ge=1)


class EmbeddingItem(Protocol):
    """One element of the API's `data` array — the two fields this pack reads."""

    @property
    def index(self) -> int: ...

    @property
    def embedding(self) -> Sequence[float]: ...


class EmbeddingBatch(Protocol):
    """What one embeddings call answers."""

    @property
    def data(self) -> Sequence[EmbeddingItem]: ...


class EmbeddingsResource(Protocol):
    """The one endpoint this pack calls, declared as the shape it calls rather than imported.

    `openai.AsyncOpenAI` satisfies this and its sibling `EmbeddingsClient`
    structurally, and the type checker proves it at `build_client` below —
    which is the point. The claim "this module sends exactly these three
    parameters and reads exactly these two fields back" is checked against the
    real SDK rather than written in a comment that would age, and a test can
    drive the embedder with a stand-in of the same shape without a network, a
    credential, or a mock of a class it does not own.
    """

    async def create(
        self, *, input: list[str], model: str, dimensions: int | Omit = omit
    ) -> EmbeddingBatch: ...


class EmbeddingsClient(Protocol):
    """The client this pack holds: one resource, and a way to give its sockets back."""

    @property
    def embeddings(self) -> EmbeddingsResource: ...

    async def close(self) -> None: ...


class OpenAIEmbedder:
    """Attaches a model-produced `Vector` to every node it is handed.

    Satisfies `weft_embed.contract.Embedder` structurally: this class never
    imports it, the same path every third-party embedder pack takes.

    `client` is a seam for a test, not a configuration surface — nothing in a
    pipeline document or a settings block can reach it, and the pipeline never
    passes one. Left unset, the real client is built on first use.
    """

    config_model: ClassVar[type[OpenAIEmbedderConfig]] = OpenAIEmbedderConfig

    def __init__(
        self,
        settings: "Settings",
        config: OpenAIEmbedderConfig | None = None,
        *,
        client: EmbeddingsClient | None = None,
    ) -> None:
        self._settings = settings
        self._config = config if config is not None else OpenAIEmbedderConfig()
        self._client = client

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx  # no service or locale this stage needs
        if not payload:
            return NothingToProduce(reason="no nodes to embed")
        texts = [_text_of(node) for node in payload]
        client = await self._connected()
        vectors: list[Vector] = []
        for batch in _batched(texts, self._config.batch_size):
            vectors.extend(await self._embed(client, batch))
        # `strict` as a backstop to `_embed`'s own per-request index check: one vector per
        # node, in order, is the whole contract of this stage, and a batching bug here would
        # otherwise drop the last node's embedding rather than say anything.
        embedded = [node.with_embedding(v) for node, v in zip(payload, vectors, strict=True)]
        return Produced(value=embedded)

    async def aclose(self) -> None:
        """Release the client's connections. Read defensively by `weft_cli.ingest`."""
        if self._client is not None:
            await self._client.close()

    async def _embed(self, client: EmbeddingsClient, texts: Sequence[str]) -> list[Vector]:
        """One request, and its vectors back in the order the texts went out.

        Ordered by each item's own `index` rather than by arrival: the
        response is documented as an array of objects that each carry one, and
        a pack that zipped arrival order onto its nodes would silently attach
        one chunk's meaning to another chunk's text — a corpus that retrieves
        confidently and wrongly, with nothing to see in a log.
        """
        config = self._config
        dimensions: int | Omit = config.dimensions if config.dimensions is not None else omit
        try:
            batch = await client.embeddings.create(
                input=list(texts), model=config.model, dimensions=dimensions
            )
        except APIError as exc:
            raise EmbeddingRequestFailedError(
                f"the embeddings API refused a batch of {len(texts)} for model "
                f"'{config.model}': {exc}",
                transient=isinstance(exc, _TRANSIENT),
            ) from exc
        by_index = {item.index: item for item in batch.data}
        expected = list(range(len(texts)))
        if sorted(by_index) != expected:
            raise EmbeddingRequestFailedError(
                f"the embeddings API answered {len(batch.data)} vector(s) for {len(texts)} "
                f"input(s), indexed {sorted(by_index)} — one vector per input, indexed from "
                f"zero, is what this stage pairs onto its nodes, and there is no safe way to "
                f"guess which node a missing or unexpected index belonged to."
            )
        return [Vector(values=tuple(by_index[position].embedding)) for position in expected]

    async def _connected(self) -> EmbeddingsClient:
        """The client, built on first use — off the loop, and refusing without a credential."""
        if self._client is not None:
            return self._client
        settings = self._settings
        if not settings.api_key.get_secret_value():
            raise MissingApiKeyError(
                "no OpenAI credential is configured, so the 'openai' embedder has nothing to "
                'authenticate with. Add `[packs.openai] api_key = "${env:OPENAI_API_KEY}"` '
                "to weft.toml — the settings loader interpolates `${env:...}`, so the key stays "
                "in the environment and out of the file."
            )
        self._client = await asyncio.to_thread(build_client, settings)
        return self._client


def build_client(settings: "Settings") -> EmbeddingsClient:
    """A real `AsyncOpenAI`, from pack settings alone.

    Public rather than private because the claim below — that this file, and
    not the ambient environment, decides where a request goes — is only worth
    making if something checks it, and the check is a unit test that builds a
    client with the vendor's own variables exported. A caller embedding
    through Weft never needs this; `OpenAIEmbedder` builds its own.

    Nothing here is left to the SDK to infer, because the SDK infers from the
    environment: `api_key`, `base_url`, `organization` and `project` each fall
    back to a variable (`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_ORG_ID`,
    `OPENAI_PROJECT_ID`) when the argument is `None`. That would be a second
    configuration source nothing in this project declares — a project whose
    `weft.toml` says nothing would work on one machine and fail on another,
    and the message `MissingApiKeyError` prints would name a file that was
    never consulted.

    **`None` is not "unset" to this SDK; it is a value.** Two repairs for one
    reviewer finding each, both measured against the installed `openai` rather
    than reasoned about:

    - `base_url=None` is exactly what triggers the `OPENAI_BASE_URL` read, so
      the unset case passes `VENDOR_BASE_URL` explicitly. An exported
      `OPENAI_BASE_URL` — the ordinary way to talk to a local or proxied
      compatible server — would otherwise redirect every call to a different
      model, and vectors of the right width from the wrong space do not
      crash a store: they rank confidently against each other.
      `organization` and `project` take the same treatment, and since the
      constructor has no way to say "no organization", they are put back
      afterwards: both are plain attributes the SDK's own `default_headers`
      reads per request, and `None` there means the header is omitted.
    - `timeout=None` is *honoured* and becomes "wait forever" in httpx. The
      constructor's own default is the `not_given` sentinel, so that is what
      an unset `timeout_seconds` passes: the SDK's real default (a 5s connect
      / 600s read `Timeout`) stays in force. Passed `None`, a stalled
      connection during `weft index` would hang the run with nothing in a log,
      and `APITimeoutError` — which `_TRANSIENT` classifies and
      `manual/troubleshooting.md` promises is marked transient — could never
      be raised at all.
    """
    client = AsyncOpenAI(
        api_key=settings.api_key.get_secret_value(),
        base_url=settings.base_url if settings.base_url is not None else VENDOR_BASE_URL,
        organization=settings.organization,
        project=settings.project,
        timeout=settings.timeout_seconds if settings.timeout_seconds is not None else not_given,
        max_retries=settings.max_retries,
    )
    client.organization = settings.organization
    client.project = settings.project
    return client


def _text_of(node: Node) -> str:
    """`node`'s content, refusing the one input the API has no answer for."""
    if not node.content.strip():
        raise UnembeddableNodeError(
            f"node '{node.id}' has no text to embed, and the embeddings API refuses an "
            f"empty input. Drop empty chunks before this stage, or check the chunker that "
            f"produced it."
        )
    return node.content


def _batched(texts: Sequence[str], size: int) -> Iterator[Sequence[str]]:
    """`texts` in slices of at most `size` — one request each, in order."""
    for start in range(0, len(texts), size):
        yield texts[start : start + size]
