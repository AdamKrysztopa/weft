"""Two mentions of one thing become one entity, deterministically. Ledger **11.8**.

Mirrors `packages/weft-rag/src/weft_kg/resolution.py` — the **pure** half of the resolution pass:
no I/O, no model, no async. The SQL half lives in `weft_kg.store` and is exercised against the
real container in `test_store.py`, because a resolution that agrees with a double and disagrees
with Postgres is the failure `docs/internal/lessons.md` L6.14 records.

**Carried prior work, under `NOTICE` case 2.** The initialism rule, the Schwartz–Hearst
definition patterns, the acronym-collision guard and the union-find are the project owner's own
`graph-study`, marked in place in `weft_kg/resolution.py` and enumerated on `README.md` beside the
atomicity filter `11.7` carried. What is Weft's own here is the *shape*: the donor takes names and
embeddings and computes similarity itself; this takes the pairs Postgres already found and does
only what a database cannot — the transitive closure and the choice of representative.

**Why the representative is lexicographic and not, say, the most-mentioned surface form.** The
task's own line: *the canonical id is a function of the **set**, not of arrival order*. A count
depends on what has been indexed so far, so the same cluster would canonicalise differently before
and after a second document arrived, and every fact already written against the old id would point
at nothing. `min()` over the members is a function of the set alone, which is what makes a second
run unable to change what a first one decided.

**The two failure modes the blend guards against, one in each direction.** They are why neither
signal is used alone, and both are stated on `resolve_clusters` where a reader changing a weight
will meet them. *(a)* A **degenerate embedder** — the donor's own recorded finding — pushes every
cosine towards 1.0, so a vector-only rule merges the whole corpus into one entity; the lexical term
is what vetoes that. *(b)* **Lexical similarity alone** merges names that look alike and are not:
`adRAP` and `adRAG` differ by one character and are two techniques, and trigram similarity cannot
tell them apart; the vector term is what vetoes that. This file asserts both directions.
"""

from __future__ import annotations

import pytest

from weft_kg.resolution import (
    acronym_definitions,
    initialism,
    initialism_candidates,
    is_short_form,
    resolve_clusters,
)


def test_a_name_alone_is_its_own_representative() -> None:
    """The floor: with nothing to merge, resolution is the identity. Without this, every
    assertion below is satisfied by a pass that collapses the corpus into one entity.
    """
    # Act
    resolved = resolve_clusters(["adRAP", "Chucri"], similar_pairs=())

    # Assert
    assert resolved == {"adRAP": "adRAP", "Chucri": "Chucri"}


def test_a_merged_pair_takes_the_lexicographically_smaller_name() -> None:
    """The representative is a function of the set. `ADRAP` sorts before `adRAP` because
    upper-case letters sort first, and that is a property of the *members*, not of which one
    the database happened to return first.
    """
    # Act
    resolved = resolve_clusters(["adRAP", "ADRAP"], similar_pairs=[("adRAP", "ADRAP")])

    # Assert
    assert resolved == {"adRAP": "ADRAP", "ADRAP": "ADRAP"}


def test_the_answer_does_not_depend_on_the_order_the_pairs_arrive_in() -> None:
    """*Not of arrival order* is the clause with teeth, and union-find is what delivers it.

    The same three names and the same two merges, offered in two orders — a database is free to
    return either, and a canonical id that moved between them would re-point every fact already
    written against it.
    """
    # Arrange
    names = ["Chucri", "C. Chucri", "Chucri, C."]
    forward = [("Chucri", "C. Chucri"), ("C. Chucri", "Chucri, C.")]
    backward = [("Chucri, C.", "C. Chucri"), ("C. Chucri", "Chucri")]

    # Act
    first = resolve_clusters(names, similar_pairs=forward)
    second = resolve_clusters(list(reversed(names)), similar_pairs=backward)

    # Assert — one component of three, and both orders agree about its name.
    assert first == second
    assert set(first.values()) == {"C. Chucri"}


