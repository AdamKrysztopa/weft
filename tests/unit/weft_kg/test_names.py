"""What this pack thinks a name looks like — one rule, two callers. Ledger **11.10**.

Mirrors `packages/weft-rag/src/weft_kg/names.py`. Pure, no I/O.

**Published because two things now ask the question.** `11.6`'s `cooccurrence-graph` matched
Title-Case runs in a *chunk* to find entity mentions; `11.10`'s `graph-walk` has to match them in a
*question* to find which entity it names. Those are the same rule, and a pack holding two copies of
it would let a question's notion of a name drift from the corpus's — which fails in the quietest
possible way, as a graph query that matches nothing and looks like a corpus with no answer. So the
regex and the leading-stopword strip move here and `weft_kg.cooccurrence` imports them; every
assertion `test_cooccurrence.py` already makes still holds, unchanged, which is what says the move
was a move.

**`with_subspans` is the retriever's half and not the builder's.** A chunk's mention is written the
way the corpus writes it, so a maximal run is the right candidate there. A question is written by
somebody who may name the entity more briefly than the corpus did — *"what did Dostoevsky write"*
against an entity stored as *Fyodor Dostoevsky* — so the retriever asks about each candidate **and**
its contiguous sub-spans. It stays one database round trip either way, because
`GraphTraversal.entities_by_name` takes the whole sequence, and it cannot invent an entity: every
name is matched exactly against rows the corpus actually produced.
"""

from __future__ import annotations

import pytest

from weft_kg.names import candidate_names, with_subspans


def test_a_title_case_run_is_one_candidate() -> None:
    """The rule `11.6` established, now stated where both callers can read it."""
    # Act
    found = candidate_names("Reciprocal Rank Fusion merges ranked lists.")

    # Assert
    assert found == ("Reciprocal Rank Fusion",)


def test_a_sentence_initial_stopword_is_not_part_of_the_name() -> None:
    """`The Board met` is a board, not a *The Board* — stripped from the front only, because a
    stopword there is a sentence artefact and the pattern only ever matches a run that starts at
    a capital.

    `Tuesday` comes back too, and that is the rule working rather than failing: this matches
    **every** Title-Case run, not the subject of the sentence. What separates a name from a
    weekday is not something a regex can see, and `11.6` shipped the over-generation knowingly —
    `10`'s row for `cooccurrence-graph` says so. The retriever inherits it and it is harmless
    there for a reason worth stating: a candidate is matched **exactly** against entity rows the
    corpus actually produced, so a spurious candidate finds nothing and costs one comparison.
    """
    # Act / Assert
    assert candidate_names("The Board met on Tuesday.") == ("Board", "Tuesday")


def test_a_run_longer_than_the_cap_is_cut_to_the_cap() -> None:
    """Requirement 6's knob, and the control disagrees — `L9.58`."""
    # Act / Assert
    assert candidate_names("New York City Council", max_words=2) == ("New York", "City Council")
    assert candidate_names("New York City Council", max_words=4) == ("New York City Council",)


def test_text_naming_nothing_yields_nothing() -> None:
    """An empty answer here means *this question named no entity*, which the retriever reports
    as a searched-but-empty list rather than as a query it declined — `L5.9` one layer up.
    """
    # Act / Assert
    assert candidate_names("what does the corpus say about all of this?") == ()


def test_a_candidate_carries_its_own_shorter_spans() -> None:
    """The retriever's half: a question saying `Dostoevsky` must reach an entity the corpus
    stored as `Fyodor Dostoevsky`, and the reverse. Longest first, so a caller that stops early
    stops on the most specific match.
    """
    # Act
    expanded = with_subspans(("Fyodor Dostoevsky",))

    # Assert
    assert expanded[0] == "Fyodor Dostoevsky"
    assert set(expanded) == {"Fyodor Dostoevsky", "Fyodor", "Dostoevsky"}


def test_sub_spans_are_contiguous_and_never_reordered() -> None:
    """`Crime and Punishment` may be asked for as `Crime` or as `Punishment`, never as
    `Crime Punishment` — a name is a phrase, and recombining its words would invent one.
    """
    # Act
    expanded = with_subspans(("Saint Petersburg Institute",))

    # Assert
    assert "Saint Petersburg" in expanded
    assert "Petersburg Institute" in expanded
    assert "Saint Institute" not in expanded


def test_expansion_deduplicates_across_candidates() -> None:
    """Two candidates sharing a word must not ask the graph the same name twice: the sequence
    goes straight into one `entities_by_name` call, and a duplicate is a wasted comparison in
    the database rather than a wrong answer — cheap, and still worth not doing.
    """
    # Act
    expanded = with_subspans(("Warsaw Institute", "Warsaw University"))

    # Assert
    assert len(expanded) == len(set(expanded))
    assert expanded.count("Warsaw") == 1


def test_a_cap_below_one_is_refused_rather_than_repaired() -> None:
    """`CooccurrenceSettings` already refuses `max_name_words < 1` at construction, naming the
    field; the function it configures must not silently disagree by returning an empty tuple.
    """
    # Act / Assert
    with pytest.raises(ValueError, match="max_words"):
        candidate_names("Reciprocal Rank Fusion", max_words=0)


def test_a_name_that_does_not_start_with_a_capital_is_not_a_candidate() -> None:
    """**The blind spot, asserted rather than only written down.** The rule matches a run that
    *begins* at a capital, so `adRAP` — a real entity name in this project's own corpus — is
    invisible to it, and a question naming only that entity seeds nothing.

    This is checked here because the alternative is a limitation that lives in a docstring and
    quietly stops being true, in either direction: a future rule that started matching it would
    change what every graph question retrieves with nothing recording the change, and a reader
    choosing this rung deserves the boundary to be a fact rather than a claim. `10`'s row for
    `graph-walk` states the same limitation where an operator meets it.
    """
    # Act / Assert
    assert candidate_names("does adRAP extend raptor?") == ()
    assert "adRAP" not in with_subspans(candidate_names("Did Chucri write adRAP?"))
