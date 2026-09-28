"""Cue lexicons — the phrase families a question's own wording can carry.

A cue names a *family* of wording, not a call site: comparing two things, aggregating over
several, asking about the whole collection rather than one passage, asking about time, or
spanning more than one document. `weft_retrieve.profile.profile_query` reports which cues a
question's own text carries, in its own language, with no model call.

**The phrases below are authored for Weft**, short and lower-case, chosen for what a question
in that language typically uses to carry one of these five families — not a translation or a
transcription of any third party's word list (see `CLAUDE.md`: no third party's source text,
and a text-shaped asset such as a word list is authored fresh or it is a copy). An operator who
wants a third locale, or disagrees with a phrase here, passes another `CueLexicon` rather than
editing this one.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, field_validator

from weft_retrieve.locale import resolve_locale


class CueName(StrEnum):
    """The five cue families a query profile reports."""

    COMPARISON = "comparison"
    AGGREGATION = "aggregation"
    GLOBAL = "global"
    TEMPORAL = "temporal"
    CROSS_DOCUMENT = "cross-document"


class CueLexicon(BaseModel):
    """A locale-keyed table of cue phrases: locale -> cue -> the phrases that fire it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    phrases: Mapping[str, Mapping[CueName, tuple[str, ...]]]

    @field_validator("phrases")
    @classmethod
    def _phrases_are_lower_case_and_not_repeated(
        cls, value: Mapping[str, Mapping[CueName, tuple[str, ...]]]
    ) -> Mapping[str, Mapping[CueName, tuple[str, ...]]]:
        for by_cue in value.values():
            for cue_phrases in by_cue.values():
                seen: set[str] = set()
                for phrase in cue_phrases:
                    if not phrase or phrase != phrase.lower():
                        raise ValueError(f"phrase {phrase!r} must be non-empty and lower-case")
                    if phrase in seen:
                        raise ValueError(f"phrase {phrase!r} is repeated within one cue")
                    seen.add(phrase)
        return value

    def for_locale(
        self, locale: str | None
    ) -> tuple[Mapping[CueName, tuple[str, ...]], str | None]:
        """`self.phrases`'s entry for `locale`, resolved, with every `CueName` present.

        A cue a locale's own table leaves out reads as `()` rather than a missing key, so a
        caller never has to guess which cues that locale bothered to name.
        """
        key = resolve_locale(locale, self.phrases)
        empty: Mapping[CueName, tuple[str, ...]] = {}
        by_cue = self.phrases.get(key, empty) if key is not None else empty
        return {cue: by_cue.get(cue, ()) for cue in CueName}, key


#: Authored for Weft — see the module docstring. An operator overrides this by passing another
#: `CueLexicon` to `weft_retrieve.profile.profile_query`.
DEFAULT_CUES: Final[CueLexicon] = CueLexicon.model_validate(
    {
        "phrases": {
            "en": {
                "comparison": ("compare", "versus", "vs", "difference between"),
                "aggregation": ("how many", "total", "count", "sum of", "average"),
                "global": ("overall", "in general", "across all", "as a whole"),
                "temporal": ("since", "before", "after", "during", "timeline"),
                "cross-document": (
                    "across documents",
                    "between the documents",
                    "in both documents",
                    "across sources",
                ),
            },
            "pl": {
                "comparison": ("porównaj", "w porównaniu", "różnica między"),
                "aggregation": ("ile", "łącznie", "suma", "średnia"),
                "global": ("ogółem", "ogólnie", "w całości", "we wszystkich"),
                "temporal": ("od kiedy", "do kiedy", "przed", "w trakcie", "chronologia"),
                "cross-document": (
                    "w obu dokumentach",
                    "między dokumentami",
                    "w różnych źródłach",
                ),
            },
        }
    }
)
