"""`mmr` — greedy diversity-based reranking. `Reranker`.

Carbonell & Goldstein, "The use of MMR, diversity-based reranking for reordering documents
and producing summaries", SIGIR '98 (Melbourne, Australia, ACM 1-58113-015-5), pp. 335-336:
select, at each step, the unselected passage maximising
`λ·Sim1(d, q) − (1−λ)·max_{d′∈selected} Sim2(d, d′)`, with the max term `0` while nothing is
yet selected. p. 335 prints this bracketed as `Arg max[λ(Sim1(Di,Q) − (1−λ)max Sim2(Di,Dj))]`
— read literally, that single pair of brackets scales the whole difference by `λ`, which
would apply `λ` to the novelty term a second time as `λ(1−λ)`. This is the standard reading
of the formula, not that one: `λ·Sim1 − (1−λ)·max Sim2`, two independently-weighted terms,
and it is what the tests beside this module pin. `relevance_weight` defaults to `0.7` from p.
335's "a larger value of λ (e.g. λ = .7)"; p. 336 records that this choice is not a precise
optimum — "there is no significant statistical difference between the λ=1, λ=.7, and λ=.3
scores" — so the default is the paper's own recommendation, not a measured best.

**Both similarity functions are cosine over the index's own stored embeddings — the paper
leaves `Sim1` and `Sim2` unspecified and names no scale for either.** `Sim1` is the cosine
between the question's own embedding, computed by one call to the run's configured
`Embedder`, and a hit's stored `Node.embedding`; `Sim2` is the cosine between two hits'
stored embeddings. The incoming `Passage.score` is never used as `Sim1`: it may already be a
fused or reranked value on a scale this arithmetic never assumed, so relevance is recomputed
from vectors rather than reused.

A hit that reaches this stage with no stored embedding is refused by name — never treated as
maximally dissimilar (`Sim2 = 0`) or maximally irrelevant, either of which would be a number
nobody measured standing in for one that does not exist.
"""

from collections.abc import Mapping, Sequence
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from weft_embed.contract import Embedder
from weft_kernel.context import Context
from weft_kernel.payload import Failed, NodeId, Outcome, Produced
from weft_retrieve.payload import Passage, Ranking
from weft_retrieve.vector_top_k import embed_query
from weft_store.contract import Scored

#: The name this reranker is registered and selectable under — see `weft_retrieve.register`.
NAME = "mmr"


