"""`cross-encoder-rerank`, ledger **41.2**: its contract with the TEI server, from `/info` to a 422.

`cross-encoder-rerank` — ledger **41.2**: a TEI-served cross-encoder, refused by name every way
it cannot score honestly.

Specified by `fix-plans/11` `20.6` as corrected at Phase 41's opening (`build-ledger.md` → 41):
the model is named and checked against the server's `/info` before any score; hits below `depth`
are dropped, never appended; a request never exceeds `/info`'s `max_client_batch_size`; truncation
is sent explicitly; the question is `payload.origin`; ties keep input order. **A fault of the
server raises** — under `weft eval experiment` a `Failed` is one counted exclusion, so a stopped
server returned as `Failed` would exclude every question and still write a record (`L28.1`) — and
only a per-question refusal (TEI's 422) is a `Failed`.

TEI is doubled with `httpx.MockTransport`; one test reaches a closed port through the real client.
"""

from __future__ import annotations

import json
import socket
from collections.abc import Callable
from typing import Any, ClassVar

import httpx
import pytest
from pydantic import ValidationError

from weft_cross_encoder import DISCLOSURE, register
from weft_cross_encoder.rerank import (
    NAME,
    CrossEncoderModelMismatchError,
    CrossEncoderModelUnsetError,
    CrossEncoderRanking,
    CrossEncoderRerank,
    CrossEncoderRerankConfig,
    CrossEncoderServerError,
    CrossEncoderUnreachableError,
    TruncationDirection,
)
from weft_cross_encoder.settings import CrossEncoderSettings
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.payload import ExtModel, Failed, MediaType, Node, Produced
from weft_kernel.registry import Registry
from weft_retrieve import Reranker
from weft_retrieve.payload import Passage, Query, Ranking
from weft_store import Scored

_MODEL = "BAAI/bge-reranker-v2-m3"
_URL = "http://tei.test:8080"


class _Upstream(ExtModel):
    """An entry an earlier stage left on the ranking, which reranking must carry untouched."""

    __namespace__: ClassVar[str] = "test-upstream"
    __schema_version__: ClassVar[str] = "1"

    said: str


def _ctx() -> Context:
    return Context(tenant_id="t", run_id="r", trace_id="tr", locale="en")


def _hit(words: str, score: float, rank: int, *, label: str = "") -> Passage:
    node = Node.synthetic(content=words, media_type=MediaType.TEXT, reason="fixture")
    return Passage(
        scored=Scored(value=node, score=score), rank=rank, retrieved_by="vector-top-k", label=label
    )


def _ranking(question: str, hits: tuple[Passage, ...]) -> Ranking:
    return Ranking(
        origin=Query(text=question),
        hits=hits,
        contributors=("vector-top-k",),
        note="an upstream note",
        ext={_Upstream.__namespace__: _Upstream(said="kept")},
    )


def _info(
    *,
    model: str = _MODEL,
    kind: str = "reranker",
    batch: int = 32,
    max_input: int = 8192,
    model_id: str | None = None,
) -> dict[str, Any]:
    return {
        "model_id": model if model_id is None else model_id,
        "served_model_name": model,
        "model_type": {kind: {"id2label": {"0": "LABEL_0"}, "label2id": {"LABEL_0": 0}}},
        "max_input_length": max_input,
        "max_client_batch_size": batch,
        "model_dtype": "float16",
        "version": "1.9.4",
    }


class _Tei:
    """A TEI double: `/info` from `info`, `/rerank` scored by `score(text)`, every call recorded."""

    def __init__(
        self,
        score: Callable[[str], float],
        *,
        info: dict[str, Any] | None = None,
        rerank_status: int = 200,
        rerank_body: Any = None,
    ) -> None:
        self.score = score
        self.info = info if info is not None else _info()
        self.rerank_status = rerank_status
        self.rerank_body = rerank_body
        self.rerank_requests: list[dict[str, Any]] = []
        self.paths: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        if request.url.path == "/info":
            return httpx.Response(200, json=self.info)
        body = json.loads(request.content)
        self.rerank_requests.append(body)
        if self.rerank_status != 200 or self.rerank_body is not None:
            return httpx.Response(self.rerank_status, json=self.rerank_body)
        scored = [
            {"index": index, "score": self.score(text)} for index, text in enumerate(body["texts"])
        ]
        return httpx.Response(200, json=sorted(scored, key=lambda row: -row["score"]))


def _plugin(tei: _Tei, **config: Any) -> CrossEncoderRerank:
    return CrossEncoderRerank(
        CrossEncoderSettings(url=_URL),
        CrossEncoderRerankConfig(model=_MODEL, **config),
        transport=httpx.MockTransport(tei),
    )


def _by_number(text: str) -> float:
    """Scores `"passage 7"` as 7.0, so a test can say which passage the model prefers."""
    return float(text.rsplit(" ", 1)[1])


