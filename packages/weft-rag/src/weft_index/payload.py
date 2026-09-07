"""`Representation` — the fact an `Expander`-derived node carries about itself.

Namespaced extension data, per `docs/02-extension-model.md` section 1: everything a pack
wants to attach to a `Node` beyond its six core fields is a declared `ExtModel` subclass,
read and written through `Node.ext_as`/`Node.with_ext`, never a bare dict key. `technique`
is the plugin name (registered under `weft_index.contract.Expander`) that built this node —
`weft_kernel.payload.node.SyntheticOrigin`'s own precedent for "explicit, greppable,
doctor-reportable" applied here: a future `weft plugins doctor` sweep can enumerate every
derived representation in a corpus and say which technique produced it, the same way it can
already enumerate every synthetic root.

Not transient: this fact is kept through storage and retrieval, on purpose. It is also read
outside this pack — structurally, never by importing it — by `weft_generate.cited_answer`,
to resolve a citation past a representation to the one node it stands in for rather than
attributing a claim to a question or a rephrasing nobody wrote as a passage. See that
module's `weft_generate.representation` for the duck-typed read and why it replaces an
import, the same precedent `weft_generate.page.page_for` already set for a chunk's offset.
"""

from pydantic import Field

from weft_kernel.payload import ExtModel


class Representation(ExtModel):
    """Marks a node as an `Expander`-derived stand-in for the one parent it was built from.

    Only meaningful together with exactly one `Lineage.parents` entry — the shape
    `Node.derive` always produces. A node `Node.combine` built from several members (a
    cluster summary) has no single "the" parent to stand in for and is cited as itself, on
    purpose: `weft_generate.representation`'s reader checks the parent count before ever
    trusting this marker, rather than this model trying to declare a rule it cannot enforce
    on its own.
    """

    __namespace__ = "weft-index"
    __schema_version__ = "1.0.0"

    #: The `Expander` plugin name that generated this node — `weft_index.hypothetical_
    #: questions.NAME` for this task's own registration.
    technique: str


class RaptorFacts(ExtModel):
    """What `raptor`'s cluster a summary was built from actually held, and how much of it the
    model that wrote the summary was actually shown. Ledger task **10.2**.

    `raptor._format_cluster` slices every member to an even share of `max_cluster_chars` so
    one long member cannot crowd its siblings out of the summary — argued in that function's
    own docstring, and this model does not change it. What it repairs is that the slicing was
    otherwise invisible: a summary built from 40% of its cluster is byte-identical to one
    built from the whole thing, at exactly the point where this plugin makes its strongest
    claim — that a summary abstracts its whole cluster, not a truncated prefix of it.

    Attached to **every** summary `raptor` returns, truncated or not — a field only a
    degraded summary carried could never be read as "nothing was dropped," because its
    absence would equally mean an older `raptor` wrote the node, or that this pack is not
    installed on whatever reads it back.

    The paper this plugin is named after does not truncate at all: Sarthi et al., *RAPTOR*
    (ICLR 2024, arXiv:2401.18059), p.4, re-clusters within an oversized cluster until every
    piece fits the model it is handed to. Weft diverges — it truncates evenly and records the
    truncation rather than re-clustering — and this model is that divergence stated rather
    than left implicit in `_format_cluster`'s own arithmetic.

    `characters_shown` describes the request that **succeeded**: when a first attempt fails
    and `raptor` retries with the cluster halved, this is the retry's count, never the
    failed attempt's — a record taken from the request that did not produce the summary
    would overstate what the summary is actually built on.

    `level` — task **10.6** — is the stored fact a filter can select on, kept beside this
    model's own `characters_held`/`characters_shown` rather than inside `Representation`,
    because `raptor-and-leaves-rrf.yaml` already filters on `ext.weft-index.technique` and
    changing what that model means would change a shipped query rung. It is **derived from
    the members, never from the stage**: a summary whose members carry no `RaptorFacts` of
    their own is level 1; a summary whose deepest member is at level *n* is at level *n+1*.
    A document may run one `raptor` stage or three, and a stage cannot know its own position
    in a pipeline, so a level computed from "which stage am I" would be wrong the moment an
    operator writes their own document — deriving it from what was actually clustered makes
    it true under any arrangement of stages. A leaf carries no `RaptorFacts` at all and
    therefore states no level: it is not level zero, because the filter
    `ext.weft-index-raptor.level` has to select exactly the abstractions, and a leaf tagged
    `0` would need every reader to know that `0` means "not one of these." T-Retriever (Wei
    et al., 2026, arXiv:2601.04945) p.5 indexes every tree node tagged with its level,
    `I = {(α, zα, lα)}`; RAPTOR itself carries no such tag because it never filters on one.
    """

    __namespace__ = "weft-index-raptor"
    __schema_version__ = "1.1.0"

    #: How many nodes the cluster held.
    members: int = Field(ge=1)
    #: How many of those members the model saw less than the whole content of.
    members_truncated: int = Field(ge=0)
    #: The total length of the members' own `content` — what the cluster held.
    characters_held: int = Field(ge=0)
    #: The total length of the member text that actually reached the model, in the request
    #: that produced this summary.
    characters_shown: int = Field(ge=0)
    #: This summary's depth in the tree: 1 over leaves, one more than the deepest member's
    #: own `level` otherwise. See the class docstring's own paragraph for why this is derived
    #: rather than read off the stage, and why a leaf states none at all rather than `0`.
    #:
    #: **No `upgrade` is implemented, so the base class's refusal stands**: a stored `1.0.0`
    #: row raises `SchemaVersionRefusedError` naming the namespace and both versions, rather
    #: than inventing a level for a row written before this field existed. That is correct
    #: rather than unfortunate — the only rows that could carry `1.0.0` were written by a
    #: development build inside this same unreleased phase.
    level: int = Field(ge=1)
