"""Splits a question into its intent, searched densely, and its exact anchors, searched lexically.

Weft's own design, settled at **G24** (2026-09-17): the owner's own formulation was "a
query-understanding/decomposition step that separates the full semantic intent from only the
exact retrieval anchors" — `docs/10-technique-catalogue.md` §1.1's `intent-and-anchors` row is
the published claim this module makes true. `hybrid` already searches only the arms a
`Query.channels` names (`weft_retrieve/hybrid.py:178 "asked = frozenset(query.channels)"`) and
skips a query whose arms it does not offer, so labelling the intent for the vector arm and each
anchor for the text arm is the whole mechanism — `hybrid` itself needs no edit.

**Precision over recall is the settled trade**, not an incidental narrowing: a false anchor sends
the text arm chasing a token that names nothing, which is the noise Phase 38 measured; a missed
anchor costs a query only the dense arm it already had. `find_anchors` is deliberately narrow
because of that trade — an all-caps acronym or a hyphenated name without a digit reads as an
identifier to a human and is refused here on purpose, not by oversight.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from enum import StrEnum
from itertools import pairwise
from typing import ClassVar, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_retrieve.payload import Channel, Query, QueryOrigin, QuerySet

#: The name this transform is registered and selectable under — see `weft_retrieve.register`.
NAME: Final[str] = "intent-and-anchors"

_QUOTE_PAIRS: Final[tuple[tuple[str, str], ...]] = (('"', '"'), ("“", "”"), ("`", "`"))
_STRIP_CHARS: Final[str] = ".,;:!?()[]{}'\"§"
_ORDINAL_RE: Final[re.Pattern[str]] = re.compile(r"^\d+(st|nd|rd|th)$", re.IGNORECASE)
_DOTTED_DIGITS_RE: Final[re.Pattern[str]] = re.compile(r"^\d+(\.\d+)+$")
_LOWER_UPPER_RE: Final[re.Pattern[str]] = re.compile(r"[a-z][A-Z]")


class AnchorKind(StrEnum):
    """Which rule matched — `Enum` per the project's string-constant rule."""

    IDENTIFIER = "identifier"
    QUOTED = "quoted"
    ENTITY = "entity"


