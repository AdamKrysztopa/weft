"""Task 43.25: the lifecycle soak's pure functions — what it writes, reads and calls a violation."""

from __future__ import annotations

import tomllib

import soak_layers
from soak_layers import Backend, Generation, Outcome, Snapshot, Source, StoredNode


def _node(
    node_id: str,
    *,
    sources: tuple[str, ...] = ("a",),
    parents: tuple[str, ...] = (),
    generations: tuple[str, ...] = ("",),
    summary: bool = False,
) -> StoredNode:
    return StoredNode(
        id=node_id,
        sources=frozenset(sources),
        parents=parents,
        generations=frozenset(generations),
        summary=summary,
        checkpoint=False,
    )


def _snapshot(
    *,
    generations: tuple[Generation, ...] = (),
    statuses: tuple[str, ...] = ("active", "active"),
    nodes: tuple[StoredNode, ...] = (),
) -> Snapshot:
    sources = tuple(
        Source(id=name, layers={soak_layers.LAYER: status})
        for name, status in zip("ab", statuses, strict=False)
    )
    return Snapshot(generations=generations, sources=sources, nodes=nodes)


def _gen(gid: str, status: str) -> Generation:
    return Generation(id=gid, layer=soak_layers.LAYER, status=status)


def _outcome(text: str) -> Outcome:
    return Outcome(argv=("index",), exit_code=0, stdout=text, stderr="")


def test_the_configuration_names_no_paid_provider_and_the_run_s_own_store() -> None:
    qdrant = Backend(kind="qdrant", database="weft_soak_qdrant_1")

    config = tomllib.loads(soak_layers.weft_toml(qdrant))

    assert {role["provider"] for role in config["llm"]["roles"].values()} == {"scripted"}
    assert config["services"] == {"store": "qdrant", "embed": "hash"}
    assert config["packs"]["qdrant"]["collection"] == "weft_soak_qdrant_1"
    assert config["packs"]["store"]["dsn"].endswith("/weft_soak_qdrant_1")


def test_a_qdrant_run_owns_every_companion_collection_and_a_pgvector_run_owns_none() -> None:
    assert Backend(kind="qdrant", database="x").collections == (
        "x",
        "x__sources",
        "x__targets",
        "x__generations",
    )
    assert Backend(kind="pgvector", database="x").collections == ()


def test_the_layer_document_leaves_the_shipped_concurrency_unpinned() -> None:
    assert "max_concurrent_summaries" not in soak_layers.layer_document()


def test_a_join_line_is_parsed_and_a_missing_one_is_none() -> None:
    assert soak_layers.joined("layer 'raptor-corpus': joined 2 leaves, 1 unassigned") == (2, 1)
    assert soak_layers.joined("6 documents: 1 indexed") is None


def test_reclaimed_counts_are_summed_over_every_line() -> None:
    text = (
        "layer 'raptor-corpus': reclaimed 2 node(s) from withdrawn generations\n"
        "  pgvector: reclaimed 3 node(s) from withdrawn generations\n"
    )

    assert soak_layers.reclaimed(text) == 5


def test_only_spans_of_the_named_role_are_counted() -> None:
    stdout = '{\n "name": "llm:index"\n}\nnoise\n{\n "name": "llm:generate"\n}\n{ broken\n'

    assert soak_layers.llm_spans(stdout) == 1


def test_a_clean_store_breaks_no_invariant() -> None:
    snap = _snapshot(
        generations=(_gen("g1", "published"),),
        nodes=(_node("c1"), _node("s1", parents=("c1",), generations=("g1",), summary=True)),
    )

    assert soak_layers.invariants(snap) == []


def test_two_published_trees_and_a_building_one_are_each_named() -> None:
    snap = _snapshot(
        generations=(_gen("g1", "published"), _gen("g2", "published"), _gen("g3", "building"))
    )

    problems = soak_layers.invariants(snap)

    assert any("more than one published generation" in p for p in problems)
    assert any("left building: ['g3']" in p for p in problems)


def test_a_node_naming_a_deleted_source_is_named() -> None:
    snap = _snapshot(nodes=(_node("c9", sources=("gone",)),))

    assert any("names sources no record holds: ['gone']" in p for p in soak_layers.invariants(snap))


