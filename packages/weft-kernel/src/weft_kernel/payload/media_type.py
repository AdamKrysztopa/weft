"""The closed vocabulary of what content a `Node` carries."""

from enum import StrEnum


class MediaType(StrEnum):
    """What kind of content a `Node` carries.

    A core field under G5's admission rule: every store and every retrieval
    strategy must understand it to function. That is why it is a closed enum
    rather than an open, pack-declared vocabulary — unlike a plugin name,
    there is no registry a third party extends here, and per the project's
    string-constant rule this is `Enum`, never `Literal[...]`.
    """

    TEXT = "text"
    IMAGE = "image"
    TABLE = "table"
