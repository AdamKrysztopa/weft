"""The two facts the cleaning chain's order actually turns on.

Task **1.7** — `docs/02-extension-model.md` §3 → *Ordering constraints*:
"G5 solved ordering by data dependency. It cannot solve the cleaning chain,
because `WhitespaceNormalizer` must run last for being destructive, not
because anyone reads its output." `intact`/`destroys` are the mirror G2 added
for exactly that case, and this module is where `weft-clean` states what it
has to declare against.

**Why two properties, not one.** The reference's own docstring gives two
independent reasons a cleaning stage cares about what an earlier stage did,
not one, and each reason is a different fact about the text:

* `Newlines` — a node's text still carries the line breaks the extractor
  produced. A word broken across a page by a trailing hyphen is only
  rejoinable while the break between its two halves is still a real newline;
  once that newline is gone, there is no longer a seam to find, only two
  separate words that happen to sit next to each other.
* `WhitespaceGaps` — a node's text still carries the original runs of
  whitespace between visually distinct regions on a page. A table's columns
  are not marked as columns anywhere in extracted text; the only signal that
  two words belong to different columns is the run of spaces between them,
  and once that run is collapsed to one space the columns are indistinguishable
  from ordinary prose.

**Why one stage destroys both.** `weft_clean.whitespace.WhitespaceNormalizer`
is the only stage in this pack that collapses whitespace, and collapsing
whitespace is what destroys both facts at once — there is no way to fold
"many spaces" down to "one space" without erasing the very run a table
lineariser reads columns from, and no way to fold "line break" into "regular
space" without erasing the seam a hyphenation repair reads a broken word
from. That is why "whitespace normalisation must run last" is not a rule
about that one stage that has to be remembered — it falls out of the single
stage that destroys two things two different earlier stages each need,
proven the same way any other `intact`/`destroys` pair is: at resolution,
by `weft_kernel.resolution.resolve`, never by a docstring an inserted stage
could land past unnoticed.

`docs/04-reference-inventory.md` category B and `docs/01-high-level-plan.md` →
Phase 1 **Lift** are the owners; both cite `indexing/cleaning/pipeline.py:
30-51` as the reference location this ordering knowledge was verified against —
see `weft_clean.hyphenation`, `weft_clean.table_linearizer` and
`weft_clean.whitespace` for where each property is actually declared.
"""

from weft_kernel.payload import Property


class Newlines(Property):
    """A node's text still carries the line breaks extraction produced, unjoined."""

    __namespace__ = "weft-clean"


class WhitespaceGaps(Property):
    """A node's text still carries its original whitespace runs, not yet collapsed."""

    __namespace__ = "weft-clean"
