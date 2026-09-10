"""A schema an operator curates, and what it admits. Ledger **11.11**.

Mirrors `packages/weft-rag/src/weft_kg/schema.py` — the pure half: the model a curated file
validates into, what it derives, what it admits, and the proposal built from what a corpus already
produced. No container and no model; `test_graph_commands.py` is the half that reads and writes.

**Typed relation rules, not two flat lists — settled with the owner 2026-09-10.** A schema of
entity types and predicates catches an invented word and admits any arrangement of approved ones,
which is most of what a wrong extraction looks like: `Method wrote Person` uses nothing an operator
did not approve. A rule is the triple `(source_type, predicate, target_type)`, so the arrangement is
the thing checked, and the vocabularies are **derived** from the rules rather than listed beside
them — two lists that can disagree with the rules they describe is the shape `docs/README.md` opens
by refusing.

**The version is a field, never a `ClassVar`.** `S5`: a persisted schema carries its version in the
stored bytes, because at the read site the pack that wrote it may not be the one installed. A
curated schema is a file in somebody's repository, read back by whatever `weft-rag` is installed
then — the most literal instance of that rule this project has. `Filter.version` is the worked
example of getting it wrong (pydantic never serialises a `ClassVar`, so a stored filter has always
carried no version at all) and `ReconcileReport.schema_version` the example of getting it right.

**`propose` is a measurement, not an opinion** — also settled with the owner. It aggregates the
`(source_type, predicate, target_type)` triples `llm-facts` already wrote and ranks them, so what
an operator curates is the shape their own corpus produced. A model asked to generalise would give
a tidier vocabulary and a worse artefact: the operator would be editing a model's guess about their
corpus rather than a measurement of it, and `propose` would cost a credential.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from weft_kg.schema import (
    KG_CURATED_SCHEMA_VERSION,
    EmptyCorpusError,
    GraphSchema,
    ObservedTriple,
    RelationRule,
    propose_schema,
)


def _schema(*rules: tuple[str, str, str], name: str = "papers") -> GraphSchema:
    return GraphSchema(
        name=name,
        relations=tuple(
            RelationRule(source_type=source, predicate=predicate, target_type=target)
            for source, predicate, target in rules
        ),
    )


def test_the_vocabularies_are_derived_from_the_rules_never_listed_beside_them() -> None:
    """Two lists and a set of rules that can disagree is exactly the drift this project opens by
    refusing. Asserted as a derivation so a schema cannot name a type no rule uses, or use one it
    forgot to name.
    """
    # Arrange
    schema = _schema(("person", "wrote", "method"), ("method", "extends", "method"))

    # Act / Assert
    assert schema.entity_types == frozenset({"person", "method"})
    assert schema.predicates == frozenset({"wrote", "extends"})


def test_a_triple_the_schema_states_is_admitted() -> None:
    """The happy path, and the only one an extraction should survive under a schema."""
    # Arrange
    schema = _schema(("person", "wrote", "method"))

    # Act / Assert
    assert schema.admits(source_type="person", predicate="wrote", target_type="method")


def test_an_arrangement_the_schema_does_not_state_is_refused() -> None:
    """**The case flat vocabularies cannot see, and the reason the shape is a rule.**
    `method wrote person` uses only approved words — an entity type the operator listed, a
    predicate they listed — and says something impossible. A schema that admitted it would be
    catching typos and calling it structure.
    """
    # Arrange
    schema = _schema(("person", "wrote", "method"))

    # Act / Assert
    assert not schema.admits(source_type="method", predicate="wrote", target_type="person")


def test_a_type_no_rule_names_is_refused() -> None:
    """The case flat vocabularies *do* catch, kept because it is the common one: a model
    inventing `organisation` where the operator approved `person` and `method`.
    """
    # Arrange
    schema = _schema(("person", "wrote", "method"))

    # Act / Assert
    assert not schema.admits(source_type="organisation", predicate="wrote", target_type="method")


def test_matching_is_case_and_space_insensitive() -> None:
    """A model writes `Person` where the schema says `person`, and the corpus is no different for
    it. Refusing on capitalisation would make `off_schema_dropped` a count of formatting rather
    than of structure, which is the number nobody could act on.
    """
    # Arrange
    schema = _schema(("person", "wrote", "method"))

    # Act / Assert
    assert schema.admits(source_type="Person", predicate="  WROTE ", target_type="Method")


def test_a_schema_carries_its_version_in_its_own_fields() -> None:
    """`S5`, at its most literal: this model is written to a file in somebody's repository and
    read back by whatever `weft-rag` is installed then. A `ClassVar` would be read off the
    importing module and could never disagree with it — `Filter.version`'s recorded mistake.
    """
    # Act
    dumped = _schema(("person", "wrote", "method")).model_dump(mode="json")

    # Assert
    assert dumped["schema_version"] == KG_CURATED_SCHEMA_VERSION
    assert "schema_version" in GraphSchema.model_fields


def test_a_schema_with_no_rules_is_refused_at_construction() -> None:
    """An empty schema admits nothing, so activating one would drop every fact in the corpus and
    report it as a schema working. Refused where it is written, naming the field.
    """
    # Act / Assert
    with pytest.raises(ValidationError):
        GraphSchema(name="empty", relations=())


def test_a_schema_file_from_the_future_is_refused_rather_than_read() -> None:
    """Upgrade-or-refuse, the rule every persisted surface in this tree follows. A file written
    by a later `weft-rag` may mean something different by the same field names, and reading it
    anyway produces a plausible graph over the wrong constraint.
    """
    # Act / Assert
    with pytest.raises(ValidationError, match="schema_version"):
        GraphSchema(
            name="papers",
            schema_version="9.0.0",
            relations=(RelationRule(source_type="a", predicate="b", target_type="c"),),
        )


def test_the_identity_is_a_function_of_the_rules_not_of_their_order() -> None:
    """The identity is what `activate` writes into the corpus and what every fact carries, so it
    has to answer *is this the same schema* — and a curated file's rules are a set an operator
    reorders while editing. Two files stating the same rules in different orders are one schema;
    a file that gained a rule is not.
    """
    # Arrange
    one = _schema(("person", "wrote", "method"), ("method", "extends", "method"))
    reordered = _schema(("method", "extends", "method"), ("person", "wrote", "method"))
    widened = _schema(
        ("person", "wrote", "method"), ("method", "extends", "method"), ("person", "cited", "paper")
    )

    # Act / Assert
    assert one.identity == reordered.identity
    assert one.identity != widened.identity


def test_the_identity_changes_when_the_name_does() -> None:
    """`weft graph show` prints which schemas a corpus holds, and two schemas an operator gave
    different names are two schemas to them whatever the rules say. The name is theirs; the
    identity must not quietly merge them.
    """
    # Act / Assert
    assert (
        _schema(("person", "wrote", "method"), name="papers").identity
        != _schema(("person", "wrote", "method"), name="reports").identity
    )


def test_a_proposal_is_the_shape_the_corpus_actually_produced() -> None:
    """`propose` is a measurement. Every triple the corpus wrote becomes a rule, ordered by how
    often the corpus wrote it, so the first thing an operator reads is the most load-bearing
    thing to keep or cut.
    """
    # Arrange
    observed = (
        ObservedTriple(source_type="person", predicate="wrote", target_type="method", count=9),
        ObservedTriple(source_type="method", predicate="extends", target_type="method", count=4),
    )

    # Act
    proposed = propose_schema(observed, name="papers")

    # Assert
    assert [rule.predicate for rule in proposed.relations] == ["wrote", "extends"]
    assert proposed.name == "papers"


def test_a_proposal_can_drop_a_long_tail_and_the_control_disagrees() -> None:
    """Requirement 6, and `L9.58`: the threshold is an operator's number and has to be shown to
    change something. A corpus of any size produces a tail of triples seen once, and a proposal
    that listed all of them would be a transcript rather than a schema.
    """
    # Arrange
    observed = (
        ObservedTriple(source_type="person", predicate="wrote", target_type="method", count=9),
        ObservedTriple(source_type="person", predicate="mused", target_type="thing", count=1),
    )

    # Act / Assert
    assert len(propose_schema(observed, name="papers", min_count=1).relations) == 2
    assert len(propose_schema(observed, name="papers", min_count=2).relations) == 1


def test_a_proposal_from_a_corpus_that_produced_nothing_is_refused() -> None:
    """There is nothing to propose from an empty graph, and printing an empty schema would
    invite an operator to activate one that admits nothing. Refused, saying what to run first.
    """
    # Act / Assert
    with pytest.raises(EmptyCorpusError, match="no facts"):
        propose_schema((), name="papers")


def test_a_threshold_that_hid_everything_says_so_rather_than_blaming_the_corpus() -> None:
    """**Found by running the binary.** A two-document corpus indexed through `index-with-facts`
    produced eleven distinct arrangements, every one of them seen once, and `propose` at its
    default `min_count=2` refused with *"index a corpus … and run this again"* — telling an
    operator to do the thing they had just done.

    Two different causes wearing one message is the shape `L5.9` is about one layer up: an empty
    result meaning *I did not find it* and *it is not there* are different facts, and a remedy
    written for one is wrong advice for the other. The corpus is empty, or the threshold hid it;
    the refusal has to say which, and the second must name the knob.
    """
    # Arrange — the corpus produced something; nothing clears the bar.
    observed = (
        ObservedTriple(source_type="person", predicate="wrote", target_type="method", count=1),
    )

    # Act / Assert
    with pytest.raises(EmptyCorpusError) as caught:
        propose_schema(observed, name="papers", min_count=2)
    message = str(caught.value)
    assert "1 distinct" in message, "the refusal does not say what the corpus did produce"
    assert "--min-count" in message, (
        "the refusal names no knob — an operator types a flag, not a Python parameter"
    )
    assert "index a corpus" not in message.lower(), (
        "the refusal tells an operator to index a corpus they have already indexed"
    )
