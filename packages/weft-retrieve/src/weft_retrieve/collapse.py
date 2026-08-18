"""`collapse-to-parent` — one `Ranking` slot per parent, never one per representation.
`Reranker`.

Task **2.33**, `docs/build-ledger.md`: "one passage cannot occupy several slots of a
ranking merely because it was indexed several ways, because collapsing a ranking to its
parents is a named stage with a stated policy." `.phase2-findings.md` §11 (BINDING) is
the reason this task exists at all: "when several derived nodes of one parent all match a
query, returning them as separate results is usually wrong — the reader wants the
passage once. Collapsing a result set to its parents is a *named, testable* operation
belonging to the retrieval pack, not an implicit behaviour of the store." Without this
stage, a chunk indexed by `hypothetical-questions` (ledger 2.31) as itself plus three
question nodes can occupy four of a ranking's own top five slots, and every fan-out
measurement in 2.16–2.18 improves for a reason that is not real — `09` §4.2's failure,
named again in the ledger line that opened this task.

**`Stage[Ranking, Ranking]` — the same signature `Reranker` already publishes, and this
registers under it rather than growing a fifth query-path contract.** `.phase2-design.md`
§A.3 states the type and where it sits ("between fusion and context packing") but not a
contract name; `Reranker` is exactly that position, already hosts a second plugin that
filters rather than rescores (`graded-retrieval`, this pack's own precedent for "same in
and out" covering more than literal re-scoring against the question), and the phase's own
re-check (`.phase2-findings.md`'s closing note on decision S2) is that 2.31–2.33 "register
against contracts that already exist rather than publishing new ones" — a fourth contract
here would be the one thing that sentence is written to rule out.

**The grouping key is duplicated from `weft_generate.representation._parent_of`, not
imported from it — on purpose.** That function resolves a *citation* past a
single-parent representation to the node it stands in for, and `weft_generate` depends on
`weft_retrieve`, never the reverse: importing it here would put the arrow backwards. The
structural check itself is exactly the shape `weft_generate.representation`'s own module
docstring anticipates for a reader it does not know about — "any future pack's own
derived-representation marker satisfies it the same way, for free, the moment it carries a
`technique: str` attribute" — and this pack is that reader. **The same narrowing that
module states is reused rather than re-derived**: a node `Node.combine` built from several
members (`raptor`, ledger 2.32) has no single "the" parent to collapse into, so a
multi-parent node is grouped under its own id, exactly as if it carried no marker at all.

**The policy question `.phase2-design.md` §A.3 names and leaves to this task: which score
survives.** `CollapsePolicy` is a closed `StrEnum`, dispatched through a mapping rather than
an `if`/`elif` chain — `weft_retrieve.repack`'s own precedent for a technique that is one
mechanism with a field, not three plugins. `max` is the default: it is the reading that
changes fan-out measurement the least (a chunk found four ways scores no higher than the
best of those four finds alone), where `sum` would reward multiplicity of representation as
if it were multiplicity of evidence — precisely the artefact this task exists to remove,
made available under a different name for an operator who wants it rather than assumed for
everyone. `mean` sits between the two.

**Which node survives is a second question the score policy does not answer, and the
ledger line answers it directly: "holds the parent."** When one of a group's own hits is
already the parent itself — the ordinary shape for `hypothetical-questions`, whose chunk
node stays retrievable beside its derived questions — that hit's node is kept outright, no
store call made. When every survivor of a group is a representation and the parent itself
was never retrieved, the parent is fetched from the store, batched exactly like
`weft_generate.cited_answer._uris_for` and `weft_generate.representation.citable_nodes`
batch theirs: one `store.get` call for every distinct parent a batch of groups actually
needs, never one per passage. A parent the store could not find (deleted between indexing
and this run, in principle) falls back to the group's own best-scoring representation
rather than dropping the group — the identical "resolves to *a* node rather than raising"
choice `citable_nodes` already made for the same failure one stage later, applied here
because a ranking-shrinking stage that could make a ranking disappear on a store race is a
worse failure than the one it exists to fix.

**`retrieved_by` on the surviving `Passage` names whichever representation contributed the
single highest score in its group** — under every policy, including `sum` and `mean`,
where the aggregate itself is no longer any one contributor's own number. That representation
is also what "the parent was never retrieved" is decided from and, failing a store fetch,
what survives outright — one passage in the group is already doing the most explaining, and
attributing provenance to it is truer than concatenating every label the group held or
choosing among equals arbitrarily.

**Collapsing changes the score landscape, so this stage re-sorts, exactly like
`weft_retrieve.rerank.LlmRerank` does one position earlier for the identical reason.** A
group combined under `sum` or `mean` can end up ahead of or behind hits `payload.hits`
placed it near, and leaving the pre-collapse order in place would hand `weft_retrieve.repack`
a `Ranking` whose order no longer matches the scores next to it. `rank` is renumbered
contiguously over what survives, the same renumbering `weft_retrieve.graded`'s own filter
already does for its own output.
"""

from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from typing import ClassVar, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from weft_kernel.context import Context
from weft_kernel.payload import Node, NodeId, Outcome, Produced
from weft_retrieve.payload import Passage, Ranking
from weft_store.contract import NodeStore, Scored

#: The name this reranker is registered and selectable under — see `weft_retrieve.register`.
NAME = "collapse-to-parent"


