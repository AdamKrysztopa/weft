"""`PolishFusedWordFixer` — splits a preposition fused onto the word after it.

Task **1.7**'s second half: `docs/04-reference-inventory.md` ranks the reference's
243-word Polish fused-word exception set the single most valuable text-shaped
asset in the reference (`indexing/cleaning/processors/dictionary_spacing.py:31`,
months of native-speaker corpus work in one `set` literal) — and states
plainly that it is text, not knowledge: CLAUDE.md's rule is that no word list
from any other codebase enters this repository, and the reference study itself
was never opened past its own citations (`path:line` references and category
counts) to find this module's shape. **`_EXCEPTIONS` below is therefore
authored fresh for Weft, independently and much smaller** — the `reference-lift`
skill's own instruction: "a handful of entries authored here, with the
mechanism proven, is a complete task. A short honest list beats a
transcribed long one."

**What survives the lift is the design, not the words.** Polish forms many
common verbs and nouns with a short prefix that is *coincidentally* spelled
like a preposition — `zawsze` ("always") begins with `za`, the perfective
verb prefix that also spells the preposition "for/behind"; splitting it
produces "za wsze", two fragments that mean nothing. A naive splitter that
sees `<preposition><word>` fused with no space between them (a real and
frequent PDF-extraction artefact — `wcelu` for `w celu`, "for the purpose
of") cannot tell the two cases apart from spelling alone, so it needs a
standing exception list of words that must never be split. That the fix is
*data a pack ships*, not logic every call site re-derives, is the asset; the
words filling that data are ordinary language and this module's own.

No `intact` constraint: the reference's own note is "can run on clean text" —
this stage does not *need* anything an earlier stage produced, unlike
`weft_clean.hyphenation.HyphenationRepair` and
`weft_clean.table_linearizer.TableLinearizer`. **Task 2.35 adds one thing to
`destroys`, though**: splitting a fused word inserts a literal space into
what was a contiguous run of characters (`_split_if_fused` below), and a
mis-decoded byte sequence `weft_clean.unicode_normalizer.UnicodeNormalizer`
has not yet repaired is exactly that — a contiguous run this stage has no
way to recognise as one thing. `destroys = (Verbatim,)` names that honestly;
see `weft_clean.property`'s module docstring for why every processor in this
pack destroys `Verbatim`, not only this one.

**`applies_to` — a repair, not part of the original lift.** This class is the
one language-specific stage in the tree, and until this fix it declared no
`applies_to` at all: `weft_kernel.runner`'s documented default for that case
is "applies to everything", so this fixer's Polish-only exception logic ran
on every node in a mixed-language batch, splitting ordinary English words
that happen to start with one of `_PREPOSITIONS`' letters (`'The dogma of
water conservation'` -> `'The do gma of w ater conservation'`). See
`weft_clean.language.Language` for why `weft-clean` is the fact's interim
owner, and `docs/02-extension-model.md` §3 → *Language, and what a var is
for* for the promise this now actually keeps: "A Polish fixer applies to
Polish nodes; English nodes flow past." No node carries `Language` yet —
there is no `detect` stage to produce one — so today this narrows the fixer
to *no* node at all, which is the correct, safe-side reading of "unknown
language flows past" until one exists.
"""

import re
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from weft_clean.language import Language
from weft_clean.property import Verbatim
from weft_kernel.context import Context
from weft_kernel.payload import Applies, Node, NothingToProduce, Outcome, Produced, Property

#: Ordered longest-first so `przez` is tried before `za`, which is tried
#: before `z` — a shorter preposition that is also a prefix of a longer one
#: must never win the match first, or `przez` would be read as `z` + `rez`.
_PREPOSITIONS: tuple[str, ...] = ("przez", "dla", "za", "na", "do", "w", "z", "o")

#: Below this many letters, the "remainder" after stripping a preposition is
#: too short to plausibly be a real word on its own, so the guard below
#: leaves the token alone without even consulting `_EXCEPTIONS`.
_MIN_REMAINDER_LENGTH = 3

#: Independently authored for Weft — see the module docstring. Twelve
#: everyday Polish words, each one a real word beginning with one of the
#: prefixes above, chosen to demonstrate the mechanism honestly rather than
#: to approximate the reference's coverage: a fused-word fixer with no exception
#: list at all would tear every one of these in half.
_EXCEPTIONS: frozenset[str] = frozenset(
    {
        "zawsze",  # always
        "zamek",  # castle / lock
        "zakochac",  # to fall in love
        "napisac",  # to write
        "nazwisko",  # surname
        "dokument",  # document
        "dolina",  # valley
        "dostawca",  # supplier
        "wodospad",  # waterfall
        "wszystko",  # everything
        "wnioski",  # conclusions
        "oczywiscie",  # obviously
    }
)

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


class PolishFusedWordFixerConfig(BaseModel):
    """`PolishFusedWordFixer` takes no `with:` configuration — an empty model is still the shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class PolishFusedWordFixer:
    """Splits `wcelu` into `w celu`, unless the fused-looking word is a real word.

    Satisfies `weft_clean.contract.Cleaner` structurally.
    """

    intact: tuple[type[Property], ...] = ()
    destroys: tuple[type[Property], ...] = (Verbatim,)
    applies_to: tuple[Applies, ...] = (Applies(Language, code="pl"),)
    config_model: type[PolishFusedWordFixerConfig] = PolishFusedWordFixerConfig

    def __init__(self, config: PolishFusedWordFixerConfig | None = None) -> None:
        self._config = config if config is not None else PolishFusedWordFixerConfig()

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        if not payload:
            return NothingToProduce(reason="no nodes to fix")
        fixed = [node.derive(content=_fix_fused_words(node.content)) for node in payload]
        return Produced(value=fixed)


def _fix_fused_words(text: str) -> str:
    """Every fused `<preposition><word>` token in `text`, split unless it is a real word."""
    return _WORD.sub(_split_if_fused, text)


def _split_if_fused(match: re.Match[str]) -> str:
    word = match.group(0)
    lower = _strip_diacritics(word.lower())
    if lower in _EXCEPTIONS:
        return word
    for preposition in _PREPOSITIONS:
        if lower.startswith(preposition) and len(word) - len(preposition) >= _MIN_REMAINDER_LENGTH:
            return f"{word[: len(preposition)]} {word[len(preposition) :]}"
    return word


_DIACRITIC_FOLD = str.maketrans("ąćęłńóśźż", "acelnoszz")


def _strip_diacritics(word: str) -> str:
    """`word`, ASCII-folded — `_EXCEPTIONS` is spelled in plain ASCII, see the module docstring."""
    return word.translate(_DIACRITIC_FOLD)
