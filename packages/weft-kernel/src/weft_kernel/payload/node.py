"""The `Node` type, and the three ways to build one.

Settled in G5, specified in `docs/02-extension-model.md` section 1 ("The
payload model"). Six core fields, admitted because every store and every
retrieval strategy must understand them to function: `id`, `lineage`,
`content`, `media_type`, `embedding`, `ext`. Everything else a pack wants to
attach is namespaced extension data — see `ext.py` — never a seventh core
field.

Three reference bugs become unrepresentable here rather than merely guarded, as
`docs/06-phase-0-build.md` step 1 requires:

* **RAPTOR's unreachable summaries.** `Node.combine` refuses an empty
  `members` sequence, and a `model_validator` on `Node` itself refuses any
  parentless node that does not carry `SyntheticOrigin` — so a summary with
  no members and no stated reason for its absent lineage cannot be built by
  any path, not only through `combine`. The reference built summary nodes with
  `relationships={}` ("global summary: no single source document"), so they
  carried no `ref_doc_id` and no deletion path could ever reach them. Under
  `combine`, parents are explicit and `Lineage.sources` is the union of the
  members' sources — a summary with no members has no sources to derive.
* **A node claiming a source its parents do not.** `Lineage` itself refuses
  `sources` authored alongside non-empty `parents` (see `lineage.py`), so a
  node cannot claim ancestry to a document unrelated to what it was actually
  built from — the same defect class, one field over.
* **The multi-MB base64 blob reaching JSONB.** The reference guarded this with
  `_TRANSIENT_METADATA_KEYS`, a tuple of key names one pipeline stage had to
  remember to check. Here, transience is declared once on the `ExtModel`
  subclass that owns the namespace (`ExtModel.__transient__`) and
  `Node.without_transient` strips by that declaration — a type-level fact
  the registration seam (step 3) will apply automatically, not a list an
  author extends. `ext` is also validated into an immutable mapping (see
  `ext.py`), so a transient blob cannot be reinserted by mutating `node.ext`
  in place after stripping — only `with_ext` can put one back.
"""

import hashlib
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from weft_kernel.payload.ext import ExtMap, ExtModel
from weft_kernel.payload.ids import NodeId, SourceId
from weft_kernel.payload.lineage import Lineage
from weft_kernel.payload.media_type import MediaType
from weft_kernel.payload.vector import Vector


class SyntheticOrigin(ExtModel):
    """Attached automatically by `Node.synthetic`, carrying why the node has no lineage.

    This is what makes a synthetic node's absence of lineage "explicit,
    greppable, doctor-reportable" rather than merely a node with empty
    `lineage.parents` indistinguishable from a bug: `node.ext_as(SyntheticOrigin)`
    finds it, and a future `weft plugins doctor` can enumerate every one.
    """

    __namespace__ = "weft-kernel"

    reason: str