async def test_hits_are_reordered_by_the_models_scores_with_ties_in_input_order() -> None:
    # Arrange — p1 and p3 tie on the model's score; p1 came first, so it stays first.
    hits = (
        _hit("passage 1", 0.9, 0, label="a"),
        _hit("passage 5", 0.8, 1),
        _hit("passage 1", 0.7, 2),
        _hit("passage 9", 0.6, 3),
    )
    tei = _Tei(_by_number)

    # Act
    outcome = await _plugin(tei).run(_ranking("which passage?", hits), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    out = outcome.value.hits
    assert [hit.node.id for hit in out] == [hits[i].node.id for i in (3, 1, 0, 2)]
    assert [hit.score for hit in out] == [9.0, 5.0, 1.0, 1.0]
    assert [hit.rank for hit in out] == [0, 1, 2, 3]
    assert out[2].label == "a"
    assert {hit.retrieved_by for hit in out} == {"vector-top-k"}


async def test_the_question_is_the_rankings_origin_and_truncation_is_always_sent() -> None:
    # Arrange
    tei = _Tei(_by_number)
    plugin = _plugin(tei, truncate=True, truncation_direction=TruncationDirection.LEFT)

    # Act
    await plugin.run(_ranking("the user's own words", (_hit("passage 2", 0.5, 0),)), _ctx())

    # Assert
    (request,) = tei.rerank_requests
    assert request["query"] == "the user's own words"
    assert request["texts"] == ["passage 2"]
    assert (request["truncate"], request["truncation_direction"]) == (True, "Left")
    assert request["raw_scores"] is False


async def test_hits_below_depth_are_dropped_never_appended_and_never_sent() -> None:
    # Arrange
    hits = tuple(_hit(f"passage {i}", 1.0 - i / 10, i) for i in range(5))
    tei = _Tei(_by_number)

    # Act
    outcome = await _plugin(tei, depth=3).run(_ranking("q", hits), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert [hit.node.id for hit in outcome.value.hits] == [hits[i].node.id for i in (2, 1, 0)]
    assert tei.rerank_requests[0]["texts"] == ["passage 0", "passage 1", "passage 2"]
    record = outcome.value.ext[CrossEncoderRanking.__namespace__]
    assert isinstance(record, CrossEncoderRanking)
    assert (record.scored, record.dropped) == (3, 2)


async def test_a_pool_wider_than_a_client_batch_is_sent_in_slices_and_merged_by_index() -> None:
    # Arrange — 50 hits, 32 per request: the second slice's indices restart at 0 on the wire.
    hits = tuple(_hit(f"passage {i}", 1.0 - i / 100, i) for i in range(50))
    tei = _Tei(_by_number, info=_info(batch=32))

    # Act
    outcome = await _plugin(tei).run(_ranking("q", hits), _ctx())

    # Assert
    assert sorted(len(request["texts"]) for request in tei.rerank_requests) == [18, 32]
    assert isinstance(outcome, Produced)
    assert [hit.node.id for hit in outcome.value.hits] == [
        hits[i].node.id for i in range(49, -1, -1)
    ]
    assert all(hit.score == float(hit.node.content.rsplit(" ", 1)[1]) for hit in outcome.value.hits)


async def test_the_record_names_the_served_model_and_every_other_ext_entry_is_carried() -> None:
    # Arrange
    tei = _Tei(_by_number)
    ranking = _ranking("q", (_hit("passage 1", 0.5, 0), _hit("passage 2", 0.4, 1)))

    # Act
    outcome = await _plugin(tei).run(ranking, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    value = outcome.value
    record = value.ext[CrossEncoderRanking.__namespace__]
    assert isinstance(record, CrossEncoderRanking)
    assert record.model == _MODEL
    assert f"model {_MODEL}" in record.explained()
    # L28.5: the served dtype changes the model's numbers, so it is identity, not a detail.
    assert record.model_dtype == "float16"
    assert "dtype float16" in record.explained()
    assert CrossEncoderRanking.produced_by == NAME
    assert value.ext[_Upstream.__namespace__] == _Upstream(said="kept")
    assert (value.origin, value.contributors, value.note) == (
        ranking.origin,
        ranking.contributors,
        ranking.note,
    )


async def test_an_empty_ranking_is_returned_as_it_arrived_without_touching_the_server() -> None:
    # Arrange
    tei = _Tei(_by_number)
    empty = _ranking("q", ())

    # Act
    outcome = await _plugin(tei).run(empty, _ctx())

    # Assert
    assert outcome == Produced(value=empty)
    assert tei.paths == []


@pytest.mark.parametrize(
    "info",
    [_info(model="cross-encoder/ms-marco-MiniLM-L6-v2"), _info(kind="embedding")],
    ids=["another-model", "not-a-reranker"],
)
async def test_a_server_serving_anything_but_the_named_reranker_is_refused_before_any_score(
    info: dict[str, Any],
) -> None:
    # Arrange
    tei = _Tei(_by_number, info=info)

    # Act
    with pytest.raises(CrossEncoderModelMismatchError) as caught:
        await _plugin(tei).run(_ranking("q", (_hit("passage 1", 0.5, 0),)), _ctx())

    # Assert
    assert tei.rerank_requests == []
    assert caught.value.valid_options == (info["served_model_name"],)
    assert _MODEL in str(caught.value)
    assert issubclass(CrossEncoderModelMismatchError, UnresolvedNameError)
    assert issubclass(CrossEncoderModelMismatchError, WeftError)


@pytest.mark.parametrize("status", [413, 424, 429, 503])
async def test_a_server_fault_raises_naming_the_url_and_status_never_an_unranked_list(
    status: int,
) -> None:
    # Arrange
    tei = _Tei(_by_number, rerank_status=status, rerank_body={"error": "no", "error_type": "x"})

    # Act
    with pytest.raises(CrossEncoderServerError) as caught:
        await _plugin(tei).run(_ranking("q", (_hit("passage 1", 0.5, 0),)), _ctx())

    # Assert
    assert _URL in str(caught.value)
    assert str(status) in str(caught.value)


async def test_a_response_that_is_not_one_score_per_offered_passage_raises() -> None:
    # Arrange — two passages offered, one score back.
    tei = _Tei(_by_number, rerank_body=[{"index": 0, "score": 1.0}])

    # Act
    with pytest.raises(CrossEncoderServerError, match="one score per passage"):
        await _plugin(tei).run(
            _ranking("q", (_hit("passage 1", 0.5, 0), _hit("passage 2", 0.4, 1))), _ctx()
        )


async def test_a_passage_the_server_will_not_tokenize_fails_this_question_only() -> None:
    # Arrange — TEI's 422 is about this input, so it is the one per-question refusal.
    body = {
        "error": "Input validation error: inputs must have less than 512 tokens",
        "error_type": "Validation",
    }
    tei = _Tei(_by_number, rerank_status=422, rerank_body=body)

    # Act
    outcome = await _plugin(tei).run(_ranking("q", (_hit("passage 1", 0.5, 0),)), _ctx())

    # Assert
    assert isinstance(outcome, Failed)
    assert "less than 512 tokens" in outcome.reason


async def test_a_server_nobody_is_listening_on_raises_naming_its_url() -> None:
    # Arrange — a port bound and released, so the real client meets a refused connection.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    plugin = CrossEncoderRerank(
        CrossEncoderSettings(url=url, timeout_seconds=2.0), CrossEncoderRerankConfig(model=_MODEL)
    )

    # Act
    with pytest.raises(CrossEncoderUnreachableError) as caught:
        await plugin.run(_ranking("q", (_hit("passage 1", 0.5, 0),)), _ctx())

    # Assert
    assert url in str(caught.value)


def test_the_model_is_required_and_a_stage_with_no_configuration_is_refused_by_name() -> None:
    # Act / Assert
    with pytest.raises(ValidationError, match="model"):
        CrossEncoderRerankConfig.model_validate({})
    with pytest.raises(CrossEncoderModelUnsetError, match="model"):
        CrossEncoderRerank(CrossEncoderSettings(), None)
    with pytest.raises(ValidationError):
        CrossEncoderRerankConfig.model_validate({"model": _MODEL, "depth": 0})


def test_it_is_registered_as_a_reranker_behind_its_own_pack_that_discloses_the_server() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-rag")
    register(registrar, CrossEncoderSettings())
    registrar.commit()

    # Act
    plugin = registry.entry(Reranker, NAME).factory(CrossEncoderRerankConfig(model=_MODEL))

    # Assert
    assert isinstance(plugin, CrossEncoderRerank)
    assert NAME == "cross-encoder-rerank"
    assert CrossEncoderRerank.cost_bound == (0, 0)
    assert isinstance(getattr(CrossEncoderRerank, "score_semantics", None), str)
    assert CrossEncoderSettings().url == "http://localhost:8080"
    assert any("[packs.cross-encoder] url" in entry for entry in DISCLOSURE.network)
    assert {resource.resource for resource in registrar.pipeline_resources} >= {
        "pipelines/cross-encoder-retrieve.yaml",
        "pipelines/cross-encoder-rerank-then-generate.yaml",
    }


async def test_identity_is_the_name_the_server_serves_under_not_where_it_loaded_the_weights() -> (
    None
):
    # Arrange — `--model-id /data/local-bge --served-model-name BAAI/bge-reranker-v2-m3`, as 41.1
    # served it; `/info`'s `model_id` is then a path and `served_model_name` the model's name.
    tei = _Tei(_by_number, info=_info(model_id="/data/local-bge"))

    # Act
    outcome = await _plugin(tei).run(_ranking("q", (_hit("passage 1", 0.5, 0),)), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    record = outcome.value.ext[CrossEncoderRanking.__namespace__]
    assert isinstance(record, CrossEncoderRanking)
    assert (record.model, record.loaded_from) == (_MODEL, "/data/local-bge")
