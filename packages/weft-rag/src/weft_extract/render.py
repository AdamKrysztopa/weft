"""`markdown` and `plain` — the two `Renderer` registrations this pack ships.

`.phase2-design.md` A.2: "first-party registrations: `markdown` and `plain`.
Both live in `weft-extract`, which already has zero third-party dependencies
and gains none." That last clause is a constraint on this module, not an
observation about it — a renderer reaching for a markdown library would make
every install of the `Extractor` contract pay for it.

**The two are genuinely different formats, and that is the point.** Two
registrations under one contract only buy anything if swapping the name changes
the answer; two that produce the same bytes would be a `format:` field wearing
a costume. The difference is the media distinction: markdown can say *this was
a table* and plain text cannot, so a table rendered as `plain` loses something
this module reports rather than hides.

**What neither carries, and why it is reported per node rather than assumed.**
An embedding is not text in any format. Extension data — page boundaries, a
table grid — is a model, and a renderer cannot know which of them a reader
would have wanted, so it names every one it dropped instead of deciding on the
reader's behalf which losses matter. That includes `SyntheticOrigin`, which
every root node carries: filtering it out would mean this module holding an
opinion about which kernel types are decorative, and being wrong about it
silently is worse than a line of noise a caller can ignore.
"""

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from weft_extract.payload import DroppedContent, DroppedKind, Rendition
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Outcome, Produced

#: The names these two are registered and selected under — see `weft_extract.register`.
PLAIN_NAME = "plain"
MARKDOWN_NAME = "markdown"


class PlainRendererConfig(BaseModel):
    """`PlainRenderer`'s `with:` configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: What goes between two nodes. A blank line by default, because the nodes a caller
    #: renders together are usually consecutive passages of one document.
    node_separator: str = "\n\n"


class MarkdownRendererConfig(BaseModel):
    """`MarkdownRenderer`'s `with:` configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    node_separator: str = "\n\n"
    #: Whether a node that is not `MediaType.TEXT` is fenced and labelled. Off would make
    #: this renderer produce the same bytes as `plain`, which is why it defaults on and
    #: is a knob rather than a compiled-in decision.
    label_non_text: bool = True


class PlainRenderer:
    """Every node's content, joined. The format that carries the least, stated honestly."""

    media_type: str = "text/plain"
    config_model: type[PlainRendererConfig] = PlainRendererConfig

    def __init__(self, config: PlainRendererConfig | None = None) -> None:
        self._config = config if config is not None else PlainRendererConfig()

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Rendition]:
        del ctx  # no service or locale this stage needs
        if not payload:
            return NothingToProduce(reason="no nodes to render")

        dropped = [drop for node in payload for drop in _unrenderable(node)]
        dropped += [
            DroppedContent(node_id=node.id, kind=DroppedKind.MEDIA, detail=node.media_type.value)
            for node in payload
            if node.media_type is not MediaType.TEXT
        ]
        return Produced(
            value=Rendition(
                text=self._config.node_separator.join(node.content for node in payload),
                media_type=self.media_type,
                nodes_rendered=len(payload),
                dropped=tuple(dropped),
            )
        )


class MarkdownRenderer:
    """Every node's content, with anything that is not prose fenced and labelled."""

    media_type: str = "text/markdown"
    config_model: type[MarkdownRendererConfig] = MarkdownRendererConfig

    def __init__(self, config: MarkdownRendererConfig | None = None) -> None:
        self._config = config if config is not None else MarkdownRendererConfig()

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Rendition]:
        del ctx  # no service or locale this stage needs
        if not payload:
            return NothingToProduce(reason="no nodes to render")

        labelling = self._config.label_non_text
        dropped = [drop for node in payload for drop in _unrenderable(node)]
        if not labelling:
            # Turned off, this renderer loses exactly what `plain` loses, and says so.
            dropped += [
                DroppedContent(
                    node_id=node.id, kind=DroppedKind.MEDIA, detail=node.media_type.value
                )
                for node in payload
                if node.media_type is not MediaType.TEXT
            ]
        return Produced(
            value=Rendition(
                text=self._config.node_separator.join(
                    _as_markdown(node, labelling=labelling) for node in payload
                ),
                media_type=self.media_type,
                nodes_rendered=len(payload),
                dropped=tuple(dropped),
            )
        )


def _as_markdown(node: Node, *, labelling: bool) -> str:
    """`node`'s content, fenced and labelled with its media type unless it is prose.

    A fence rather than a markdown table for a `TABLE` node: the grid a real
    table needs is not in `content` — it would be an extension model — so
    emitting pipes and dashes would invent a structure this renderer cannot
    see. The fence is honest about what is known: this was a table, and here is
    the text of it.
    """
    if not labelling or node.media_type is MediaType.TEXT:
        return node.content
    return f"```{node.media_type.value}\n{node.content}\n```"


def _unrenderable(node: Node) -> list[DroppedContent]:
    """Everything on `node` that no text format holds — its vector and its extensions.

    Shared by both renderers deliberately: the losses these two have in common
    are the ones a third renderer will also have, and a second copy of this list
    is where the two would quietly start disagreeing about what honesty means.
    """
    dropped: list[DroppedContent] = []
    if node.embedding is not None:
        dropped.append(
            DroppedContent(
                node_id=node.id,
                kind=DroppedKind.EMBEDDING,
                detail=f"{len(node.embedding.values)}-dimensional vector",
            )
        )
    dropped.extend(
        DroppedContent(node_id=node.id, kind=DroppedKind.EXTENSION, detail=namespace)
        for namespace in sorted(node.ext)
    )
    return dropped
