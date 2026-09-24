"""Reorders hits by a served cross-encoder, and aborts a run rather than fake an order.

`cross-encoder-rerank` — ledger **41.2**: a TEI-served cross-encoder, refused by name every
way it cannot score honestly.

Specified by `fix-plans/11` `20.6` as corrected at Phase 41's opening: the model is named and
checked against a running [Text Embeddings Inference](
https://github.com/huggingface/text-embeddings-inference) server's `/info` before any score is
trusted; hits below `depth` are dropped, never appended; a request to `/rerank` never exceeds
`/info`'s own `max_client_batch_size`; truncation is sent explicitly rather than left to the
server's own default; the question scored against every passage is `payload.origin`, never a
transform's derivation; and ties in the model's own scores keep the order the passages arrived
in. **A fault of the server raises** rather than returning an unranked list — under
`weft eval experiment` a `Failed` outcome is one silently counted exclusion
(`weft_cli.eval_scoring`), so a stopped server has to abort the run rather than write a record
that looks like every question was simply irrelevant. Only TEI's own 422 — a passage this
server will not tokenize — is a `Failed`, because that is a fact about one question, not
about the server.
"""

import json
from enum import StrEnum
from typing import Any, ClassVar, cast
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel, ConfigDict, Field

from weft_cross_encoder.settings import CrossEncoderSettings
from weft_kernel.context import Context
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.payload import ExtModel, Failed, Outcome, Produced
from weft_retrieve.payload import Passage, Ranking
from weft_store import Scored

#: The name this reranker is registered and selectable under — see `weft_cross_encoder.register`.
NAME = "cross-encoder-rerank"


class TruncationDirection(StrEnum):
    """Which end of an over-long passage TEI trims — `Enum` per this project's own rule."""

    LEFT = "Left"
    RIGHT = "Right"


class CrossEncoderUnreachableError(WeftError):
    """Makes a stopped TEI server abort the run instead of producing an unranked record.

    No TEI server answered at the configured address — a connection failure or a timeout,
    the whole `httpx.TransportError` family. Raised before any score is trusted, on either
    `/info` or `/rerank`.
    """


class CrossEncoderServerError(WeftError):
    """Aborts the run on a server fault, so an outage is not recorded as irrelevant questions.

    TEI answered with a fault: a non-2xx status other than 422, or a `/rerank` response that
    is not exactly one score per passage sent. Never guessed at — a passage list this stage
    cannot vouch for is not returned unranked.
    """


class CrossEncoderModelUnsetError(WeftError):
    """Refuses to rerank against whatever model a TEI server happens to be running.

    `cross-encoder-rerank` was constructed with no `with:` config at all — `model` is
    required and nothing here may assume one.
    """


class CrossEncoderModelMismatchError(WeftError, UnresolvedNameError):
    """The server's `/info` names a different model, or a model that is not a reranker at all.

    Fitness function 12's family: `valid_options` is the one name the server actually serves,
    a typed field rather than only interpolated into the message — see `weft_kernel.errors.
    UnresolvedNameError`'s own docstring for why membership is structural.
    """

    def __init__(self, message: str, *, valid_options: tuple[str, ...]) -> None:
        super().__init__(message, plugin=NAME)
        self.valid_options = valid_options