def test_merging_is_transitive_even_where_no_pair_was_offered() -> None:
    """Union-find rather than a pairwise mapping, and this is the case that tells them apart.

    `a~b` and `b~c` were found; `a~c` was not, and need not have been — below the threshold, or
    simply not returned. A pass that only honoured the pairs it was handed would leave `a` and
    `c` as two entities that both mean the thing `b` means.
    """
    # Act
    resolved = resolve_clusters(
        ["alpha", "beta", "gamma"], similar_pairs=[("alpha", "beta"), ("beta", "gamma")]
    )

    # Assert
    assert set(resolved.values()) == {"alpha"}


def test_a_second_run_over_the_first_run_s_own_answer_changes_nothing() -> None:
    """Idempotence, asserted as *a second run cannot change it* rather than assumed from purity.

    The pass runs on every `weft reconcile`, so this is not a nicety: a resolution that moved
    each time would re-point every alias on every pass and make the canonical id a fact about
    how many times somebody had run the command.
    """
    # Arrange
    names = ["adRAP", "ADRAP", "Adaptive RAG"]
    pairs = [("adRAP", "ADRAP"), ("ADRAP", "Adaptive RAG")]

    # Act
    once = resolve_clusters(names, similar_pairs=pairs)
    twice = resolve_clusters(sorted(set(once.values()) | set(names)), similar_pairs=pairs)

    # Assert
    assert {name: twice[once[name]] for name in names} == once


def test_a_pair_the_database_did_not_return_is_not_merged() -> None:
    """The blend's second failure mode, stated as a test rather than as a caveat.

    `adRAP` and `adRAG` differ by one character; trigram similarity alone reads them as the same
    name and they are two techniques. The vector term is what vetoes it, and by the time this
    function runs that veto has already happened in the query — so what this asserts is that the
    pure half adds no merges of its own on top of what it was given.
    """
    # Act
    resolved = resolve_clusters(["adRAP", "adRAG"], similar_pairs=())

    # Assert
    assert resolved == {"adRAP": "adRAP", "adRAG": "adRAG"}


# --- the acronym signals, and their opposite precision arguments ---------------------------


def test_an_initialism_skips_the_words_a_name_does_not_turn_on() -> None:
    """Carried rule. *Department of Health and Human Services* is `DHHS`, not `DOHAHS` — a
    reader writing the short form drops the function words, so a rule that kept them would match
    nothing anybody actually writes.
    """
    # Act / Assert
    assert initialism("Federal Aviation Administration") == "FAA"
    assert initialism("Department of Health and Human Services") == "DHHS"
    assert initialism("Reciprocal Rank Fusion") == "RRF"


def test_a_short_form_is_recognised_by_shape_rather_than_by_a_list() -> None:
    """The gate on signal 3: only an all-caps run of 2–10 characters is offered as a short form.

    A list of known acronyms would be a corpus-specific asset this pack cannot ship, and would
    silently do nothing on the first corpus nobody wrote it for.
    """
    # Act / Assert
    assert is_short_form("RRF")
    assert not is_short_form("Reciprocal")
    assert not is_short_form("R")
    assert not is_short_form("RECIPROCAL RANK FUSION")


def test_a_definition_the_text_states_is_the_high_precision_signal() -> None:
    """Signal 2, and the argument for trusting it: the *text itself* defined the pair.

    Both orders are read, because both are ordinary in prose, and a pair is returned only when
    the long form's own initials produce the short form — so a parenthesis that happens to follow
    a capitalised word is not mistaken for a definition.
    """
    # Act
    forward = acronym_definitions("We use Reciprocal Rank Fusion (RRF) to merge the lists.")
    reverse = acronym_definitions("We use RRF (Reciprocal Rank Fusion) to merge the lists.")

    # Assert
    assert forward == (("RRF", "Reciprocal Rank Fusion"),)
    assert reverse == (("RRF", "Reciprocal Rank Fusion"),)