class Anchor(BaseModel):
    """One exact span the text arm is asked to look up on its own."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1)
    kind: AnchorKind


def _find_quoted(text: str) -> tuple[list[tuple[int, Anchor]], str]:
    """Quoted spans, replaced by whitespace so later steps never see what they enclosed."""
    found: list[tuple[int, Anchor]] = []
    remaining = list(text)
    for opener, closer in _QUOTE_PAIRS:
        start = 0
        while True:
            open_at = text.find(opener, start)
            if open_at == -1:
                break
            close_at = text.find(closer, open_at + len(opener))
            if close_at == -1:
                break
            inner = text[open_at + len(opener) : close_at].strip()
            if inner:
                found.append((open_at, Anchor(text=inner, kind=AnchorKind.QUOTED)))
            for index in range(open_at, close_at + len(closer)):
                remaining[index] = " "
            start = close_at + len(closer)
    return found, "".join(remaining)


def _find_entities(text: str, entities: Sequence[str]) -> tuple[list[tuple[int, Anchor]], str]:
    """Configured entities, matched whole-word and case-sensitively, then blanked out."""
    found: list[tuple[int, Anchor]] = []
    remaining = list(text)
    for entity in entities:
        pattern = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(entity) + r"(?![A-Za-z0-9_])")
        for match in pattern.finditer(text):
            if any(character != " " for character in remaining[match.start() : match.end()]):
                found.append((match.start(), Anchor(text=entity, kind=AnchorKind.ENTITY)))
                for index in range(match.start(), match.end()):
                    remaining[index] = " "
    return found, "".join(remaining)


def _is_identifier_shaped(token: str) -> bool:
    has_letter = any(character.isascii() and character.isalpha() for character in token)
    has_digit = any(character.isdigit() for character in token)
    if has_letter and has_digit and not _ORDINAL_RE.match(token):
        return True
    if token.isdigit() and len(token) >= 3:
        return True
    if _DOTTED_DIGITS_RE.match(token):
        return True
    if "_" in token:
        for left, right in pairwise(token.split("_")):
            if left and right and left[-1].isalnum() and right[0].isalnum():
                return True
    return bool(_LOWER_UPPER_RE.search(token))


def _find_identifiers(text: str) -> list[tuple[int, Anchor]]:
    """Whitespace-split tokens, stripped of leading/trailing punctuation, that pass the rule."""
    found: list[tuple[int, Anchor]] = []
    for match in re.finditer(r"\S+", text):
        raw = match.group()
        stripped = raw.strip(_STRIP_CHARS)
        if not stripped or not _is_identifier_shaped(stripped):
            continue
        offset = match.start() + raw.index(stripped)
        found.append((offset, Anchor(text=stripped, kind=AnchorKind.IDENTIFIER)))
    return found


def find_anchors(text: str, *, entities: Sequence[str] = ()) -> tuple[Anchor, ...]:
    """The anchors in `text`, in order of first occurrence, each appearing once.

    Applied in order — quoted spans, then configured entities, then identifier-shaped tokens —
    each step removing what it matched from the text the later steps see, so a quoted span or a
    matched entity is never re-split by a later rule.
    """
    quoted, after_quotes = _find_quoted(text)
    entity_hits, after_entities = _find_entities(after_quotes, entities)
    identifier_hits = _find_identifiers(after_entities)

    ordered = sorted((*quoted, *entity_hits, *identifier_hits), key=lambda pair: pair[0])
    seen: set[str] = set()
    anchors: list[Anchor] = []
    for _, anchor in ordered:
        if anchor.text in seen:
            continue
        seen.add(anchor.text)
        anchors.append(anchor)
    return tuple(anchors)


class IntentAndAnchorsConfig(BaseModel):
    """`IntentAndAnchors`'s `with:` config. Every field has a default, per this pack's own rule
    that a Phase 2 pack's settings must be constructible with none supplied.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Matched whole-word and case-sensitively — see `find_anchors`.
    entities: tuple[str, ...] = ()

    @field_validator("entities")
    @classmethod
    def _no_entity_is_blank(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not entity for entity in value):
            raise ValueError(
                "every entry of IntentAndAnchorsConfig.entities names one entity to match "
                "as a whole word; a blank entry matches nothing."
            )
        return value


class IntentAndAnchors:
    """Splits a question into its intent and its anchors. Satisfies `weft_retrieve.contract.
    QueryTransform` structurally.

    Never returns `NothingToProduce` or `Failed` — a question always has an intent, even when
    it has no anchor.
    """

    config_model: ClassVar[type[IntentAndAnchorsConfig]] = IntentAndAnchorsConfig

    def __init__(self, config: IntentAndAnchorsConfig | None = None) -> None:
        self._config = config if config is not None else IntentAndAnchorsConfig()

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[QuerySet]:
        """The intent, aimed at the vector arm alone, plus one query per anchor for the text arm.

        Every incoming query another transform already derived (`produced_by` non-empty) passes
        through unchanged; every query still carrying the user's own words (`produced_by == ""`)
        is replaced by the intent — same text, aimed at `Channel.VECTOR` alone.
        """
        del ctx
        anchors = find_anchors(payload.origin.text, entities=self._config.entities)

        intent = payload.origin.model_copy(update={"channels": (Channel.VECTOR.value,)})
        passthrough = tuple(query for query in payload.queries if query.produced_by)
        anchor_queries = tuple(
            Query(
                text=anchor.text,
                origin=QueryOrigin.DERIVED,
                produced_by=NAME,
                locale=payload.origin.locale,
                channels=(Channel.TEXT.value,),
                filter=payload.origin.filter,
            )
            for anchor in anchors
        )

        return Produced(
            value=QuerySet(
                origin=payload.origin,
                queries=(intent, *passthrough, *anchor_queries),
                history=payload.history,
                ext=payload.ext,
            )
        )