class CollapsePolicy(StrEnum):
    """Which of a collapsed group's own scores becomes the surviving score. `Enum`, the
    project's rule for a closed vocabulary — an operator's typo in a `with:` block is a
    `ValidationError` naming the valid set, never a silent fall-through to whichever
    branch a chain reached first."""

    #: The best individual score in the group. This module's default — see the module
    #: docstring for why the artefact-removing reading, not the evidence-rewarding one,
    #: is what an operator gets without asking for something else.
    MAX = "max"
    #: Every individual score in the group, added.
    SUM = "sum"
    #: The group's own average score.
    MEAN = "mean"


class CollapseToParentConfig(BaseModel):
    """`CollapseToParent`'s `with:` config. Every field has a default, per this pack's own
    rule."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy: CollapsePolicy = CollapsePolicy.MAX


#: One mapping, not a chain: the enum member selects its own aggregator, so a fourth policy
#: is one entry here — never a new branch to remember to add. `max` and `sum` are the
#: builtins; `mean` is the one line neither builtin states.
_AGGREGATORS: Mapping[CollapsePolicy, Callable[[Sequence[float]], float]] = {
    CollapsePolicy.MAX: max,
    CollapsePolicy.SUM: sum,
    CollapsePolicy.MEAN: lambda scores: sum(scores) / len(scores),
}


@runtime_checkable
class _RepresentationMarker(Protocol):
    """Structurally, `weft_index.payload.Representation` — see the module docstring for why
    this is a fresh Protocol rather than an import of the pack that ships that class."""

    technique: str


def _collapse_key(node: Node) -> NodeId:
    """The id this node collapses under: its one parent, for a single-parent
    representation; itself, for everything else — a plain chunk, a root, or a
    `Node.combine` summary with no single "the" parent to stand in for."""
    if len(node.lineage.parents) != 1:
        return node.id
    if not any(isinstance(value, _RepresentationMarker) for value in node.ext.values()):
        return node.id
    return node.lineage.parents[0]


class CollapseToParent:
    """Groups a ranking's hits by parent, keeps one per parent, scores each by the
    configured policy. Satisfies `weft_retrieve.contract.Reranker` structurally.

    `cost_bound = (0, 0)`: `run` resolves `NodeStore` — never an `LLM`-shaped service — and
    only when a group's parent was not itself among the ranking's own hits, so a corpus
    with no multi-representation indexing in it makes no store call at all. See
    `weft_retrieve.vector_top_k`'s own module docstring for why a class attribute
    tracking model-call cost reads `(0, 0)` for a plugin whose real work is a store round
    trip rather than the absence of one.
    """

    config_model: ClassVar[type[CollapseToParentConfig]] = CollapseToParentConfig
    needs_store: ClassVar[tuple[type, ...]] = (NodeStore,)
    cost_bound: ClassVar[tuple[int, int]] = (0, 0)

    def __init__(self, config: CollapseToParentConfig | None = None) -> None:
        self._config = config if config is not None else CollapseToParentConfig()

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Ranking]:
        """Group by parent, aggregate by policy, fetch a missing parent once per group that
        needs one, re-sort by the surviving score, and renumber.

        **The emptiness rule** — no hits at all collapses to an empty `Ranking`, the
        identical case every other contract in this pack's own `contract.py` handles, for
        the identical reason (`09` §4's V2 requires the engine to answer "not in this
        corpus"). `origin`, `contributors` and `note` all pass through unchanged: this
        stage removes duplicate slots, it does not change which retriever or channel fed
        the ranking, and it does not manufacture a note the plugin one seam earlier did not
        already state.
        """
        if not payload.hits:
            return Produced(
                value=Ranking(
                    origin=payload.origin,
                    contributors=payload.contributors,
                    note=payload.note,
                    ext=payload.ext,
                )
            )

        groups: dict[NodeId, list[Passage]] = {}
        for passage in payload.hits:
            groups.setdefault(_collapse_key(passage.node), []).append(passage)

        missing = tuple(
            key for key, group in groups.items() if not any(p.node.id == key for p in group)
        )
        fetched: dict[NodeId, Node] = {}
        if missing:
            store = ctx.require(NodeStore)
            fetched = {node.id: node for node in await store.get(missing)}

        aggregate = _AGGREGATORS[self._config.policy]
        collapsed: list[tuple[float, int, Passage]] = []
        for key, group in groups.items():
            score = aggregate(tuple(passage.score for passage in group))
            strongest = max(group, key=lambda passage: passage.score)
            direct = next((passage.node for passage in group if passage.node.id == key), None)
            node = direct if direct is not None else fetched.get(key, strongest.node)
            collapsed.append(
                (
                    score,
                    strongest.rank,
                    Passage(
                        scored=Scored(value=node, score=score),
                        rank=strongest.rank,
                        retrieved_by=strongest.retrieved_by,
                    ),
                )
            )

        ordered = sorted(collapsed, key=lambda item: (-item[0], item[1]))
        hits = tuple(
            passage.model_copy(update={"rank": rank})
            for rank, (_, _, passage) in enumerate(ordered)
        )
        return Produced(
            value=Ranking(
                origin=payload.origin,
                hits=hits,
                contributors=payload.contributors,
                note=payload.note,
                ext=payload.ext,
            )
        )
