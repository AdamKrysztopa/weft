"""A schema an operator curates, and what it admits. Ledger **11.11**.

The pure half of curated schemas: the model a curated file validates into, what it derives, what
it admits, and the proposal built from what a corpus already produced. No container and no model
call here — `weft_kg.commands` is the half that reads a file, talks to the store, and prints; this
module has no dependency capable of either.

**Typed relation rules, not two flat lists — settled with the owner 2026-09-10.** A schema of
entity types and predicates catches an invented word and admits any arrangement of approved ones,
and that arrangement is most of what a wrong extraction actually looks like: `Method wrote Person`
uses nothing an operator did not approve — `method` and `person` are both named, `wrote` is both
named — and says something impossible. A **rule** is the triple `(source_type, predicate,
target_type)`, so the arrangement itself is the thing checked. `entity_types` and `predicates`
below are therefore **derived** from `relations`, never stored beside them as their own fields:
two lists that can disagree with the rules they describe is exactly the drift `docs/README.md`
opens by refusing, and a derivation cannot drift from the thing it derives from.

**Matching is case- and whitespace-normalised, in one helper both `admits` and `identity` use.**
A model writes `Person` where the curated schema says `person`; refusing on capitalisation would
turn the drop counter an operator reads into a count of formatting accidents rather than of
structural violations — the number nobody could act on. `admits` and `identity` both have to
agree on what makes two rules "the same" one, so the normalisation lives in exactly one place
(`_normalised`) rather than two call sites that could quietly diverge.

**The version is a field, never a `ClassVar` — `S5`, at its most literal.** This model is written
to a TOML file in somebody's repository and read back later by whatever `weft-rag` is installed
then, which may not be the pack that wrote it. `weft_store.contract.Filter.version` is this
project's own recorded example of getting it wrong: a `ClassVar` is read off the *importing*
module, pydantic never serialises one, and a stored filter has therefore always carried no version
at all — the stored bytes and the field disagree by construction. `schema_version` here is an
ordinary field, defaulted to `KG_CURATED_SCHEMA_VERSION` and validated on every construction: a
value that does not match the installed pack is refused rather than silently read, because a file
from a later `weft-rag` may mean something different by the same field names, and reading it
anyway produces a plausible graph checked against the wrong constraint. Upgrade-or-refuse, the
rule every persisted surface in this tree follows — `weft_store.contract.ReconcileReport.
schema_version` is the worked example of getting it right, one distribution over.

**`propose_schema` is a measurement, not a model's opinion — also settled with the owner.** It
turns the `(source_type, predicate, target_type)` triples `llm-facts` already wrote into rules and
ranks them by how often the corpus produced them, so what an operator curates is the shape their
own corpus actually produced. A model asked to generalise a schema from a corpus would hand back a
tidier vocabulary and a worse artefact: the operator would be editing a model's guess about their
corpus rather than a measurement of it, and every `propose` call would cost a credential for
exactly the number this module can compute for free from facts already on disk.

**What `identity` is for.** `activate` writes it into the corpus and every fact the graph store
holds carries it, so it is the one question `weft graph show` and a reconcile pass both need
answered: *is this the same schema*, across checkouts and across time, independent of the order an
operator's editor happened to leave the rules in. Adding or removing a rule must change it —
otherwise a schema an operator widened would silently keep answering as if it had not — and
reordering the rules or the fields inside them must not, because a curated TOML file's rule set is
exactly the kind of thing an operator reorders while editing. The schema's `name` is part of the
digest and is never normalised: two schemas an operator gave different names are two schemas to
them, whatever their rules say.
"""

from __future__ import annotations

import tomllib
from collections.abc import Sequence
from hashlib import sha256
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from weft_kernel.errors import WeftError

#: `S5`: this pack's own curated-schema surface, versioned independently of `weft_kg.store.
#: KG_SCHEMA_VERSION` — a curated TOML file and the Postgres tables `GraphStore` owns are two
#: different persisted surfaces, and conflating their version numbers would make a change to one
#: read as a change to the other.
KG_CURATED_SCHEMA_VERSION: Final[str] = "1.0.0"


def _normalised(value: str) -> str:
    """The one place case- and whitespace-folding happens for schema matching.

    `admits` and `GraphSchema.identity` both need to agree on what makes two rules the same rule;
    routing both through this single helper is what keeps that agreement mechanical rather than a
    convention two call sites could drift apart on.
    """
    return value.strip().casefold()


