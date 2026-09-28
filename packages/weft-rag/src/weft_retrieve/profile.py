"""`profile_query` — a question's shape, described with no model call.

A `QueryProfile` names three things about a question's own text: how long it is, which exact
spans it names (the anchors `weft_retrieve.intent_and_anchors.find_anchors` already finds), and
which cue families (`weft_retrieve.profile_cues.CueName`) its wording carries, in its own
language. Deterministic and model-free: the same text, locale and lexicon always give the same
profile, so its `features()` are names a routing rule can test and an evidence claim can cite.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict

from weft_retrieve.intent_and_anchors import AnchorKind, find_anchors
from weft_retrieve.profile_cues import DEFAULT_CUES, CueLexicon, CueName

#: Bump whenever the text -> profile mapping changes, so a stored profile can be told apart
#: from one a later version of this module would have produced.
PROFILER_VERSION: Final[str] = "1"

#: `AnchorKind.EXTRACTED` is named only by `method: model` and is not counted here — this
#: profiler never calls a model.
_COUNTED_ANCHOR_KINDS: Final[tuple[AnchorKind, ...]] = (
    AnchorKind.IDENTIFIER,
    AnchorKind.QUOTED,
    AnchorKind.ENTITY,
)

_WORD_RE: Final[re.Pattern[str]] = re.compile(r"\w+")


class QueryProfile(BaseModel):
    """A question's shape, described with no model call — see the module docstring."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    word_count: int
    anchors: Mapping[AnchorKind, int]
    cues: frozenset[CueName]
    locale_used: str | None
    locale_fallback: bool
    profiler_version: str

    def features(self) -> Mapping[str, int | float | bool]:
        """The flat, named features a routing rule tests and an evidence claim cites."""
        return {
            "query.word_count": self.word_count,
            "query.anchor.identifier": self.anchors[AnchorKind.IDENTIFIER],
            "query.anchor.quoted": self.anchors[AnchorKind.QUOTED],
            "query.anchor.entity": self.anchors[AnchorKind.ENTITY],
            "query.locale_fallback": self.locale_fallback,
            **{f"query.cue.{cue.value}": cue in self.cues for cue in CueName},
        }


def _is_fallback(asked: str | None, used: str | None) -> bool:
    """Whether `used` is not the locale a caller actually asked for.

    No locale asked is a fallback by definition. Otherwise, `used` matching either the asked
    locale itself or its primary subtag (`pl-PL` -> `pl`) is not a fallback; anything else is.
    """
    if asked is None:
        return True
    primary = asked.split("-", 1)[0]
    return used != asked and used != primary


def _cues_firing(text: str, phrases: Mapping[CueName, tuple[str, ...]]) -> frozenset[CueName]:
    folded = text.casefold()
    return frozenset(
        cue
        for cue, cue_phrases in phrases.items()
        if any(re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", folded) for phrase in cue_phrases)
    )


def profile_query(
    text: str,
    *,
    locale: str | None,
    cues: CueLexicon = DEFAULT_CUES,
    entities: Sequence[str] = (),
) -> QueryProfile:
    """`text`'s shape: its length, its anchors, and which of `cues`'s families it carries.

    Pure and model-free — no network, no clock, no randomness — and never raises on any `str`.
    """
    word_count = len(_WORD_RE.findall(text))
    anchor_counts = Counter(anchor.kind for anchor in find_anchors(text, entities=entities))
    phrases, locale_used = cues.for_locale(locale)
    return QueryProfile(
        word_count=word_count,
        anchors={kind: anchor_counts[kind] for kind in _COUNTED_ANCHOR_KINDS},
        cues=_cues_firing(text, phrases),
        locale_used=locale_used,
        locale_fallback=_is_fallback(locale, locale_used),
        profiler_version=PROFILER_VERSION,
    )
