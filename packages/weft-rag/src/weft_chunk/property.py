"""Ordering-constraint properties this pack's stages can need `intact` or declare `destroys`.

`docs/02-extension-model.md` §3 → *Ordering constraints*: "The properties are
published by whichever pack publishes the contract — namespaced marker
classes." `Chunker` opts every implementation into stating `destroys`
(`weft_chunk.contract.Chunker.publishes_property_vocabulary`); this module is
where `weft-chunk` says what it actually has to declare against that.

`WordBoundaries` is real, not a placeholder for task 1.7's cleaning chain.
`weft_chunk.fixed_size.FixedSizeChunker` slices `Node.content` at a fixed
character offset with no regard for where a word ends — a word split across
a chunk boundary is embedded as two disconnected fragments, and no later
stage can rejoin them, except here the break can happen at every window
boundary, not only where an upstream page break happened to land. A
hyphenation-repair stage that needs unbroken words has no way to ask that of
`FixedSizeChunker`'s output today; `destroys = (WordBoundaries,)` states the
fact plainly instead of leaving it to be rediscovered downstream by whichever
stage runs into it first.
"""

from weft_kernel.payload import Property


class WordBoundaries(Property):
    """A node's text has not been split in the middle of a word."""

    __namespace__ = "weft-chunk"
