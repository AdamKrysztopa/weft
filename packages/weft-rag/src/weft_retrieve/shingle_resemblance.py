"""`shingle-resemblance` — drops a passage whose w-shingle resemblance to a higher-ranked
**kept** passage meets a threshold. `Reranker`.

Andrei Z. Broder, "On the resemblance and containment of documents", *Compression and
Complexity of Sequences 1997*, Positano, IEEE, pp. 21-29 — the resemblance of two documents
A and B, `r_w(A,B) = |S(A,w) ∩ S(B,w)| / |S(A,w) ∪ S(B,w)|`, over their sets of contiguous
w-token shingles `S(·,w)`. This module computes exactly that measure, exactly, over every
pair a higher-ranked kept passage and a candidate form, and drops the candidate the moment
one such pair meets the configured threshold — a near-duplicate filter for a `Ranking`,
named for the measure it computes rather than for the purpose it is put to, so an
embedding-based near-duplicate filter is free to keep a name of its own.

**Both defaults are quoted at the value they carry, not derived.** `threshold = 0.5`: "We
calculated our clusters based on a 50% resemblance." (Andrei Z. Broder, Steven C. Glassman,
Mark S. Manasse, Geoffrey Zweig, "Syntactic clustering of the Web", *Computer Networks and
ISDN Systems* 29, WWW6 1997, p. 1164.) `shingle_size = 10`: "The shingle size w is 10."
(same paper, p. 1159) — stated there with no rationale of its own, and Broder 1997 p. 4
argues only a trade-off ("a larger size ... is possibly over-sensitive to small
alterations") rather than a value, so `10` is the one traceable default here, not a derived
one.

**Fidelity.** Faithful to the measure Broder 1997 defines; simplified against the sketch —
no min-hashing, no fixed-size signature, exact sets throughout, which a reranking-sized
list of passages can afford where a web-scale corpus could not. Shingles are word shingles
over casefolded Unicode tokens (`re.findall(r"\\w+", text.casefold())`), not the paper's
own tokenisation, because Weft's inputs are passages already segmented for retrieval rather
than raw web documents.
"""

import re
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_retrieve.payload import Passage, Ranking
from weft_store.contract import Scored

#: The name this reranker is registered and selectable under — see `weft_retrieve.register`.
NAME = "shingle-resemblance"

#: A word token: a maximal run of Unicode word characters. `str.casefold` first, so a
#: passage's case never changes which shingles it produces; `\\w` is Unicode-aware for
#: `str`, so `jaźń` stays one token rather than splitting at its diacritics.
_TOKEN: re.Pattern[str] = re.compile(r"\w+")


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(_TOKEN.findall(text.casefold()))


def _shingles(tokens: tuple[str, ...], *, w: int) -> frozenset[tuple[str, ...]]:
    """`tokens`' set of contiguous `w`-token shingles.

    A passage with fewer than `w` tokens but at least one is one shingle: its whole token
    tuple — the paper's sketch has no such case because a signature is fixed-size
    regardless, but an exact set has to say what a short passage's shingle set *is*, and
    the whole passage standing in for the window it cannot fill is the reading that keeps
    "no tokens at all" as the only genuinely empty case. A passage with no tokens has no
    shingle at all, and resembles nothing.
    """
    if not tokens:
        return frozenset()
    if len(tokens) < w:
        return frozenset({tokens})
    return frozenset(tokens[start : start + w] for start in range(len(tokens) - w + 1))


def _resemblance(a: frozenset[tuple[str, ...]], b: frozenset[tuple[str, ...]]) -> float:
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


class ShingleResemblanceConfig(BaseModel):
    """`ShingleResemblance`'s `with:` config.

    Every field has a default, per this pack's own rule — both quoted at the source that fixes them
    in the module docstring above.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    threshold: float = Field(default=0.5, gt=0, le=1)
    shingle_size: int = Field(default=10, ge=1)


class ShingleResemblance:
    """Drops any passage whose resemblance to a higher-ranked **kept** passage meets the threshold.

    Satisfies `weft_retrieve.contract.Reranker` structurally.

    `cost_bound = (0, 0)`: resemblance is computed over token sets already carried on each
    passage's own content, with no service resolved and no model called — the identical
    reading `weft_retrieve.vector_top_k`'s own module docstring gives for a plugin whose
    real cost is neither a store round trip nor its absence.

    **Compared only against what survived, never against everything ranked above it.**
    A passage dropped as a near-duplicate of something already dropped would, if compared
    against the raw incoming order instead, be judged by a passage no reader will ever see
    — `weft_retrieve.collapse`'s own precedent for "the group a hit joins is decided by what
    is still standing," applied here to a running set of kept shingle sets rather than a
    parent id.
    """

    config_model: ClassVar[type[ShingleResemblanceConfig]] = ShingleResemblanceConfig
    cost_bound: ClassVar[tuple[int, int]] = (0, 0)

    def __init__(self, config: ShingleResemblanceConfig | None = None) -> None:
        self._config = config if config is not None else ShingleResemblanceConfig()

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Ranking]:
        """Walk `payload.hits` in incoming order, keeping a hit unless its resemblance to
        any already-kept hit meets the threshold. Survivors keep their score and
        `retrieved_by`; `rank` is renumbered contiguously over what survives.

        The emptiness rule: no hits at all passes through unchanged, the same reading every
        other `Reranker` in this pack gives it.
        """
        del ctx
        if not payload.hits:
            return Produced(value=payload)

        w = self._config.shingle_size
        threshold = self._config.threshold
        kept: list[Passage] = []
        kept_shingles: list[frozenset[tuple[str, ...]]] = []
        for passage in payload.hits:
            shingles = _shingles(_tokens(passage.node.content), w=w)
            if any(_resemblance(shingles, other) >= threshold for other in kept_shingles):
                continue
            kept.append(passage)
            kept_shingles.append(shingles)

        hits = tuple(
            Passage(
                scored=Scored(value=passage.node, score=passage.score),
                rank=rank,
                retrieved_by=passage.retrieved_by,
                label=passage.label,
            )
            for rank, passage in enumerate(kept)
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
