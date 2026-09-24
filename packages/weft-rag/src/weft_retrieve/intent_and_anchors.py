"""Splits a question into its intent, searched densely, and its exact anchors, searched lexically.

Weft's own design, settled at **G24** (2026-09-17): the owner's own formulation was "a
query-understanding/decomposition step that separates the full semantic intent from only the
exact retrieval anchors" — `docs/10-technique-catalogue.md` §1.1's `intent-and-anchors` row is
the published claim this module makes true. `hybrid` already searches only the arms a
`Query.channels` names (`weft_retrieve/hybrid.py:178 "asked = frozenset(query.channels)"`) and
skips a query whose arms it does not offer, so labelling the intent for the vector arm and each
anchor for the text arm is the whole mechanism — `hybrid` itself needs no edit.

**`find_anchors`, the default `method: rule`, is deliberately narrow** — an all-caps acronym or a
hyphenated name without a digit is refused — and it failed its gate on meaning, not shape: a blind
forty scored precision 0.800 / recall 0.923, `32MB` read as an identifier beside `AX6000` and
`ETIMEDOUT` missed (ledger `39.1`). **`method: model`** asks the configured `LLM` through the
registered `question-anchors` prompt instead. G24's trade was then reversed by the owner to
**recall first, precision at least 0.95**: an anchor the model names may recombine words the user
typed (`TLS 1.2` from "TLS 1.3 … with 1.2") and is refused only when it introduces a word the
question does not contain.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from enum import StrEnum
from itertools import pairwise
from typing import Annotated, ClassVar, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from weft_kernel.context import Context
from weft_kernel.payload import Failed, Outcome, Produced
from weft_llm.contract import LLM, LLMRole
from weft_prompts.cascade import execute
from weft_prompts.contract import Prompt
from weft_retrieve.contract import StageLookup
from weft_retrieve.payload import Channel, Query, QueryOrigin, QuerySet
from weft_retrieve.prompts import QUESTION_ANCHORS_NAME, QuestionAnchors, QuestionAnchorsRequest

#: The name this transform is registered and selectable under — see `weft_retrieve.register`.
NAME: Final[str] = "intent-and-anchors"

_QUOTE_PAIRS: Final[tuple[tuple[str, str], ...]] = (('"', '"'), ("“", "”"), ("`", "`"))
_STRIP_CHARS: Final[str] = ".,;:!?()[]{}'\"§"
_ORDINAL_RE: Final[re.Pattern[str]] = re.compile(r"^\d+(st|nd|rd|th)$", re.IGNORECASE)
_DOTTED_DIGITS_RE: Final[re.Pattern[str]] = re.compile(r"^\d+(\.\d+)+$")
#: Two lowercase letters first, so `DoH`, `iOS` and `iPhone` stay words; PascalCase is refused
#: because by shape alone it cannot be told from a brand name (`39.1`'s first gate).
_CAMEL_CASE_RE: Final[re.Pattern[str]] = re.compile(r"[a-z]{2,}[A-Z][a-z]")
#: A number glued to a unit of size, rate, frequency or time is an amount, never an identifier —
#: the one error class both extractors shared at `39.1`'s gate (`5GHz`, `32MB`).
_AMOUNT_RE: Final[re.Pattern[str]] = re.compile(
    r"^\d+(?:\.\d+)?\s?(?:[kmgtp]i?b|[kmg]?hz|[kmg]?bps|[mµun]?s)$", re.IGNORECASE
)


class AnchorKind(StrEnum):
    """Which rule matched — `Enum` per the project's string-constant rule."""

    IDENTIFIER = "identifier"
    QUOTED = "quoted"
    ENTITY = "entity"
    #: Named by `method: model` — the model, not a local rule, decided this span was an anchor.
    EXTRACTED = "extracted"


