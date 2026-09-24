"""`anchor-promote` — reorders a `Ranking` by the question's own anchors. `Reranker`.

Phase 39 fused a lexical list per anchor with dense and fitted its weight to about zero
(`39.1`). This is that weight's weight→∞ limit, restricted to dense's own candidates rather
than adding a lexical arm: a passage holding more of the question's anchors — found by
`weft_retrieve.intent_and_anchors.find_anchors`'s own rule — moves above one holding fewer,
the incoming order decides within a tie, and a question with no anchor leaves the ranking
exactly as it arrived. Weft-coined; no paper states this mechanism, only Phase 39's own
measurement of the weight it is the limit of.

**The matcher and `promote` are public** because Phase 40's ceiling and its oracle control
call the same two functions this stage does, rather than a second copy of either.

**The rule extractor's caveat carries over unchanged.** `find_anchors`'s shape-only rule was
measured at precision 0.800 on forty blind questions (`39.1`) — a false anchor can lift a
sibling passage above the one that actually answers the question, and this stage inherits
that ceiling rather than raising it: it never admits a passage the incoming ranking did not
already hold.
"""

import re
from collections.abc import Sequence
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from weft_kernel.context import Context
from weft_kernel.payload import ExtModel, Outcome, Produced
from weft_retrieve.intent_and_anchors import find_anchors
from weft_retrieve.payload import Passage, Ranking
from weft_store.contract import Scored

#: The name this reranker is registered and selectable under — see `weft_retrieve.register`.
NAME = "anchor-promote"

#: A hyphen between two word characters, removed before tokenising — `WRH-123` and `wrh123`
#: are the same anchor, but a bare hyphen (a list bullet, a line break) is not a token
#: separator this rule invents.
_INFIX_HYPHEN: re.Pattern[str] = re.compile(r"(?<=\w)-(?=\w)")
_TOKEN: re.Pattern[str] = re.compile(r"\w+")


def _tokens(text: str) -> tuple[str, ...]:
    normalised = _INFIX_HYPHEN.sub("", text.casefold())
    return tuple(_TOKEN.findall(normalised))


def anchor_contained(anchor: str, text: str) -> bool:
    """Whether `anchor`'s tokens occur as a **contiguous** subsequence of `text`'s tokens.

    Both are casefolded and stripped of infix hyphens before tokenising, so `WRH-123` matches
    `wrh123` and `CVE-2019-4102` matches itself regardless of case. Whole-token: `7.5.0.2`
    tokenises to `7 5 0 2` and is not contained in `7.5.0.21`'s `7 5 0 21`, because `2` and
    `21` are different tokens. An anchor with no tokens at all is contained nowhere.
    """
    needle = _tokens(anchor)
    if not needle:
        return False
    haystack = _tokens(text)
    span = len(needle)
    return any(
        haystack[start : start + span] == needle for start in range(len(haystack) - span + 1)
    )


def promote(hits: Sequence[Passage], anchors: Sequence[str]) -> tuple[tuple[Passage, ...], int]:
    """`hits`, stably partitioned by how many `anchors` each one contains, most first.

    Each emitted passage is rescored `3 × anchors held + its incoming score`, so the score
    agrees with the emitted order whenever incoming scores span less than 3 — true of cosine
    similarity, not of an integer-scoring reranker placed before this one.
    The returned int is how many hits hold at least one anchor, which is what the caller
    needs to tell "some passage was promoted" from "none were."
    """
    held_counts = [
        sum(1 for anchor in anchors if anchor_contained(anchor, hit.node.content)) for hit in hits
    ]
    order = sorted(range(len(hits)), key=lambda index: -held_counts[index])
    promoted = tuple(
        Passage(
            scored=Scored(value=hits[index].node, score=3 * held_counts[index] + hits[index].score),
            rank=rank,
            retrieved_by=hits[index].retrieved_by,
            label=hits[index].label,
        )
        for rank, index in enumerate(order)
    )
    return promoted, sum(1 for count in held_counts if count >= 1)


class AnchorBranch(StrEnum):
    """Which of the three branches `AnchorPromote.run` took.

    `Enum` per the project's string-constant rule.
    """

    NO_ANCHOR = "no-anchor"
    NONE_CONTAINED = "none-contained"
    PROMOTED = "promoted"