def test_a_parenthesis_that_is_not_a_definition_is_not_read_as_one() -> None:
    """The precision half of signal 2. Prose is full of capitalised words before parentheses,
    and a signal that fired on all of them would merge unrelated entities with high confidence —
    which is worse than a signal that fires rarely, because it is trusted.
    """
    # Act
    found = acronym_definitions("The Warsaw Institute (founded 1951) funded the work.")

    # Assert
    assert found == ()


def test_a_definition_is_reported_once_however_often_the_text_repeats_it() -> None:
    """A paper defines its acronym once and uses it throughout; some define it again per
    section. The signal is *that the pair was defined*, so a count would be a fact about the
    prose rather than about the entity.
    """
    # Act
    found = acronym_definitions(
        "Reciprocal Rank Fusion (RRF) merges lists. Reciprocal Rank Fusion (RRF) again."
    )

    # Assert
    assert found == (("RRF", "Reciprocal Rank Fusion"),)


def test_a_definition_the_text_states_merges_the_two_names() -> None:
    """Signal 2 reaching the clustering, matched case-insensitively at both ends — a paper that
    writes `adRAP` in one sentence and `ADRAP` in the next has defined one thing.
    """
    # Act
    resolved = resolve_clusters(
        ["RRF", "reciprocal rank fusion"],
        similar_pairs=(),
        acronym_definitions=[("RRF", "Reciprocal Rank Fusion")],
    )

    # Assert
    assert set(resolved.values()) == {"RRF"}


def test_an_initialism_merges_only_when_the_vectors_agree_it_is_plausible() -> None:
    """Signal 3, and its gate. `RRF` *is* the initialism of `Reciprocal Rank Fusion`, and it is
    equally the initialism of `Rapid Response Force` — the letters alone cannot say which, so a
    cosine floor is what stops the rule from merging on spelling.
    """
    # Act
    merged = resolve_clusters(
        ["RRF", "Reciprocal Rank Fusion"],
        similar_pairs=(),
        cosines={("RRF", "Reciprocal Rank Fusion"): 0.8},
    )
    refused = resolve_clusters(
        ["RRF", "Reciprocal Rank Fusion"],
        similar_pairs=(),
        cosines={("RRF", "Reciprocal Rank Fusion"): 0.05},
    )

    # Assert — the control disagrees with the subject, so the floor is proven to do something.
    assert set(merged.values()) == {"RRF"}
    assert set(refused.values()) == {"RRF", "Reciprocal Rank Fusion"}


def test_a_short_form_matching_two_long_forms_merges_with_neither() -> None:
    """The acronym-collision guard, and the argument that makes it worth its cost.

    `RRF` expands to both names below, and both clear the floor. Picking either would be picking
    by iteration order — the one thing this task's line forbids — and merging all three would
    assert that two unrelated things are one. Abstaining leaves three entities, which is wrong in
    a way a reader can see, rather than wrong in a way that reads as a finding.
    """
    # Act
    resolved = resolve_clusters(
        ["RRF", "Reciprocal Rank Fusion", "Rapid Response Force"],
        similar_pairs=(),
        cosines={
            ("RRF", "Reciprocal Rank Fusion"): 0.8,
            ("RRF", "Rapid Response Force"): 0.8,
        },
    )

    # Assert
    assert len(set(resolved.values())) == 3


def test_an_initialism_with_no_cosine_at_all_is_not_merged() -> None:
    """A missing vector means *not known*, never *close enough*.

    A pair whose alias rows carry no embedding cannot clear a floor, and treating an absent cosine
    as passing would make signal 3 fire hardest exactly where there is least evidence — the inverse
    of what a gate is for. `docs/internal/lessons.md` L5.9's rule for an empty collection, applied
    to a missing number.
    """
    # Act
    resolved = resolve_clusters(["RRF", "Reciprocal Rank Fusion"], similar_pairs=(), cosines={})

    # Assert
    assert set(resolved.values()) == {"RRF", "Reciprocal Rank Fusion"}


