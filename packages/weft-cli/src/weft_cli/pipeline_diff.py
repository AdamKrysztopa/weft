"""`weft pipeline diff a b` — an exact comparison, because resolution is fully explicit.

Task **3.7**. `docs/03-cli.md` → *Command surface*: "renders the difference between two
*resolved* pipelines. Because resolution produces a fully-explicit form, this is an exact
comparison rather than a guess, and it is what makes derived pipelines reviewable." The
word *exact* is the whole reason this module exists rather than a one-line call to
`difflib` over two rendered strings: a text diff is a comparison of *two renderers'
opinions* — it agrees or disagrees depending on field order, whitespace, how a renderer
chose to print a `Mapping`, none of which is a fact about the pipelines themselves. `02` §3
says resolution already did the hard part — "every stage, plugin, version and configuration
value named, with no inheritance left to interpret" — so a diff only has to compare two
already-fully-explicit `weft_kernel.resolution.ResolvedPipeline` **values**, field by field,
with `==`. That is what `diff_resolved` below does, and it is what makes the exactness claim
provable rather than asserted: `tests/unit/weft_cli/test_pipeline_diff.py` builds two
`ResolvedPipeline`s directly (no YAML, no registry) with one deliberate, small change and
proves this module reports exactly that change and nothing else, and a second test resolves
one pipeline twice and proves `diff_resolved` reports `identical=True` — repeatable, not
merely plausible-looking.

**Stages are matched by id, never by position.** Two pipelines can insert or remove stages
anywhere in the list — comparing `a.stages[i]` against `b.stages[i]` positionally would
report a shift as N unrelated changes rather than one addition. Matching by `ResolvedStage.
id` is also what `weft_kernel.resolution`'s own model already keys everything else by (`02`
§3 → *Derivation*: "every stage in the resolved form records which pipeline or pack put it
there").

**A changed stage is reported as a whole, not field by field.** `ResolvedStage` is frozen
and comparable by `==` — the same property that makes `ResolvedPipeline` itself comparable
across two `resolve()` calls (see that module's own docstring) — so "did this stage change
at all" is one equality check, and a renderer that wants the finer detail already has both
full `ResolvedStage` values to inspect. Diffing field-by-field inside a stage would be a
second, narrower notion of "changed" this module does not need for the property task 3.7
asks it to prove.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from weft_kernel.resolution import ResolvedPipeline, ResolvedStage


class StageChange(BaseModel):
    """One stage id present in both resolved pipelines, whose `ResolvedStage` differs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    a: ResolvedStage
    b: ResolvedStage


class VarChange(BaseModel):
    """One var name whose final, resolved value differs between the two pipelines.

    `a`/`b` are `str | None` rather than `Scalar | None` (`weft_kernel.pipeline.Scalar`,
    `str | int | float | bool`) purely for this model's own render-ability — `weft_cli.
    render` prints a var's value as text regardless of its original scalar type, and
    carrying the narrower, already-stringified form here keeps that renderer from needing
    to know the union at all. `None` means the var is undefined on that side — a var one
    pipeline's chain defines and the other's does not, which `resolve()` itself would only
    ever allow if the var goes unreferenced.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    a: str | None
    b: str | None


class PipelineDiff(BaseModel):
    """The exact difference between two resolved pipelines — `diff_resolved`'s whole answer.

    `identical` is true only when every field below is empty and both `unapplied_operators`/
    `unplaced_contributions` also matched — the single boolean a renderer or a script can
    check first, backed by the same structural comparison that would have caught anything
    it might disagree with.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    a_name: str
    b_name: str
    identical: bool
    added_stages: tuple[ResolvedStage, ...]
    removed_stages: tuple[ResolvedStage, ...]
    changed_stages: tuple[StageChange, ...]
    var_changes: tuple[VarChange, ...]
    unapplied_operators_changed: bool
    unplaced_contributions_changed: bool


def diff_resolved(a: ResolvedPipeline, b: ResolvedPipeline) -> PipelineDiff:
    """The exact, structural difference between `a` and `b` — see the module docstring.

    Never touches a rendered string, a YAML document, or the registry: everything this
    function needs is already sitting in the two `ResolvedPipeline` values it is handed,
    which is the proof that the comparison is exact rather than a guess about how two
    renderers happened to print the same fact.
    """
    a_by_id = {stage.id: stage for stage in a.stages}
    b_by_id = {stage.id: stage for stage in b.stages}

    added = tuple(b_by_id[stage_id] for stage_id in b_by_id if stage_id not in a_by_id)
    removed = tuple(a_by_id[stage_id] for stage_id in a_by_id if stage_id not in b_by_id)
    changed = tuple(
        StageChange(id=stage_id, a=a_by_id[stage_id], b=b_by_id[stage_id])
        for stage_id in sorted(set(a_by_id) & set(b_by_id))
        if a_by_id[stage_id] != b_by_id[stage_id]
    )

    var_names = sorted(set(a.vars) | set(b.vars))
    var_changes = tuple(
        VarChange(
            name=name,
            a=None if name not in a.vars else str(a.vars[name]),
            b=None if name not in b.vars else str(b.vars[name]),
        )
        for name in var_names
        if a.vars.get(name) != b.vars.get(name)
    )

    operators_changed = a.unapplied_operators != b.unapplied_operators
    contributions_changed = a.unplaced_contributions != b.unplaced_contributions

    identical = (
        not added
        and not removed
        and not changed
        and not var_changes
        and not operators_changed
        and not contributions_changed
    )

    return PipelineDiff(
        a_name=a.name,
        b_name=b.name,
        identical=identical,
        added_stages=added,
        removed_stages=removed,
        changed_stages=changed,
        var_changes=var_changes,
        unapplied_operators_changed=operators_changed,
        unplaced_contributions_changed=contributions_changed,
    )


__all__ = ["PipelineDiff", "StageChange", "VarChange", "diff_resolved"]