class RelationRule(BaseModel):
    """One admitted arrangement: a source entity type, a predicate, a target entity type.

    The unit a curated schema is built from — see the module docstring for why a rule and not two
    flat vocabularies.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_type: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    target_type: str = Field(min_length=1)


class GraphSchema(BaseModel):
    """A named, versioned set of admitted relation rules — what an operator curates.

    `entity_types` and `predicates` are properties derived from `relations`, never stored fields;
    see the module docstring. `relations` itself must be non-empty: an empty schema admits
    nothing, so activating one would drop every fact a corpus holds and report it as a schema
    working correctly, which is refused here rather than left for `activate` to discover.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = KG_CURATED_SCHEMA_VERSION
    name: str = Field(min_length=1)
    relations: tuple[RelationRule, ...] = Field(min_length=1)

    @field_validator("schema_version")
    @classmethod
    def _refuse_a_disagreeing_version(cls, value: str) -> str:
        if value != KG_CURATED_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version {value!r} does not match this installed weft-rag's "
                f"schema_version {KG_CURATED_SCHEMA_VERSION!r}. A curated schema file written by "
                "a different weft-rag may mean something different by the same field names, so "
                "it is refused rather than read: upgrade weft-rag to match the file, or edit the "
                "file's schema_version to the installed one once you have checked its rules "
                "still mean what they said."
            )
        return value

    @property
    def entity_types(self) -> frozenset[str]:
        """Every `source_type`/`target_type` named by `relations` — derived, never stored."""
        types: set[str] = set()
        for relation in self.relations:
            types.add(relation.source_type)
            types.add(relation.target_type)
        return frozenset(types)

    @property
    def predicates(self) -> frozenset[str]:
        """Every `predicate` named by `relations` — derived, never stored."""
        return frozenset(relation.predicate for relation in self.relations)

    @property
    def identity(self) -> str:
        """A stable digest of `(name, the normalised rule set)` — see the module docstring.

        Order-independent (the normalised rules are sorted before hashing) so an operator
        reordering a curated file's rules while editing does not read as a new schema; a rule
        added or removed does change it. `name` is included raw, never normalised — see the
        module docstring's closing paragraph. Digest convention (`sha256`, hex, truncated to 32
        characters) matches `weft_kg.store._alias_id_for`, this pack's own existing one.
        """
        normalised_rules = sorted(
            (
                _normalised(relation.source_type),
                _normalised(relation.predicate),
                _normalised(relation.target_type),
            )
            for relation in self.relations
        )
        canonical = "\x1f".join(
            (self.name, *("\x1e".join(rule) for rule in normalised_rules)),
        )
        return sha256(canonical.encode("utf-8")).hexdigest()[:32]

    def admits(self, *, source_type: str, predicate: str, target_type: str) -> bool:
        """Whether some rule states exactly this arrangement, case- and space-insensitively.

        Checks the triple as a unit rather than each part against its own vocabulary — the whole
        reason this schema is built from rules and not two flat lists. See the module docstring's
        `Method wrote Person` example.
        """
        candidate = (
            _normalised(source_type),
            _normalised(predicate),
            _normalised(target_type),
        )
        return any(
            (
                _normalised(relation.source_type),
                _normalised(relation.predicate),
                _normalised(relation.target_type),
            )
            == candidate
            for relation in self.relations
        )


