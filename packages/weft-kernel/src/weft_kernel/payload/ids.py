"""The two identifier types the payload model needs.

`NodeId` is a content-addressed digest — see `node.py` for how it is computed.
`SourceId` identifies the document a node's lineage traces back to; it is
assigned by whichever component owns the record of that source document.
Both live in the kernel because `Lineage`, a kernel type, names them in its
own fields, and a pack downstream of the kernel cannot be the type a kernel
field is declared against.

Each is a `typing.NewType` over `str` rather than a real subclass: a
`NodeId`/`SourceId` compares, hashes and sorts exactly like the string it is,
with no unwrapping at call sites, while a signature can still require the
specific type rather than any string. Pydantic has built-in, dependency-free
support for `NewType` fields — unlike a genuine `str` subclass, which needs a
custom `__get_pydantic_core_schema__` that imports `pydantic_core` directly,
an import the kernel does not declare and fitness function 1 refuses.
"""

from typing import NewType

NodeId = NewType("NodeId", str)
SourceId = NewType("SourceId", str)
