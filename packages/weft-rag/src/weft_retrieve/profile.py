"""`profile_query` and `corpus_profile` — a question's and a corpus's shape, no model call.

A `QueryProfile` names three things about a question's own text: how long it is, which exact
spans it names (the anchors `weft_retrieve.intent_and_anchors.find_anchors` already finds), and
which cue families (`weft_retrieve.profile_cues.CueName`) its wording carries, in its own
language. Deterministic and model-free: the same text, locale and lexicon always give the same
profile, so its `features()` are names a routing rule can test and an evidence claim can cite.

**`CorpusProfile`** — ledger task **44.15** — is the same idea turned on the corpus a run has
in front of it rather than on the question: how many sources, how big, how far each derived
layer has reached, and whether the whole thing fits a role's declared context window. Built
from the `list_sources()` read an ask already makes for `weft_store.coverage.coverage_of`
(`weft_cli.commands._coverage_for`), never a second store round trip. A feature whose value is
not known — sizes no index run recorded, tokens counted by two different tokenizers, a context
size no role declared — is left out of `features()` entirely, never guessed: a rule that tests
a missing feature simply does not match, the identical "omit rather than invent" contract
`QueryProfile.features` already keeps.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from weft_llm.roles import RoleMapping
from weft_retrieve.intent_and_anchors import AnchorKind, find_anchors
from weft_retrieve.profile_cues import DEFAULT_CUES, CueLexicon, CueName
from weft_store.contract import SourceRecord, SourceStats, SourceStatus
from weft_store.coverage import layer_coverage_of

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

#: Every `features()` key these two profilers can emit but one: `corpus.layer.<name>.ready` is named
#: by whichever layers a corpus carries, so it is matched by shape in `is_declared_feature`.
DECLARED_FEATURES: Final[frozenset[str]] = frozenset(
    {
        "query.word_count",
        "query.locale_fallback",
        *(f"query.anchor.{kind.value}" for kind in _COUNTED_ANCHOR_KINDS),
        *(f"query.cue.{cue.value}" for cue in CueName),
        "corpus.documents",
        "corpus.fully_enriched",
        "corpus.leaves",
        "corpus.leaf_tokens",
        "corpus.fits_context",
    }
)

_LAYER_FEATURE_RE: Final[re.Pattern[str]] = re.compile(r"corpus\.layer\..+\.ready")

_FITS_CONTEXT: Final[str] = "corpus.fits_context"
_FITS_CONTEXT_ROLE_PREFIX: Final[str] = f"{_FITS_CONTEXT}."
_ANSWER_ROLE: Final[str] = "generate"


def is_declared_feature(name: str) -> bool:
    """Whether `name` is a feature `QueryProfile` or `CorpusProfile` can emit.

    What a routing rule's misspelt feature is checked against (R44.15): a declared name the
    corpus omits is *unknown* and matches nothing, while a name neither declared nor carried by a
    scorecard is an error.
    """
    return (
        name in DECLARED_FEATURES
        or _LAYER_FEATURE_RE.fullmatch(name) is not None
        or fits_context_role(name) is not None
    )


def fits_context_role(feature: str) -> str | None:
    """The role a context-fit feature is about, or `None` when `feature` is not one.

    `corpus.fits_context` is `generate`'s; `corpus.fits_context.<role>` is `<role>`'s (R44.20b).
    """
    if feature == _FITS_CONTEXT:
        return _ANSWER_ROLE
    if feature.startswith(_FITS_CONTEXT_ROLE_PREFIX):
        return feature.removeprefix(_FITS_CONTEXT_ROLE_PREFIX) or None
    return None


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


class LayerState(BaseModel):
    """How far one derived layer has reached across the corpus, and whether that is "ready".

    `ready` is `built == of` over at least one source (`of > 0`) — a layer named on no
    `ACTIVE` source at all is not ready either, the same "nothing built" reading
    `weft_store.coverage.ready_layers` already gives an empty `of`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    built: int
    of: int
    ready: bool