class ObservedTriple(BaseModel):
    """One `(source_type, predicate, target_type)` a corpus's own facts already produced, and how
    many times. `propose_schema`'s only input — see that function and the module docstring's
    paragraph on why proposing is a measurement.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_type: str
    predicate: str
    target_type: str
    count: int = Field(ge=1)


class EmptyCorpusError(WeftError):
    """`propose_schema` found nothing at or above `min_count` to propose from.

    A `WeftError` — so `weft_cli`'s `except WeftError` maps it to a diagnosable exit the same way
    every other pack failure is mapped — and, because nothing else in this pack's public surface
    raises a bare `ValueError` for "these arguments produce nothing" and a direct caller of this
    pure function reasonably expects that ordinary idiom, also a `ValueError`. Printing an empty
    schema instead would invite an operator to activate one that admits nothing and drops every
    fact the corpus holds; refusing here is cheaper than that mistake.
    """


class MalformedSchemaFileError(WeftError):
    """`load_schema`'s file is missing, is not TOML, or does not validate as a `GraphSchema`.

    A curated schema is hand-edited, so a malformed file is the ordinary case here rather than the
    exotic one `weft_cli.registry_bootstrap.ConfigFileError` treats `weft.toml` as. The message
    always names the path, because an operator with more than one curated file needs to know which
    one — see `load_schema`.
    """


#: The message every path through `propose_schema`'s empty-result case shares, save the `min_count`
#: it was actually called with.
_PROPOSE_NO_FACTS_TEMPLATE: Final[str] = (
    "weft_kg has no facts to propose a schema from: nothing in this corpus was extracted at or "
    "above min_count={min_count}. Index a corpus through a rung that names the llm-facts stage — "
    "`weft index <path> --pipeline index-with-facts` is the shipped one — and run this again. "
    "A corpus built with `index-with-cooccurrence` reaches this too: a schema constrains "
    "(source_type, predicate, target_type), and a co-occurrence edge has none of the three."
)


#: The other half of that case, and the one a real corpus reaches first: facts exist, and none of
#: them cleared the bar. The remedy is the knob, never the corpus — see `propose_schema`'s own
#: comment for why one message for both causes was wrong advice half the time.
_PROPOSE_BELOW_THRESHOLD_TEMPLATE: Final[str] = (
    "weft_kg found {observed} distinct arrangement(s) in this corpus and none of them was seen "
    "at least {min_count} time(s), so there is nothing to propose at that threshold. Lower it — "
    "`weft graph propose --min-count 1` proposes from everything the corpus wrote — or index "
    "more of the corpus so the arrangements worth keeping recur."
)


def propose_schema(
    observed: Sequence[ObservedTriple], *, name: str, min_count: int = 1
) -> GraphSchema:
    """Turn what a corpus's own facts already produced into a schema an operator can curate.

    Every observed triple at or above `min_count` becomes a `RelationRule`, ordered by `count`
    descending so the first rule an operator reads is the most load-bearing one to keep or cut;
    ties are broken by the normalised triple itself, so two runs over the identical corpus agree
    on an order rather than depending on `observed`'s own incoming order. Raises
    `EmptyCorpusError` — naming what to run first — when nothing survives, rather than returning a
    schema that admits nothing; see that error's own docstring and the module docstring's
    "measurement, not opinion" paragraph for why this counts and orders rather than guessing.
    """
    survivors = [triple for triple in observed if triple.count >= min_count]
    if not survivors:
        # **Two causes, two remedies — found by running the binary at `11.11`.** A corpus that
        # produced nothing needs indexing; a corpus whose every arrangement fell below the bar
        # needs a lower bar, and telling that operator to index is advice for a problem they do
        # not have. `L5.9`'s distinction — *I did not find it* is not *it is not there* — applied
        # to a refusal's remedy rather than to a return value.
        raise EmptyCorpusError(
            _PROPOSE_NO_FACTS_TEMPLATE.format(min_count=min_count)
            if not observed
            else _PROPOSE_BELOW_THRESHOLD_TEMPLATE.format(
                observed=len(observed), min_count=min_count
            ),
            pack="weft-rag",
        )
    survivors.sort(
        key=lambda triple: (
            -triple.count,
            _normalised(triple.source_type),
            _normalised(triple.predicate),
            _normalised(triple.target_type),
        )
    )
    relations = tuple(
        RelationRule(
            source_type=triple.source_type,
            predicate=triple.predicate,
            target_type=triple.target_type,
        )
        for triple in survivors
    )
    return GraphSchema(name=name, relations=relations)


def load_schema(path: Path) -> GraphSchema:
    """Read a curated schema from a TOML file and validate it into a `GraphSchema`.

    The one place this module touches a filesystem. Any failure — the file is missing, is not
    TOML, or parses but fails `GraphSchema`'s own validation (an unknown `schema_version` among
    them) — is re-raised as `MalformedSchemaFileError` naming `path` and the underlying reason,
    the same "one file, one reader, no bare stdlib traceback out of an operator command" discipline
    `weft_cli.registry_bootstrap.document_at` already applies to `weft.toml` itself.
    """
    try:
        with path.open("rb") as handle:
            document = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise MalformedSchemaFileError(f"{path} is not valid TOML: {exc}", pack="weft-rag") from exc
    except OSError as exc:
        raise MalformedSchemaFileError(f"{path} could not be read: {exc}", pack="weft-rag") from exc
    try:
        return GraphSchema.model_validate(document)
    except ValidationError as exc:
        raise MalformedSchemaFileError(
            f"{path} does not hold a valid curated graph schema: {exc}", pack="weft-rag"
        ) from exc