class AnchorPromotion(ExtModel):
    """What `AnchorPromote` did to one `Ranking`, attached under its own namespace.

    Rides `Ranking.ext`, never a `Node` — not registered with `weft_store.register_ext_model`,
    the same reading `weft_retrieve.fusion.FusionEvidence`'s own docstring gives for a record
    that never crosses the arity reduction onto a stored payload.
    """

    __namespace__ = "weft-retrieve-anchor-promote"
    __schema_version__ = "1"

    branch: AnchorBranch
    anchors: tuple[str, ...]
    hits_promoted: int

    produced_by: ClassVar[str] = NAME

    def explained(self) -> str:
        """The one-line sentence `weft_cli.explain.record_lines` prints under `--explain`."""
        if self.branch is AnchorBranch.NO_ANCHOR:
            return "branch: no-anchor, ranking unchanged"
        if self.branch is AnchorBranch.NONE_CONTAINED:
            return f"branch: none-contained, anchors {len(self.anchors)}, ranking unchanged"
        return f"branch: promoted, anchors {len(self.anchors)}, hits promoted {self.hits_promoted}"


class AnchorPromoteConfig(BaseModel):
    """`AnchorPromote`'s `with:` config. Every field has a default, per this pack's own rule.

    No `method` and no model option: this stage only ever reorders what `promote` gives it,
    over anchors `find_anchors`'s rule found — there is no second, model-backed way to do
    that, unlike `intent-and-anchors`'s own `method: model`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    entities: tuple[str, ...] = ()


class AnchorPromote:
    """Reorders a ranking by the question's own anchors.

    Satisfies `weft_retrieve.contract.Reranker` structurally.

    `cost_bound = (0, 0)`: `find_anchors` is a shape-only rule over the question's own text and
    `promote` a comparison over each hit's already-stored content — no service is resolved and
    no model is called, the same reading `weft_retrieve.shingle_resemblance`'s own module
    docstring gives for a plugin whose cost is neither a store round trip nor its absence.
    """

    score_semantics: ClassVar[str] = (
        "3 × the number of the question's anchors this passage holds, plus its incoming "
        "score — orders passages by anchors held, and is not a similarity nor comparable "
        "to a score from a different stage"
    )
    config_model: ClassVar[type[AnchorPromoteConfig]] = AnchorPromoteConfig
    cost_bound: ClassVar[tuple[int, int]] = (0, 0)

    def __init__(self, config: AnchorPromoteConfig | None = None) -> None:
        self._config = config if config is not None else AnchorPromoteConfig()

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Ranking]:
        """Promote hits by the anchors the question carries.

        Promote `payload.hits` by the anchors `payload.origin.text` carries, recording
        which of the three branches ran.

        No anchors at all, or no hit holding one, leaves `hits` unchanged; only the promoted
        branch reorders and rescores. `origin`, `contributors` and `note` always pass through
        untouched, and every other `ext` entry is carried alongside this stage's own record.
        """
        del ctx
        anchors = tuple(
            a.text for a in find_anchors(payload.origin.text, entities=self._config.entities)
        )

        if not anchors:
            record = AnchorPromotion(branch=AnchorBranch.NO_ANCHOR, anchors=(), hits_promoted=0)
            return Produced(
                value=payload.model_copy(
                    update={"ext": {**payload.ext, AnchorPromotion.__namespace__: record}}
                )
            )

        promoted, hits_promoted = promote(payload.hits, anchors)
        if hits_promoted == 0:
            record = AnchorPromotion(
                branch=AnchorBranch.NONE_CONTAINED, anchors=anchors, hits_promoted=0
            )
            return Produced(
                value=payload.model_copy(
                    update={"ext": {**payload.ext, AnchorPromotion.__namespace__: record}}
                )
            )

        record = AnchorPromotion(
            branch=AnchorBranch.PROMOTED, anchors=anchors, hits_promoted=hits_promoted
        )
        return Produced(
            value=payload.model_copy(
                update={
                    "hits": promoted,
                    "ext": {**payload.ext, AnchorPromotion.__namespace__: record},
                }
            )
        )


__all__ = [
    "NAME",
    "AnchorBranch",
    "AnchorPromote",
    "AnchorPromoteConfig",
    "AnchorPromotion",
    "anchor_contained",
    "promote",
]