class AnchorMethod(StrEnum):
    """How `IntentAndAnchors` finds a question's anchors."""

    #: `find_anchors`'s shape-only rule — the default, and the only path that touches no
    #: `ctx` service.
    RULE = "rule"
    #: The model decomposition (`39.1`, second form) — asks the configured `LLM` through the
    #: registered `question-anchors` prompt.
    MODEL = "model"


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
    if _AMOUNT_RE.match(token):
        return False
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
    return bool(_CAMEL_CASE_RE.match(token))


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
    """`IntentAndAnchors`'s `with:` config.

    Every field has a default, per this pack's own rule that a Phase 2 pack's settings must be
    constructible with none supplied.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Which mechanism finds the anchors — see `AnchorMethod`.
    method: AnchorMethod = AnchorMethod.RULE
    #: Matched whole-word and case-sensitively — see `find_anchors`. Ignored under
    #: `method: model`, which is why the two may not be configured together — see
    #: `_entities_need_the_rule` below.
    entities: tuple[str, ...] = ()
    #: The registered `Prompt` asked under `method: model` — see
    #: `weft_retrieve.prompts.QuestionAnchorsPrompt`.
    prompt: str = Field(default=QUESTION_ANCHORS_NAME, min_length=1)
    #: The role `method: model`'s call to `execute` is billed and rate-limited under.
    role: Annotated[str, LLMRole()] = Field(default="anchors", min_length=1)

    @field_validator("entities")
    @classmethod
    def _no_entity_is_blank(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not entity for entity in value):
            raise ValueError(
                "every entry of IntentAndAnchorsConfig.entities names one entity to match "
                "as a whole word; a blank entry matches nothing."
            )
        return value

    @model_validator(mode="after")
    def _entities_need_the_rule(self) -> IntentAndAnchorsConfig:
        if self.method is AnchorMethod.MODEL and self.entities:
            raise ValueError(
                "IntentAndAnchorsConfig.entities is ignored under method=model: the model "
                "decomposition asks the question alone and never sees configured entities, "
                "so naming both would promise a match this method does not make."
            )
        return self


def _dedupe_first(texts: Sequence[str]) -> tuple[str, ...]:
    """`texts`, each kept at its first occurrence — the model path's own copy of the rule
    dedup `find_anchors` already applies to its own three sources.
    """
    seen: set[str] = set()
    kept: list[str] = []
    for text in texts:
        if text in seen:
            continue
        seen.add(text)
        kept.append(text)
    return tuple(kept)


def _searchable(anchor: str) -> str:
    """A model-named span as it is searched: without a call's `()` or a possessive `'s`."""
    text = anchor.strip()
    text = text.removesuffix("()")
    for possessive in ("'s", "\u2019s"):
        text = text.removesuffix(possessive)
    return text.strip()


def _anchor_queries(anchor_texts: Sequence[str], *, origin: Query) -> tuple[Query, ...]:
    """One `Query` per anchor text, aimed at `Channel.TEXT` alone — shared by both the rule
    and the model path, so an anchor is turned into a query exactly one way regardless of
    which mechanism named it.
    """
    return tuple(
        Query(
            text=text,
            origin=QueryOrigin.DERIVED,
            produced_by=NAME,
            locale=origin.locale,
            channels=(Channel.TEXT.value,),
            filter=origin.filter,
        )
        for text in anchor_texts
    )


class IntentAndAnchors:
    """Splits a question into its intent and its anchors.

    Satisfies `weft_retrieve.contract. QueryTransform` structurally.

    Never returns `NothingToProduce` — a question always has an intent, even when it has no
    anchor. `method: model` can return `Failed`: a model-named anchor carrying a word the
    question does not contain is refused rather than searched (see the module docstring);
    `method: rule` never fails.
    """

    config_model: ClassVar[type[IntentAndAnchorsConfig]] = IntentAndAnchorsConfig

    def __init__(self, config: IntentAndAnchorsConfig | None = None) -> None:
        self._config = config if config is not None else IntentAndAnchorsConfig()

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[QuerySet]:
        """The intent, aimed at the vector arm alone, plus one query per anchor for the text arm.

        Every incoming query another transform already derived (`produced_by` non-empty) passes
        through unchanged; every query still carrying the user's own words (`produced_by == ""`)
        is replaced by the intent — same text, aimed at `Channel.VECTOR` alone.

        `method: rule` (the default) never touches `ctx` — `find_anchors` is a pure function
        of the question and the configured entities. `method: model` asks the configured
        `LLM` the same question through the registered `question-anchors` prompt, exactly the
        shape `weft_retrieve.transforms.StepBack.run` asks its own prompt.
        """
        if self._config.method is AnchorMethod.MODEL:
            llm = ctx.require(LLM)
            lookup = ctx.require(StageLookup)
            prompt = await lookup.build_capability(Prompt, self._config.prompt)
            generated = await execute(
                llm=llm,
                prompt=prompt,
                values=QuestionAnchorsRequest(question=payload.origin.text),
                output=QuestionAnchors,
                role=self._config.role,
                ctx=ctx,
            )
            if not isinstance(generated, Produced):
                # Relayed exactly as `StepBack.run` relays its own cascade outcome — see that
                # method's own comment on this line.
                return generated
            named = (_searchable(anchor) for anchor in generated.value.value.anchors)
            anchor_texts = _dedupe_first(
                tuple(anchor for anchor in named if anchor and not _AMOUNT_RE.match(anchor))
            )
            question = payload.origin.text
            for anchor in anchor_texts:
                invented = [
                    word for word in anchor.split() if word.strip(_STRIP_CHARS) not in question
                ]
                if invented:
                    return Failed(
                        reason=(
                            f"the model named anchor '{anchor}', and the question does not "
                            f"contain {invented[0]!r}; an anchor may recombine the words the "
                            "user typed but never introduce one"
                        )
                    )
        else:
            anchor_texts = tuple(
                anchor.text
                for anchor in find_anchors(payload.origin.text, entities=self._config.entities)
            )

        intent = payload.origin.model_copy(update={"channels": (Channel.VECTOR.value,)})
        passthrough = tuple(query for query in payload.queries if query.produced_by)

        return Produced(
            value=QuerySet(
                origin=payload.origin,
                queries=(
                    intent,
                    *passthrough,
                    *_anchor_queries(anchor_texts, origin=payload.origin),
                ),
                history=payload.history,
                ext=payload.ext,
            )
        )
