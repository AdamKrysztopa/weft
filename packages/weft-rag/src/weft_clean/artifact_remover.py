"""`ArtifactRemover` — strips page-number lines and separator lines, and nothing else.

Task **2.35** — the second of the two processors `docs/04-reference-inventory.md` category A
names and `weft-clean` did not ship. Verified at source, `reference/study/08-salvage.md` §T1.1
and `artifact_remover.py:10-79`: the reference's docstring promises header/footer removal by
"short lines appearing at fixed intervals", but `process()` is 28 lines doing exactly two
things — a page-number regex substitution and a per-line non-alphanumeric-ratio filter.
There is no interval analysis, no line-frequency map, no positional logic anywhere in the
79-line file. **That half is deliberately not lifted.** Carrying the docstring's promise
without the code behind it would ship a comment describing a capability that does not
exist — the exact drift `01`'s Phase 2 exit reference audit exists to catch, one file over from
where it was already caught once. This is a scar, recorded rather than quietly worked
around: a real header/footer remover, if one is ever built, is new work against a real
interval-analysis design, not a promise finally kept.

**Two constants carried as facts, not text** (`artifact_remover.py:22`, `:26`):
`_PAGE_NUMBER`'s pattern and `_SEPARATOR_THRESHOLD`'s value are the two behaviours that do
exist, unchanged from the reference — CLAUDE.md's rule is that no source text crosses the
reference symlink, but a regex and a threshold are facts about what already-verified code does,
not prose or a name.

**The page pattern is the English literal `Page`, left that way — §T1.1's own correction
list, item 6, on the record.** The reference's fix is "change it to a per-language list", but
the reference's own file never supplies one — no Polish (or any other) translation for "page"
appears anywhere in `artifact_remover.py` or in the salvage study's own citations of it.
`weft_clean.language.Language` exists in this pack and could narrow this stage the way
`weft_clean.dictionary_spacing.PolishFusedWordFixer` narrows itself with `applies_to` —
but that narrows a *stage* to a *language it is built for*, not a regex literal to a word
nobody has verified. Inventing a translation table with no source behind it — "Strona" for
Polish, and then what for every other locale this pack might someday see — is exactly the
fabricated-coverage failure `weft_clean.dictionary_spacing`'s own module docstring already
refused once, in the same pack, for the identical reason: a short honest list — or, here,
an honestly named absence — beats a table nobody verified. The limitation is real and
stated plainly instead: this stage's page-number removal only recognises the English word.
Its separator-line filter is not affected — it reads Unicode alphanumeric properties, never
a word, so it works the same for a Polish document's separator lines as an English one's.

**`intact = (Newlines,)`.** Both of this stage's behaviours are line-oriented by
construction: `_PAGE_NUMBER` is anchored `MULTILINE`, so `^`/`$` match at every `\\n`, and
the separator filter runs `text.split("\\n")` directly. Both depend on `\\n` still marking
the same line boundaries extraction produced — the identical dependency
`weft_clean.hyphenation.HyphenationRepair` already declares, for the identical property.
**`destroys = (Verbatim,)`** — deleting a whole line, or substituting a matched page number
with nothing, is deletion: the resulting text is no longer, character for character, what
extraction produced, which is `weft_clean.property`'s own definition of what this stage
takes from `weft_clean.unicode_normalizer.UnicodeNormalizer`.

`config_model = ArtifactRemoverConfig` — a repair, not part of the original lift, on the
same footing `weft_clean.hyphenation`'s own note gives.
"""

import re
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from weft_clean.property import Newlines, Verbatim
from weft_kernel.context import Context
from weft_kernel.payload import Node, NothingToProduce, Outcome, Produced, Property

#: **The specification, which is what makes this string ours to write:** a line whose entire
#: content is the word "Page", any run of spaces, and a run of digits — nothing else on the line
#: but leading or trailing whitespace — is a page number rather than prose, and page numbers are
#: extraction artefacts. Case-insensitive because a header may shout; `MULTILINE` because the
#: anchors are per line, not per document.
#:
#: `docs/04-reference-inventory.md`'s own settlement (2026-09-05) is why the specification is written
#: out rather than the citation left to stand alone: a string a written specification determines is
#: a specification, not an asset, and the reader should be able to check that claim here instead of
#: taking it. The reference arrived at the same string — `reference/study/08-salvage.md` §T1.1's constants
#: table, `artifact_remover.py:22` — which is evidence that the specification determines it, not a
#: source it was taken from. English only; see the module docstring for why no translation is
#: invented here.
_PAGE_NUMBER = re.compile(r"^\s*Page\s+\d+\s*$", re.IGNORECASE | re.MULTILINE)

#: `artifact_remover.py:26`. A line whose non-alphanumeric character ratio (spaces
#: excluded from both the numerator and the count) exceeds this is a separator, not prose.
_SEPARATOR_THRESHOLD = 0.5


class ArtifactRemoverConfig(BaseModel):
    """`ArtifactRemover` takes no `with:` configuration — an empty model is still the shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class ArtifactRemover:
    """Strips page-number lines (English `Page N`) and separator lines from every node.

    Satisfies `weft_clean.contract.Cleaner` structurally. See the module docstring for the
    reference's documented header/footer removal, which this class deliberately does not carry.
    """

    intact: tuple[type[Property], ...] = (Newlines,)
    destroys: tuple[type[Property], ...] = (Verbatim,)
    config_model: type[ArtifactRemoverConfig] = ArtifactRemoverConfig

    def __init__(self, config: ArtifactRemoverConfig | None = None) -> None:
        self._config = config if config is not None else ArtifactRemoverConfig()

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        if not payload:
            return NothingToProduce(reason="no nodes to remove artifacts from")
        cleaned = [node.derive(content=_remove_artifacts(node.content)) for node in payload]
        return Produced(value=cleaned)


def _remove_artifacts(text: str) -> str:
    """`text` with every English page-number line and every separator line dropped."""
    without_page_numbers = _PAGE_NUMBER.sub("", text)
    kept = [line for line in without_page_numbers.split("\n") if not _is_separator_line(line)]
    return "\n".join(kept)


def _is_separator_line(line: str) -> bool:
    """Whether `line` is more than half non-alphanumeric, spaces excluded either way."""
    stripped = line.strip()
    if not stripped:
        return False
    non_alnum = sum(1 for char in stripped if not char.isalnum() and not char.isspace())
    return (non_alnum / len(stripped)) > _SEPARATOR_THRESHOLD
