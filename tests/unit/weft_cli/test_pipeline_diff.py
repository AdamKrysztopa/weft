"""Unit tests for `weft_cli.pipeline_diff`.

Mirrors `packages/weft-rag/src/weft_cli/pipeline_diff.py`. Task **3.7**'s own exactness
proof: every test here builds `weft_kernel.resolution.ResolvedPipeline` values directly —
no YAML, no registry, no `resolve()` call — because the property under test is that
`diff_resolved` is a structural comparison of two already-resolved values, not a
rendered-text comparison. Covers the happy path (two structurally identical resolutions of
one pipeline diff to `identical=True`), the edge cases of an added/removed/changed stage
and a changed var, and proves the comparison actually distinguishes something.
"""

from weft_cli.pipeline_diff import VarChange, diff_resolved
from weft_kernel.resolution import ResolvedPipeline, ResolvedStage


def _stage(id: str, use: str = "fixed-size", *, distribution: str = "weft-chunk") -> ResolvedStage:
    return ResolvedStage(
        id=id, contract="Chunker", use=use, distribution=distribution, provenance="base"
    )


def test_two_separate_resolutions_of_the_same_pipeline_are_identical() -> None:
    # Arrange — `ResolvedPipeline` is comparable by `==` across two separate calls to
    # resolve() (that model's own docstring); `diff_resolved` must agree with `==`.
    a = ResolvedPipeline(name="base", stages=(_stage("chunk"),))
    b = ResolvedPipeline(name="base", stages=(_stage("chunk"),))

    # Act
    diff = diff_resolved(a, b)

    # Assert
    assert diff.identical
    assert diff.added_stages == ()
    assert diff.removed_stages == ()
    assert diff.changed_stages == ()
    assert diff.var_changes == ()


def test_an_inserted_stage_is_reported_as_added_and_nothing_else() -> None:
    # Arrange — `specific` derives `base` by inserting one stage after `chunk`, `02` §3's
    # own worked example. The diff must report exactly the one addition, proving the
    # comparison is exact rather than "something differs".
    a = ResolvedPipeline(name="base", stages=(_stage("chunk"),))
    b = ResolvedPipeline(
        name="specific",
        stages=(_stage("chunk"), _stage("keywords", use="keybert", distribution="weft-kw")),
    )

    # Act
    diff = diff_resolved(a, b)

    # Assert
    assert not diff.identical
    assert [stage.id for stage in diff.added_stages] == ["keywords"]
    assert diff.removed_stages == ()
    assert diff.changed_stages == ()


def test_a_removed_stage_is_reported_as_removed_and_nothing_else() -> None:
    # Edge case — the reverse direction of the addition above.
    a = ResolvedPipeline(name="base", stages=(_stage("chunk"), _stage("embed", use="hash")))
    b = ResolvedPipeline(name="base", stages=(_stage("chunk"),))

    diff = diff_resolved(a, b)

    assert not diff.identical
    assert diff.added_stages == ()
    assert [stage.id for stage in diff.removed_stages] == ["embed"]
    assert diff.changed_stages == ()


def test_a_stage_present_on_both_sides_with_a_different_plugin_is_reported_as_changed() -> None:
    # Error-adjacent case — same id, different `use:`, which `ResolvedStage.__eq__` (a
    # frozen pydantic model) already tells apart; diff_resolved must surface exactly that
    # one stage as changed, never as one removal plus one addition.
    a = ResolvedPipeline(name="base", stages=(_stage("chunk", use="fixed-size"),))
    b = ResolvedPipeline(name="base", stages=(_stage("chunk", use="sentence"),))

    diff = diff_resolved(a, b)

    assert not diff.identical
    assert diff.added_stages == ()
    assert diff.removed_stages == ()
    assert [change.id for change in diff.changed_stages] == ["chunk"]
    assert diff.changed_stages[0].a.use == "fixed-size"
    assert diff.changed_stages[0].b.use == "sentence"


def test_a_changed_var_is_reported_and_an_unchanged_var_is_not() -> None:
    # Arrange — `base-de.yaml`'s own worked example (`02` §3 → *Language, and what a var is
    # for*): a child retargets one var, leaving another untouched.
    a = ResolvedPipeline(name="base", vars={"target_lang": "en", "stable": "x"})
    b = ResolvedPipeline(name="base-de", vars={"target_lang": "de", "stable": "x"})

    diff = diff_resolved(a, b)

    assert not diff.identical
    assert diff.var_changes == (VarChange(name="target_lang", a="en", b="de"),)