class CorpusProfile(BaseModel):
    """A corpus's shape, described with no model call and no second `list_sources()` read.

    See the module docstring for the "omit rather than invent" contract `features()` keeps.
    `leaves`/`leaf_tokens` are summed across `ACTIVE` sources only, and only when every one of
    them carries the field — a source `weft index` has never sized is an unknown total, never a
    partial one silently reported as the whole. `leaf_tokens` additionally requires every
    counted source to share one tokenizer: token counts from two tokenizers are not
    comparable, let alone summable.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    documents: int
    leaves: int | None
    leaf_tokens: int | None
    leaf_tokens_complete: bool
    layers: Mapping[str, LayerState]
    fully_enriched: bool
    fits_context: bool | None
    fits_context_by_role: Mapping[str, bool] = Field(default_factory=dict)

    def features(self) -> Mapping[str, int | float | bool]:
        """The flat, named `corpus.*` features a routing rule tests, omitting every unknown."""
        features: dict[str, int | float | bool] = {
            "corpus.documents": self.documents,
            "corpus.fully_enriched": self.fully_enriched,
        }
        if self.leaves is not None:
            features["corpus.leaves"] = self.leaves
        if self.leaf_tokens is not None:
            features["corpus.leaf_tokens"] = self.leaf_tokens
        if self.fits_context is not None:
            features[_FITS_CONTEXT] = self.fits_context
        for role, fits in sorted(self.fits_context_by_role.items()):
            features[f"{_FITS_CONTEXT_ROLE_PREFIX}{role}"] = fits
        for name, layer in self.layers.items():
            features[f"corpus.layer.{name}.ready"] = layer.ready
        return features


def _summed_leaves(stats: Sequence[SourceStats | None]) -> int | None:
    """Every `stats.leaves`, summed — or `None` unless every one of `stats` carries it."""
    if not stats or any(stat is None for stat in stats):
        return None
    return sum(stat.leaves for stat in stats if stat is not None)


def _summed_leaf_tokens(stats: Sequence[SourceStats | None]) -> int | None:
    """Every `stats.tokens`, summed — or `None` unless every one shares one tokenizer.

    Counted independently of `_summed_leaves`: a token count is a second, stricter fact about
    the same sources, not merely a narrower read of the same one.
    """
    if not stats or any(stat is None or stat.tokens is None for stat in stats):
        return None
    tokenizers = {stat.tokenizer for stat in stats if stat is not None}
    if len(tokenizers) != 1:
        return None
    return sum(stat.tokens for stat in stats if stat is not None and stat.tokens is not None)


def _layer_states(records: Sequence[SourceRecord]) -> dict[str, LayerState]:
    """One `LayerState` per layer `weft_store.coverage.layer_coverage_of` names."""
    return {
        coverage.name: LayerState(
            built=coverage.built,
            of=coverage.of,
            ready=coverage.of > 0 and coverage.built == coverage.of,
        )
        for coverage in layer_coverage_of(records)
    }


def corpus_profile(
    records: Sequence[SourceRecord],
    *,
    context_tokens: int | None,
    role_context_tokens: Mapping[str, int | None] | None = None,
) -> CorpusProfile:
    """`records`' shape: how many sources, how big, how enriched, and whether it fits a context.

    `records` is the whole `list_sources()` read a caller already made — see the module
    docstring for why this never reads a store itself. `context_tokens` is the role a run would
    generate under's declared context window (`weft_llm.roles.RoleMapping.context_tokens`),
    or `None` when it is not declared; `fits_context` is `None` whenever either side of that
    comparison is unknown. `role_context_tokens` is every role's own declared window, from which
    `fits_context_by_role` is built — a role with no window, or a corpus with no known size,
    contributes nothing, so no role is ever read as fitting by another's window (R44.20b).
    """
    active = tuple(record for record in records if record.status is SourceStatus.ACTIVE)
    stats = tuple(record.stats for record in active)
    leaves = _summed_leaves(stats)
    leaf_tokens = _summed_leaf_tokens(stats)
    layers = _layer_states(records)
    fits_context = (
        leaf_tokens <= context_tokens
        if leaf_tokens is not None and context_tokens is not None
        else None
    )
    fits_by_role = {
        role: leaf_tokens <= window
        for role, window in (role_context_tokens or {}).items()
        if leaf_tokens is not None and window is not None
    }
    return CorpusProfile(
        documents=len(active),
        leaves=leaves,
        leaf_tokens=leaf_tokens,
        leaf_tokens_complete=leaf_tokens is not None,
        layers=layers,
        fully_enriched=bool(layers) and all(layer.ready for layer in layers.values()),
        fits_context=fits_context,
        fits_context_by_role=fits_by_role,
    )


def corpus_profile_under(
    records: Sequence[SourceRecord], roles: Mapping[str, RoleMapping]
) -> CorpusProfile:
    """`corpus_profile` over every window `roles` declares, `generate`'s as the plain fit.

    The one place a `[llm.roles]` block becomes context windows, so the three callers that build
    a profile — `weft ask`, `weft route explain` and an eval router arm — cannot disagree.
    """
    windows = {name: mapping.context_tokens for name, mapping in roles.items()}
    return corpus_profile(
        records, context_tokens=windows.get(_ANSWER_ROLE), role_context_tokens=windows
    )