def test_a_withdrawn_tree_survives_the_command_only_when_that_command_withdrew_it() -> None:
    snap = _snapshot(
        generations=(_gen("g1", "withdrawn"),),
        statuses=("stale", "stale"),
        nodes=(_node("s1", generations=("g1",), summary=True),),
    )

    assert any("survives only in withdrawn" in p for p in soak_layers.invariants(snap))
    assert soak_layers.invariants(snap, spared=frozenset({"g1"})) == []


def test_a_base_node_also_held_by_a_withdrawn_generation_is_not_a_survivor() -> None:
    snap = _snapshot(
        generations=(_gen("g1", "withdrawn"),), nodes=(_node("c1", generations=("", "g1")),)
    )

    assert soak_layers.invariants(snap) == []


def test_a_published_summary_missing_a_parent_breaks_an_active_layer_only() -> None:
    nodes = (_node("s1", parents=("gone",), generations=("g1",), summary=True),)
    gens = (_gen("g1", "published"),)

    active = soak_layers.invariants(_snapshot(generations=gens, nodes=nodes))
    stale = soak_layers.invariants(_snapshot(generations=gens, statuses=("stale",), nodes=nodes))

    assert any("missing parent" in p for p in active)
    assert not any("missing parent" in p for p in stale)


def test_a_join_of_nothing_that_moves_the_tree_is_a_violation() -> None:
    before = _snapshot(
        generations=(_gen("g1", "published"),),
        nodes=tuple(_node(f"s{i}", generations=("g1",), summary=True) for i in range(3)),
    )
    after = _snapshot(
        generations=(_gen("g1", "withdrawn"), _gen("g2", "published")),
        nodes=tuple(_node(f"s{i}", generations=("g1", "g2"), summary=True) for i in range(2)),
    )
    line = _outcome("layer 'raptor-corpus': joined 0 leaves, 1 unassigned")

    problems = soak_layers.check_join(before, after, line)

    assert problems == [
        "joined 0 leaves, yet the published tree moved: 3 -> 2 summaries, 1 gone, 0 new"
    ]


def test_a_join_that_carries_its_whole_tree_forward_passes() -> None:
    before = _snapshot(
        generations=(_gen("g1", "published"),),
        nodes=(_node("s1", generations=("g1",), summary=True),),
    )
    after = _snapshot(
        generations=(_gen("g1", "withdrawn"), _gen("g2", "published")),
        nodes=(_node("s1", generations=("g1", "g2"), summary=True),),
    )

    assert soak_layers.check_join(before, after, _outcome("joined 0 leaves, 0 unassigned")) == [
        "no `joined N leaves, M unassigned` line in: joined 0 leaves, 0 unassigned"
    ]
    assert (
        soak_layers.check_join(
            before, after, _outcome("layer 'raptor-corpus': joined 0 leaves, 0 unassigned")
        )
        == []
    )


def test_a_layer_stale_on_one_source_only_is_not_stale_everywhere() -> None:
    assert soak_layers.check_stale(_snapshot(statuses=("stale", "stale"))) == []
    assert soak_layers.check_stale(_snapshot(statuses=("stale", "active"))) != []


def test_each_read_is_named_by_the_single_tree_it_saw() -> None:
    old, new = frozenset({"a", "b"}), frozenset({"b", "c"})
    reads: list[frozenset[str]] = [
        old,
        new,
        frozenset({"a", "c"}),
        frozenset({"b"}),
        frozenset(),
        frozenset({"z"}),
    ]

    assert soak_layers.classify_reads(old, new, reads) == "ON?=x?"


def test_the_corpus_scales_every_topic_and_gives_each_file_its_own_text() -> None:
    files = soak_layers.corpus(2)

    assert len(files) == 2 * sum(len(names) for names in soak_layers.TOPICS.values())
    assert len(set(files.values())) == len(files)


def test_a_revision_changes_a_document_s_bytes() -> None:
    assert soak_layers.document("elements", "radon") != soak_layers.document(
        "elements", "radon", revision=1
    )