class CrossEncoderRerankConfig(BaseModel):
    """Which model the TEI server must be serving, how deep to rerank, and how to truncate.

    `model` is the one field this pack cannot default — see `CrossEncoderModelUnsetError` — because
    assuming one would score every passage against a server that may be running anything at all.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str = Field(min_length=1)
    depth: int = Field(default=50, ge=1)
    truncate: bool = False
    truncation_direction: TruncationDirection = TruncationDirection.RIGHT
    raw_scores: bool = False


class CrossEncoderRanking(ExtModel):
    """What `CrossEncoderRerank` did to one `Ranking`, attached under its own namespace.

    Rides `Ranking.ext`, never a `Node` — not registered with `weft_store.register_ext_model`,
    the same reading `weft_retrieve.anchor_promote.AnchorPromotion`'s own docstring gives for a
    record that never crosses the arity reduction onto a stored payload.
    """

    __namespace__ = "weft-cross-encoder-rerank"
    __schema_version__ = "1"

    #: The served name that matched `config.model` — never the raw `model_id`, which may be a
    #: filesystem path a server was launched with (`--model-id`), not a name anyone else uses.
    model: str
    #: `/info`'s own `model_id`, kept separate from `model` for exactly that reason.
    loaded_from: str
    scored: int
    dropped: int
    requests: int
    truncate: bool
    max_input_length: int | None
    #: `/info`'s `model_dtype`. The same weights served in float16 and float32 score differently,
    #: and a Metal build of TEI defaults to float16 where its CPU image serves float32 (`L28.5`).
    model_dtype: str | None = None

    produced_by: ClassVar[str] = NAME

    def explained(self) -> str:
        """The one-line sentence `weft_cli.explain.record_lines` prints under `--explain`."""
        request_word = "request" if self.requests == 1 else "requests"
        truncate_word = "on" if self.truncate else "off"
        return (
            f"model {self.model}, scored {self.scored}, dropped {self.dropped}, "
            f"{self.requests} {request_word}, truncate {truncate_word}, "
            f"dtype {self.model_dtype or 'unreported'}"
        )


class _RejectedError(Exception):
    """A TEI 422 on `/rerank` — one question's own refusal, converted to `Failed` in `run`.

    Never a `WeftError`: a 422 is not a fault of the server, and `run` never lets this escape
    its own `try` — it exists purely so a rejection found while iterating several batches does
    not need its own threaded return value.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _error_detail(response: httpx.Response) -> str:
    """The server's own `error` field, when the body is JSON and has one; `""` otherwise."""
    try:
        body = response.json()
    except json.JSONDecodeError:
        return ""
    if isinstance(body, dict):
        error = cast("dict[str, Any]", body).get("error")
        if isinstance(error, str):
            return error
    return ""


def _server_error(url: str, path: str, response: httpx.Response) -> CrossEncoderServerError:
    detail = _error_detail(response)
    message = f"'{NAME}': {urljoin(url, path)} answered {response.status_code}"
    if detail:
        message = f"{message}: {detail}"
    return CrossEncoderServerError(message, plugin=NAME)


def _batch_scores(url: str, raw_entries: Any, sent: int) -> dict[int, float]:
    """Validate one `/rerank` answer and return its scores keyed by in-batch index.

    Raises:
        CrossEncoderServerError: The answer is not one score per passage sent.
    """
    if not isinstance(raw_entries, list):
        raise CrossEncoderServerError(
            f"'{NAME}': {urljoin(url, '/rerank')} did not answer one score per passage "
            f"— sent {sent}, scored 0.",
            plugin=NAME,
        )
    entries = cast("list[Any]", raw_entries)
    if len(entries) != sent:
        raise CrossEncoderServerError(
            f"'{NAME}': {urljoin(url, '/rerank')} did not answer one score per passage "
            f"— sent {sent}, scored {len(entries)}.",
            plugin=NAME,
        )
    scores: dict[int, float] = {}
    for entry in entries:
        index = cast("dict[str, Any]", entry).get("index") if isinstance(entry, dict) else None
        if not isinstance(index, int) or not (0 <= index < sent) or index in scores:
            raise CrossEncoderServerError(
                f"'{NAME}': {urljoin(url, '/rerank')} did not answer one score per "
                "passage — a response index was out of range or repeated.",
                plugin=NAME,
            )
        scores[index] = float(cast("dict[str, Any]", entry)["score"])
    return scores