class Node(BaseModel):
    """A unit of content flowing through a pipeline.

    Frozen: every change is a new `Node`, produced by `derive`, `with_ext`,
    `with_embedding` or `without_transient`, never by mutating this one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: NodeId
    lineage: Lineage
    content: str
    media_type: MediaType
    embedding: Vector | None = None
    # `validate_default` sends even the omitted-`ext` case through the field's
    # validator, so a freshly built `MappingProxyType` comes out of the
    # `default_factory` too — `default=MappingProxyType({})` would hand every
    # node the *same* proxy instance, which `copy.deepcopy` (pydantic's guard
    # against shared mutable defaults) cannot copy, since `mappingproxy` has
    # no `__deepcopy__` and is not picklable.
    ext: ExtMap = Field(default_factory=dict, validate_default=True)

    @model_validator(mode="after")
    def _lineage_requires_parents_or_synthetic_origin(self) -> "Node":
        """Refuse a parentless node unless it carries `SyntheticOrigin`.

        This is what makes the reference's unreachable-summary bug unrepresentable
        by construction rather than only by the three factories being
        well-behaved: a plain `Node(...)` call with empty `lineage.parents`
        and no stated reason is refused here, no matter how it was built.
        """
        if self.lineage.parents:
            return self
        origin = self.ext.get(SyntheticOrigin.__namespace__)
        if not isinstance(origin, SyntheticOrigin):
            raise ValueError(
                "a node with no lineage parents must carry SyntheticOrigin in ext, "
                "stating why — construct it through Node.synthetic, which stamps "
                "this automatically; an unexplained parentless node is exactly the "
                "reference's RAPTOR bug, unreachable by any cascade delete"
            )
        return self

    def derive(
        self, *, content: str, media_type: MediaType | None = None, ordinal: int = 0
    ) -> "Node":
        """A child produced from this node. Lineage is carried; `ext` and `embedding` are not.

        The child is different content, so the parent's extension data and
        embedding do not silently carry over — later stages attach their own.
        """
        effective_media_type = self.media_type if media_type is None else media_type
        lineage = Lineage.derived(parents=(self.id,), sources=self.lineage.sources)
        node_id = _content_digest(
            media_type=effective_media_type,
            content=content,
            parent_ids=lineage.parents,
            ordinal=ordinal,
        )
        return type(self)(
            id=node_id, lineage=lineage, content=content, media_type=effective_media_type
        )

    @classmethod
    def combine(
        cls, members: Sequence["Node"], *, content: str, media_type: MediaType, ordinal: int = 0
    ) -> "Node":
        """A summary built from `members`. Parents are explicit and never empty.

        Raises if `members` is empty — see the module docstring for why that
        refusal is the fix for the reference's unreachable-summary bug.
        """
        if not members:
            raise ValueError(
                "Node.combine requires at least one member. An empty set would produce "
                "a summary with no derivable sources, unreachable by any cascade delete — "
                "this is the exact shape of the reference's RAPTOR bug, refused by construction."
            )

        parents = tuple(member.id for member in members)
        sources = frozenset[SourceId]().union(*(member.lineage.sources for member in members))
        lineage = Lineage.derived(parents=parents, sources=sources)
        node_id = _content_digest(
            media_type=media_type, content=content, parent_ids=parents, ordinal=ordinal
        )
        return cls(id=node_id, lineage=lineage, content=content, media_type=media_type)

    @classmethod
    def synthetic(
        cls,
        *,
        content: str,
        media_type: MediaType,
        reason: str,
        sources: frozenset[SourceId] = frozenset(),
        ordinal: int = 0,
    ) -> "Node":
        """A node with no real lineage — its absence stated rather than implied.

        `sources` is accepted directly here, and only here, because there are
        no parents to derive it from. This is also the root of a document's
        very first node: extraction has no upstream `Node`, only a source
        document, so it states that document's id as `sources` explicitly.

        Built in one constructor call, with `SyntheticOrigin` already in
        `ext`: the model-level invariant above rejects a parentless node
        that does not carry it, and `model_copy` (which `with_ext` uses)
        skips validation, so a two-step "build, then attach" sequence would
        raise on the intermediate object.
        """
        if not reason:
            raise ValueError("Node.synthetic requires a non-empty reason, so it stays greppable")

        lineage = Lineage(parents=(), sources=sources)
        node_id = _content_digest(
            media_type=media_type, content=content, parent_ids=(), ordinal=ordinal
        )
        return cls(
            id=node_id,
            lineage=lineage,
            content=content,
            media_type=media_type,
            ext={SyntheticOrigin.__namespace__: SyntheticOrigin(reason=reason)},
        )

    def _replace(self, **updates: object) -> "Node":
        """Rebuild this node through full validation.

        `model_copy(update=...)` skips validation entirely, so it would let a
        caller smuggle an invalid `content`, `media_type` or `ext` past every
        guard this model declares — including the lineage invariant above.
        Revalidating the whole node closes that: `with_ext`, `with_embedding`
        and `without_transient` cannot become a second, unchecked way to
        build one.
        """
        return type(self).model_validate({**self.__dict__, **updates})

    def with_ext(self, model: ExtModel) -> "Node":
        """Attach namespaced extension data, replacing any prior value in that namespace."""
        namespace = type(model).__namespace__
        return self._replace(ext={**self.ext, namespace: model})

    def ext_as[T: ExtModel](self, kind: type[T]) -> T | None:
        """This node's data for `kind`'s namespace, or `None` if absent.

        `None` is legitimate — the producing stage may have run and produced
        nothing for this node. A namespace occupied by a different type than
        requested raises: that is not a legitimate absence, it is two packs
        disagreeing about what one namespace means.
        """
        value = self.ext.get(kind.__namespace__)
        if value is None:
            return None
        if not isinstance(value, kind):
            raise TypeError(
                f"namespace '{kind.__namespace__}' holds {type(value).__name__}, "
                f"not {kind.__name__}"
            )
        return value

    def without_transient(self) -> "Node":
        """This node with every `__transient__` namespace stripped."""
        kept = {ns: model for ns, model in self.ext.items() if not type(model).__transient__}
        if len(kept) == len(self.ext):
            return self
        return self._replace(ext=kept)

    def with_embedding(self, embedding: Vector) -> "Node":
        """This node with its embedding set. Identity is unaffected — the digest excludes it."""
        return self._replace(embedding=embedding)


def _content_digest(
    *, media_type: MediaType, content: str, parent_ids: Sequence[NodeId], ordinal: int
) -> NodeId:
    """The content-addressed identity: media type, content, sorted parents, an ordinal.

    Excludes the embedding (derived from content, and it would bind ids to a
    model) and any stage configuration, so two pipelines producing
    byte-identical output produce one node. The ordinal disambiguates
    byte-identical content under the same parent set — the reference's RAPTOR row
    recovery used exact float equality and cross-assigned cluster ids for
    identical chunks silently; a caller passing distinct ordinals for
    siblings avoids that here.

    Parts are length-prefixed before hashing so that no concatenation of
    variable-length strings can collide across a different split of the same
    bytes.
    """
    digest = hashlib.sha256()
    for part in (media_type.value, content, *sorted(parent_ids), str(ordinal)):
        encoded = part.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, byteorder="big"))
        digest.update(encoded)
    return NodeId(digest.hexdigest())