def test_the_cosine_floor_is_a_parameter_and_the_control_disagrees() -> None:
    """Requirement 6, and `L9.58`: a parameterised control must be shown to change something."""
    # Arrange
    names = ["RRF", "Reciprocal Rank Fusion"]
    cosines = {("RRF", "Reciprocal Rank Fusion"): 0.3}

    # Act / Assert
    assert len(set(resolve_clusters(names, similar_pairs=(), cosines=cosines).values())) == 2
    assert (
        len(
            set(
                resolve_clusters(
                    names, similar_pairs=(), cosines=cosines, cosine_floor=0.2
                ).values()
            )
        )
        == 1
    )


def test_a_pair_naming_something_absent_is_refused_rather_than_invented() -> None:
    """A merge names two surface forms; one the caller did not list is a caller mistake, and
    silently adding it would put an entity in the graph that no mention supports.
    """
    # Act / Assert
    with pytest.raises(ValueError, match="ghost"):
        resolve_clusters(["adRAP"], similar_pairs=[("adRAP", "ghost")])


# --- ledger task 11.9: the cosines signal 3 needs, without the corpus-sized fetch ---
#
# `11.8` fetched **every** alias pair's cosine and handed the whole map to `resolve_clusters`,
# which is `O(corpus²)` in memory and was recorded on `_run_resolution_pass`'s own docstring as a
# cost belonging to this task rather than ahead of it. Signal 3 only ever looks up the pairs where
# one name has a short form's shape and the other's initials spell it, and that set is a function
# of the names alone — so it can be computed first and the database asked for exactly those.
# `initialism_candidates` is that function, published so the store can ask the narrow question and
# `_apply_initialisms` can keep asking the same one.


def test_the_candidate_pairs_are_the_ones_whose_initials_actually_spell_the_short_form() -> None:
    """The narrowing has to be *exact*, not merely smaller: a pair signal 3 would have consulted
    and this function omits is a merge that silently stops happening.
    """
    # Arrange — one real pair, one short form whose letters match nothing, one ordinary name.
    names = ["RRF", "Reciprocal Rank Fusion", "adRAP", "DHHS"]

    # Act
    candidates = initialism_candidates(names)

    # Assert
    assert candidates == (("RRF", "Reciprocal Rank Fusion"),)


def test_two_names_of_the_same_shape_are_never_a_candidate_pair() -> None:
    """Signal 3 is *short form and its expansion*; two acronyms, or two ordinary names, offer it
    nothing to gate and would only widen the fetch this function exists to narrow.
    """
    # Act / Assert
    assert initialism_candidates(["RRF", "DHHS"]) == ()
    assert initialism_candidates(["Reciprocal Rank Fusion", "Rapid Response Force"]) == ()


def test_resolving_with_only_the_candidate_cosines_matches_resolving_with_every_pair() -> None:
    """The property that licenses the store to stop fetching the whole matrix — asserted as an
    equality between two resolutions rather than as a claim about which lookups happen, because
    what matters is the clustering, not the map.

    The wide map deliberately carries a high cosine for a pair signal 3 has no interest in, so a
    `resolve_clusters` that consulted cosines anywhere else would make the two sides disagree.
    """
    # Arrange
    names = ["RRF", "Reciprocal Rank Fusion", "adRAP", "adRAG"]
    every_pair = {
        ("RRF", "Reciprocal Rank Fusion"): 0.9,
        ("adRAP", "adRAG"): 0.99,
        ("RRF", "adRAP"): 0.95,
        ("Reciprocal Rank Fusion", "adRAG"): 0.95,
    }
    narrow = {pair: every_pair[pair] for pair in initialism_candidates(names)}

    # Act
    wide_result = resolve_clusters(names, similar_pairs=(), cosines=every_pair)
    narrow_result = resolve_clusters(names, similar_pairs=(), cosines=narrow)

    # Assert
    assert narrow_result == wide_result
    assert narrow_result["RRF"] == narrow_result["Reciprocal Rank Fusion"]
    assert narrow_result["adRAP"] != narrow_result["adRAG"]