class CrossEncoderRerank:
    """Rescores a `Ranking`'s hits against the question through a TEI server.

    Satisfies `weft_retrieve.contract.Reranker` structurally.

    `cost_bound = (0, 0)`: this stage calls no LLM — it makes one HTTP round trip per batch to
    a scoring server, which is neither a model call nor its absence in the sense `cost_bound`
    tracks.
    """

    score_semantics: ClassVar[str] = (
        "the served model's own relevance score for (question, passage) — a probability "
        "unless raw_scores is set, and not comparable across two different served models"
    )
    config_model: ClassVar[type[CrossEncoderRerankConfig]] = CrossEncoderRerankConfig
    cost_bound: ClassVar[tuple[int, int]] = (0, 0)

    def __init__(
        self,
        settings: CrossEncoderSettings,
        config: CrossEncoderRerankConfig | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if config is None:
            raise CrossEncoderModelUnsetError(
                f"'{NAME}' needs `model:` in its `with:` block, the reranker the TEI server "
                "serves (for example BAAI/bge-reranker-v2-m3). No model is assumed.",
                plugin=NAME,
            )
        self._settings = settings
        self._config = config
        self._transport = transport

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Ranking]:
        """Score `payload.hits[:depth]` against `payload.origin` through the configured server.

        Every other hit is dropped, never appended. `origin`, `contributors` and `note` pass
        through untouched, and every other `ext` entry is carried alongside this stage's own
        `CrossEncoderRanking` record.
        """
        del ctx
        if not payload.hits:
            return Produced(value=payload)

        config = self._config
        url = self._settings.url
        async with httpx.AsyncClient(
            base_url=url, timeout=self._settings.timeout_seconds, transport=self._transport
        ) as client:
            info = await self._fetch_info(client)
            served_model_name = info.get("served_model_name")
            served = str(served_model_name) if served_model_name else str(info.get("model_id"))
            model_type = info.get("model_type")
            model_type_map = (
                cast("dict[str, Any]", model_type) if isinstance(model_type, dict) else None
            )
            has_reranker = model_type_map is not None and "reranker" in model_type_map
            if served != config.model or not has_reranker:
                kind = next(iter(model_type_map), "unknown") if model_type_map else "unknown"
                raise CrossEncoderModelMismatchError(
                    f"'{NAME}' is configured for '{config.model}', but {url} serves "
                    f"'{served}' ({kind}).",
                    valid_options=(served,),
                )

            loaded_from = str(info.get("model_id", ""))
            max_input_length = info.get("max_input_length")

            hits = payload.hits[: config.depth]
            dropped = len(payload.hits) - len(hits)
            texts = [hit.node.content for hit in hits]
            max_batch = info.get("max_client_batch_size") or len(texts)

            try:
                scores, requests = await self._score(
                    client, url, payload.origin.text, texts, max_batch, config
                )
            except _RejectedError as rejected:
                return Failed(reason=rejected.reason)

        order = sorted(range(len(hits)), key=lambda index: (-scores[index], index))
        promoted = tuple(
            Passage(
                scored=Scored(value=hits[index].node, score=scores[index]),
                rank=rank,
                retrieved_by=hits[index].retrieved_by,
                label=hits[index].label,
            )
            for rank, index in enumerate(order)
        )
        record = CrossEncoderRanking(
            model=config.model,
            loaded_from=loaded_from,
            scored=len(hits),
            dropped=dropped,
            requests=requests,
            truncate=config.truncate,
            max_input_length=max_input_length,
            model_dtype=info.get("model_dtype"),
        )
        return Produced(
            value=payload.model_copy(
                update={
                    "hits": promoted,
                    "ext": {**payload.ext, CrossEncoderRanking.__namespace__: record},
                }
            )
        )

    async def _fetch_info(self, client: httpx.AsyncClient) -> dict[str, Any]:
        response = await self._request(client, "GET", "/info")
        if not response.is_success:
            raise _server_error(self._settings.url, "/info", response)
        return response.json()

    async def _score(
        self,
        client: httpx.AsyncClient,
        url: str,
        query: str,
        texts: list[str],
        max_batch: int,
        config: CrossEncoderRerankConfig,
    ) -> tuple[list[float], int]:
        collected: dict[int, float] = {}
        requests = 0
        for start in range(0, len(texts), max_batch):
            slice_texts = texts[start : start + max_batch]
            body = {
                "query": query,
                "texts": slice_texts,
                "truncate": config.truncate,
                "truncation_direction": config.truncation_direction.value,
                "raw_scores": config.raw_scores,
                "return_text": False,
            }
            requests += 1
            response = await self._request(client, "POST", "/rerank", json=body)
            if response.status_code == 422:
                raise _RejectedError(
                    _error_detail(response) or f"{urljoin(url, '/rerank')} refused input (422)"
                )
            if not response.is_success:
                raise _server_error(url, "/rerank", response)
            batch = _batch_scores(url, response.json(), len(slice_texts))
            collected.update({start + index: score for index, score in batch.items()})
        return [collected[position] for position in range(len(texts))], requests

    async def _request(
        self, client: httpx.AsyncClient, method: str, path: str, **kwargs: Any
    ) -> httpx.Response:
        try:
            return await client.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            raise CrossEncoderUnreachableError(
                f"'{NAME}' could not reach {urljoin(self._settings.url, path)} "
                f"({type(exc).__name__}). Start the TEI server, or point "
                "[packs.cross-encoder] url at the one that is running.",
                plugin=NAME,
            ) from exc


__all__ = [
    "NAME",
    "CrossEncoderModelMismatchError",
    "CrossEncoderModelUnsetError",
    "CrossEncoderRanking",
    "CrossEncoderRerank",
    "CrossEncoderRerankConfig",
    "CrossEncoderServerError",
    "CrossEncoderUnreachableError",
    "TruncationDirection",
]