class MmrConfig(BaseModel):
    """`Mmr`'s `with:` config. Every field has a default, per this pack's own rule.

    `relevance_weight` is `λ` — `1.0` orders purely by relevance to the question, `0.0`
    purely by novelty against what is already selected. `top_n`, when set, stops the greedy
    walk after that many selections rather than reordering every hit; `None` keeps every hit
    and returns it reordered.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    relevance_weight: float = Field(default=0.7, ge=0, le=1)
    top_n: int | None = Field(default=None, ge=1)


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    """Cosine similarity, brute force.

    `weft_store.memory.MemoryStore`'s own helper, written fresh here rather than imported: this pack
    does not reach into a store's private module for arithmetic every store already knows how to do
    internally, and this plugin needs it *between two hits*, a comparison no `NodeStore` method
    offers.
    """
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    magnitude = (sum(a * a for a in left) ** 0.5) * (sum(b * b for b in right) ** 0.5)
    return 0.0 if magnitude == 0.0 else dot / magnitude


def _select(
    hits: Sequence[Passage],
    vectors: Mapping[NodeId, tuple[float, ...]],
    relevance: Mapping[NodeId, float],
    *,
    lam: float,
    limit: int,
) -> list[tuple[Passage, float]]:
    """Greedily pick up to `limit` hits, each maximising relevance minus weighted novelty."""
    remaining = list(hits)
    selected: list[tuple[Passage, float]] = []
    selected_vectors: list[tuple[float, ...]] = []
    while remaining and len(selected) < limit:
        candidates: list[tuple[float, Passage]] = []
        for hit in remaining:
            novelty = max(
                (_cosine(vectors[hit.node.id], other) for other in selected_vectors),
                default=0.0,
            )
            value = lam * relevance[hit.node.id] - (1 - lam) * novelty
            candidates.append((value, hit))
        best_value, best_hit = max(candidates, key=lambda item: (item[0], -item[1].rank))
        remaining.remove(best_hit)
        selected_vectors.append(vectors[best_hit.node.id])
        selected.append((best_hit, best_value))
    return selected


class Mmr:
    """Keep near-duplicate passages from crowding a ranking's top, trading relevance for novelty.

    Greedily reorders a ranking by relevance to the question and novelty against what is
    already chosen. Satisfies `weft_retrieve.contract.Reranker` structurally.

    `score_semantics` states plainly that what this stage emits is not a similarity: it is
    the MMR value — `λ·Sim1 − (1−λ)·max Sim2` — a hit was *selected* with, on a scale a plain
    cosine reader would misread as a similarity score. `cost_bound = (0, 0)`: `run` resolves
    `Embedder`, never an `LLM`-shaped service, and calls it exactly once regardless of how
    many hits arrive — see `weft_retrieve.vector_top_k`'s own module docstring for why a
    class attribute tracking model-call cost reads `(0, 0)` for a plugin whose only service
    call is an embedding.
    """

    score_semantics: ClassVar[str] = (
        "the MMR value the passage was selected with — λ·Sim1(question) minus "
        "(1−λ)·the highest Sim2 against an already-selected passage — never a bare "
        "similarity, and not comparable to a score from a different λ or a different stage"
    )
    config_model: ClassVar[type[MmrConfig]] = MmrConfig
    cost_bound: ClassVar[tuple[int, int]] = (0, 0)

    def __init__(self, config: MmrConfig | None = None) -> None:
        self._config = config if config is not None else MmrConfig()

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Ranking]:
        """Embed the question once, then greedily select by the paper's own criterion.

        **The emptiness rule** — no hits at all returns an empty `Ranking` with no embedding
        call, the same "never asked" fact every contract in `weft_retrieve.contract` states
        for its own position. `origin`, `contributors`, `note` and `ext` all pass through
        unchanged: this stage reorders and rescores, it does not change which retriever fed
        the ranking or manufacture a note an earlier plugin did not already state.

        **A hit with no stored embedding is refused before anything is resolved**, naming
        this plugin and the node it could not score — the "a silent fallback is worse than a
        failure" rule applied to the one input this arithmetic cannot proceed without.
        """
        if not payload.hits:
            return Produced(
                value=Ranking(
                    origin=payload.origin,
                    contributors=payload.contributors,
                    note=payload.note,
                    ext=payload.ext,
                )
            )

        missing = tuple(hit for hit in payload.hits if hit.node.embedding is None)
        if missing:
            ids = ", ".join(hit.node.id for hit in missing)
            return Failed(
                reason=(
                    f"'{NAME}' scores relevance and novelty from stored vectors, and "
                    f"{len(missing)} hit(s) arrived with no stored embedding: {ids}."
                )
            )

        embedder = ctx.require(Embedder)
        query_vector = await embed_query(payload.origin.text, embedder=embedder, ctx=ctx)
        if isinstance(query_vector, Failed):
            return query_vector

        # Total, not partial: `missing` above refused every hit without a vector.
        vectors: dict[NodeId, tuple[float, ...]] = {
            hit.node.id: hit.node.embedding.values
            for hit in payload.hits
            if hit.node.embedding is not None
        }
        lam = self._config.relevance_weight
        relevance = {
            node_id: _cosine(query_vector.values, vector) for node_id, vector in vectors.items()
        }
        limit = self._config.top_n if self._config.top_n is not None else len(payload.hits)
        selected = _select(payload.hits, vectors, relevance, lam=lam, limit=limit)

        hits = tuple(
            Passage(
                scored=Scored(value=hit.node, score=value),
                rank=rank,
                retrieved_by=hit.retrieved_by,
            )
            for rank, (hit, value) in enumerate(selected)
        )
        return Produced(
            value=Ranking(
                origin=payload.origin,
                hits=hits,
                contributors=payload.contributors,
                note=payload.note,
                ext=payload.ext,
            )
        )
