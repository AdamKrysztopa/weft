"""The three facts the cleaning chain's order actually turns on.

Task **1.7**, extended by task **2.35** — `docs/02-extension-model.md` §3 → *Ordering
constraints*: "G5 solved ordering by data dependency. It cannot solve the cleaning chain,
because `WhitespaceNormalizer` must run last for being destructive, not because anyone
reads its output." `intact`/`destroys` are the mirror G2 added for exactly that case, and
this module is where `weft-clean` states what it has to declare against.

**Why three properties, not two.** The reference's own docstring
(`indexing/cleaning/pipeline.py:30-51`) gives three independent reasons a cleaning stage
cares about what an earlier stage did, not two — the first two hold a *later* stage to a
fact an *earlier* one must not have erased yet; the third is the mirror image, holding
every *later* stage to account for a fact the *first* one needs. Each is a different fact
about the text:

* `Newlines` — a node's text still carries the line breaks the extractor produced. A word
  broken across a page by a trailing hyphen is only rejoinable while the break between its
  two halves is still a real newline; once that newline is gone, there is no longer a seam
  to find, only two separate words that happen to sit next to each other.
* `WhitespaceGaps` — a node's text still carries the original runs of whitespace between
  visually distinct regions on a page. A table's columns are not marked as columns anywhere
  in extracted text; the only signal that two words belong to different columns is the run
  of spaces between them, and once that run is collapsed to one space the columns are
  indistinguishable from ordinary prose.
* `Verbatim` — a node's text is still, character for character, what extraction handed
  over: no earlier stage has inserted, deleted or rearranged anything in it. A mis-decoded
  byte sequence (the reference's own example, `unicode_normalizer.py:15`: "Ã³ -> ó") is only
  recognisable and repairable by `ftfy.fix_text` while its bytes are still contiguous and
  in the order extraction produced them. Insert a space in the middle of it
  (`weft_clean.dictionary_spacing.PolishFusedWordFixer`), delete the line it sits on
  (`weft_clean.artifact_remover.ArtifactRemover`), or join it across a removed line break
  (`weft_clean.hyphenation.HyphenationRepair`), and the sequence `ftfy` needed to see is
  gone before it ever runs — not merely harder to fix, but no longer the sequence extraction
  actually produced.

**Why one stage destroys the first two, and every stage destroys the third.**
`weft_clean.whitespace.WhitespaceNormalizer` is the only stage in this pack that collapses
whitespace, and collapsing whitespace is what destroys `Newlines` and `WhitespaceGaps` at
once — there is no way to fold "many spaces" down to "one space" without erasing the very
run a table lineariser reads columns from, and no way to fold "line break" into "regular
space" without erasing the seam a hyphenation repair reads a broken word from. `Verbatim`
is destroyed the opposite way: not by one destructive stage, but by *every* stage in this
pack, because repairing text is what a `Cleaner` is for — inserting, deleting or rejoining
characters is not a side effect any of the six processors has, it is each one's entire job.
Only `weft_clean.unicode_normalizer.UnicodeNormalizer` ever needs `Verbatim` intact, so
`intact = (Verbatim,)` there and `destroys` naming `Verbatim` everywhere else is the
identical mechanism `WhitespaceNormalizer`'s "must run last" already uses, pointed the
other way: one property, needed by exactly one stage, destroyed by every stage that could
run before it, which is what forces that one stage to position 1 with no new machinery —
proven the same way any other `intact`/`destroys` pair is: at resolution, by
`weft_kernel.resolution.resolve`, never by a docstring an inserted stage could land past
unnoticed.

`docs/04-reference-inventory.md` category A and `docs/01-high-level-plan.md` → Phase 1 **Lift**
(task **2.35**'s correction) are the owners; both cite `indexing/cleaning/pipeline.py:
30-51` as the reference location this ordering knowledge was verified against — see
`weft_clean.hyphenation`, `weft_clean.table_linearizer`, `weft_clean.whitespace`,
`weft_clean.dictionary_spacing`, `weft_clean.artifact_remover` and
`weft_clean.unicode_normalizer` for where each property is actually declared.
"""

from weft_kernel.payload import Property


class Newlines(Property):
    """A node's text still carries the line breaks extraction produced, unjoined."""

    __namespace__ = "weft-clean"


class WhitespaceGaps(Property):
    """A node's text still carries its original whitespace runs, not yet collapsed."""

    __namespace__ = "weft-clean"


class Verbatim(Property):
    """A node's text is still, character for character, what extraction handed over."""

    __namespace__ = "weft-clean"
