"""`Keywords` — the namespaced fact `KeyBertKeywordExtractor` attaches to a node.

`docs/02-extension-model.md` section 1 → *The payload model*: everything a pack wants to
attach to a `Node` beyond its six core fields is namespaced extension data, read and
written through `Node.ext_as`/`Node.with_ext`, never a bare dict key a plugin has to
remember the spelling of. `terms` is deliberately the only field — see
`weft_enhance.keybert_stand_in` for why there is no `score` alongside each term.
"""

from weft_kernel.payload import ExtModel


class Keywords(ExtModel):
    """The keywords a node's content ranked highest for, most important first."""

    __namespace__ = "weft-enhance"
    __schema_version__ = "1.0.0"

    terms: tuple[str, ...]
