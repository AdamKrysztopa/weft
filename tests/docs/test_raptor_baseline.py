"""Ledger task **10.0** — the baseline that has to exist before any line changes `raptor`.

`build-ledger.md` → Phase 10, task 10.0: *"a baseline exists before any line changes the
plugin: a persisted `weft eval` run, against a real embedder, comparing leaves-only retrieval
with the shipped one-level `raptor` on the corpus, stating the smallest effect it could have
detected."* Every clause of that sentence is a fact about committed files, so it is checked
here rather than asserted in prose: 10.2 and 10.3 change what the plugin builds, and a baseline
taken after them measures the repaired plugin instead of the shipped one.

**No live run, no credential, no container** — `tests/docs/test_baseline_shape.py`'s own rule
for V3's committed baseline, applied one artefact over. The six run records under
`eval/raptor-baseline/runs/` were produced by the shipped `weft eval run` binary from a
directory that is not this repository; what this file does is read them back and hold the
statement beside them to what they actually say.

**Where the two sides come from, said exactly rather than claimed.** The **verdicts** in
`eval/raptor-baseline/measurement.json` are a transcription of what `weft eval compare
--baseline` printed at the terminal, and `test_the_stated_verdicts_are_the_ones_the_records_
produce` recomputes them from the committed records through `weft_eval.falsify` — two genuinely
different sources, which disagree if the transcription is wrong or the binary and the library have
drifted apart. The **spreads, arm means and minimum detectable effect** are not: they are derived
from the same records by the same functions the assertions call, because the terminal prints its
bounds to three decimals and never prints an arm's full three-repetition spread at all. So those
assertions catch a hand-edited number, a swapped record, and a repetition added or dropped without
the statement being retaken — a staleness check, which is real and is not an independent
measurement, and `docs/internal/lessons.md` L9.28 is why that distinction is written down here
instead of being left for a reader to assume the stronger one.

**Why the minimum detectable effect is the *wider* of the two arms' own spreads.** V3 derives a
tolerance from a baseline repeating itself, and `weft_eval.falsify` judges one difference
against one arm's spread. Two arms is Weft's own extension of that and is stated rather than
borrowed: an effect smaller than *either* arm's own repetition noise is not one this instrument
can see, so the smallest detectable effect is the larger of the two widths. No paper is cited
for it, and the papers' own reported effect sizes (RAPTOR Tables 1–2: 0.33 to 4.41 points) are
carried in the file as the bar this instrument is compared against, never as a prediction.
"""

import json
from pathlib import Path
from statistics import fmean
from typing import Any, Final

import pytest

from weft_eval.falsify import BaselineSpread, baseline_spreads, judge_differences
from weft_eval.run_record import RunRecord, load_run_record
from weft_kernel.payload import Produced

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
BASELINE_DIR: Final[Path] = REPO_ROOT / "eval" / "raptor-baseline"
RUNS_DIR: Final[Path] = BASELINE_DIR / "runs"
MEASUREMENT: Final[Path] = BASELINE_DIR / "measurement.json"

#: The deterministic embedder `poe ci-checks` runs against. A baseline taken through it would
#: measure nothing — `weft_retrieve/pipelines/index-with-raptor.yaml` already records that
#: `similarity_threshold: 0.75` is a bar no `hash` vector clears — which is why 10.0 says
#: "against a real embedder" and why this name is refused rather than merely not expected.
DETERMINISTIC_EMBEDDER: Final[str] = "hash"

#: The `raptor` configuration the **baseline was taken under**, which is what these records
#: encode and therefore what this file may assert. It is no longer what the shipped document
#: writes: task 10.9 replaced `cluster_size` and `similarity_threshold` with `auto` in
#: `index-with-raptor.yaml`, retiring two numbers nothing had measured. That is exactly the move
#: this constant's own earlier comment anticipated — *"10.9 is where these numbers are allowed to
#: move"* — and the pin stays because a baseline describes the run that produced it, not the
#: tree's current defaults. A later baseline taken under `auto` will carry `auto`'s own resolved
#: values on its nodes instead, which is what `RaptorFacts` records them for.
SHIPPED_RAPTOR_CONFIG: Final[dict[str, object]] = {
    "cluster_size": 4,
    "min_cluster_size": 2,
    "similarity_threshold": 0.75,
}


@pytest.fixture(scope="module")
def measurement() -> dict[str, Any]:
    """The transcribed statement — what the terminal said, typed into a file."""
    return json.loads(MEASUREMENT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def records(measurement: dict[str, Any]) -> dict[str, tuple[RunRecord, ...]]:
    """Each arm's own repetitions, in the order the statement names them."""
    return {
        arm: tuple(load_run_record(RUNS_DIR / f"{run_id}.json") for run_id in body["runs"])
        for arm, body in measurement["arms"].items()
    }


def _stage(record: RunRecord, use: str) -> Any:
    """The one resolved stage of `record` whose plugin is `use`, or `None`."""
    for stage in record.resolved_pipeline.stages:
        if stage.use == use:
            return stage
    return None


def _spread_widths(repetitions: tuple[RunRecord, ...]) -> dict[str, float]:
    """Every metric's own interval width across `repetitions` — the quantity
    `weft eval compare --baseline` judges a difference against.
    """
    return {
        name: measured.width
        for name, measured in baseline_spreads(repetitions).items()
        if isinstance(measured, BaselineSpread)
    }


def test_the_baseline_exists_as_two_arms_of_repeated_runs(
    measurement: dict[str, Any], records: dict[str, tuple[RunRecord, ...]]
) -> None:
    # Floor. V3's own failure clause is a baseline run once, which records no interval; 10.0
    # asks for two arms, so both need one. `weft_eval.falsify.baseline_spreads` refuses fewer
    # than two repetitions outright, and a file naming one would fail below with an exception
    # rather than an assertion — so the count is checked here, where the message can say why.
    # Assert
    assert set(records) == {measurement["arms_are"]["leaves"], measurement["arms_are"]["raptor"]}
    for arm, repetitions in records.items():
        assert len(repetitions) >= 2, (
            f"arm '{arm}' carries {len(repetitions)} repetition(s). A baseline run once records "
            f"no interval and no later run can be judged against it (09 §4.3, V3)."
        )


def test_every_run_was_taken_against_a_real_embedder(
    records: dict[str, tuple[RunRecord, ...]],
) -> None:
    # 10.0's own words. `hash` vectors carry no semantic similarity by their own admission, so a
    # baseline through them measures the absence of clustering rather than the plugin.
    # Assert
    for arm, repetitions in records.items():
        for record in repetitions:
            uses = [stage.use for stage in record.resolved_pipeline.stages]
            assert DETERMINISTIC_EMBEDDER not in uses, (
                f"arm '{arm}' names '{DETERMINISTIC_EMBEDDER}' among its stages {uses}"
            )
            assert record.model_versions, (
                f"arm '{arm}' recorded no model version, so nothing says which embedder ran"
            )


def test_the_two_arms_differ_by_exactly_the_shipped_summariser(
    measurement: dict[str, Any], records: dict[str, tuple[RunRecord, ...]]
) -> None:
    # A comparison between two pipelines that differ in more than one place attributes the
    # difference to whichever change the reader had in mind. The leaves arm is the raptor arm
    # with the `summarise` stage removed and nothing else, and the summariser carries the
    # configuration `index-with-raptor.yaml` ships rather than one tuned for this measurement.
    leaves = records[measurement["arms_are"]["leaves"]][0]
    raptor = records[measurement["arms_are"]["raptor"]][0]

    # Act
    leaves_stages = [(stage.id, stage.use) for stage in leaves.resolved_pipeline.stages]
    raptor_stages = [(stage.id, stage.use) for stage in raptor.resolved_pipeline.stages]
    summariser = _stage(raptor, "raptor")

    # Assert
    assert summariser is not None, "the raptor arm resolves no stage using the 'raptor' plugin"
    assert _stage(leaves, "raptor") is None, "the leaves arm resolves a 'raptor' stage too"
    assert [pair for pair in raptor_stages if pair != (summariser.id, "raptor")] == leaves_stages
    # `ResolvedStage.config` read back from JSON is a plain mapping — there is no registry in
    # this process to validate it into the plugin's own `config_model`, and asking for one would
    # make this file need an installed `weft-openai` to read a number the record already carries.
    config = dict(summariser.config)
    for field, expected in SHIPPED_RAPTOR_CONFIG.items():
        assert config.get(field) == expected, (
            f"the baseline measured '{field}={config.get(field)}', which is not the shipped "
            f"value {expected!r} — it did not measure the plugin this project ships"
        )


def test_every_run_is_comparable_to_every_other(
    records: dict[str, tuple[RunRecord, ...]],
) -> None:
    # `weft_cli.eval_commands._incomparable_reasons`' own three facts. Two runs that differ by
    # more than their pipeline are not evidence about the pipeline, and the whole statement is a
    # difference between two of these.
    every = [record for repetitions in records.values() for record in repetitions]
    first = every[0]

    # Assert
    for record in every[1:]:
        assert record.corpus == first.corpus
        assert record.model_versions == first.model_versions
        assert record.active_distributions == first.active_distributions


def test_the_stated_spread_is_the_one_the_records_produce(
    measurement: dict[str, Any], records: dict[str, tuple[RunRecord, ...]]
) -> None:
    # The transcription against the records. `weft eval compare --baseline` printed these
    # widths; `baseline_spreads` recomputes them from the files that were committed beside it.
    # Assert
    for arm, repetitions in records.items():
        stated = measurement["arms"][arm]["spread_width"]
        assert stated == pytest.approx(_spread_widths(repetitions), abs=5e-7), (
            f"arm '{arm}''s transcribed spread is not what its own committed runs span"
        )


def test_the_stated_verdicts_are_the_ones_the_records_produce(
    measurement: dict[str, Any], records: dict[str, tuple[RunRecord, ...]]
) -> None:
    # The falsification instrument's own answer, recomputed. `compared.a`/`compared.b` name the
    # one run of each arm the statement judged; the repetitions a spread is taken over exclude
    # both, exactly as `weft_cli.eval_commands._falsify_against_baseline` excludes them.
    compared = measurement["compared"]
    a = load_run_record(RUNS_DIR / f"{compared['a']}.json")
    b = load_run_record(RUNS_DIR / f"{compared['b']}.json")

    for arm, stated in measurement["verdicts"].items():
        # Act
        repetitions = tuple(
            record
            for run_id, record in zip(measurement["arms"][arm]["runs"], records[arm], strict=True)
            if run_id not in {compared["a"], compared["b"]}
        )
        judged = judge_differences(a, b, baseline_spreads(repetitions))

        # Assert
        assert {name: judgement.verdict.value for name, judgement in judged.items()} == stated, (
            f"the verdicts transcribed against baseline '{arm}' are not the ones its own "
            f"committed repetitions produce"
        )


def test_the_stated_arm_means_are_the_ones_the_records_produce(
    measurement: dict[str, Any], records: dict[str, tuple[RunRecord, ...]]
) -> None:
    # The arm means are what the first caveat says a claim should be read from, and what
    # `what_the_baseline_says` subtracts. `weft eval compare` computes neither, so nothing else
    # in this tree would notice them going stale against the records they were taken from.
    # Assert
    for arm, repetitions in records.items():
        measured = {
            name: fmean(
                [
                    outcome.value.mean
                    for record in repetitions
                    if isinstance(outcome := record.metrics.get(name), Produced)
                ]
            )
            for name in measurement["arms"][arm]["arm_mean"]
        }
        assert measurement["arms"][arm]["arm_mean"] == pytest.approx(measured, abs=5e-7)


def test_the_smallest_detectable_effect_is_stated_and_compared_against_the_papers_bar(
    measurement: dict[str, Any], records: dict[str, tuple[RunRecord, ...]]
) -> None:
    # 10.0's last clause, and the one the Exit rests on: *"stating the smallest effect it could
    # have detected."* The number is derived from both arms' own repetitions — see the module
    # docstring — and it is stated *beside* the effect sizes the papers report, so a later
    # phase reading this file learns whether a null result meant "no effect" or "no instrument".
    bar = measurement["papers_effect_size_bar"]
    leaves = _spread_widths(records[measurement["arms_are"]["leaves"]])
    raptor = _spread_widths(records[measurement["arms_are"]["raptor"]])

    # Assert
    assert set(measurement["minimum_detectable_effect"]) == set(leaves) & set(raptor)
    for metric, stated in measurement["minimum_detectable_effect"].items():
        widest = max(leaves[metric], raptor[metric])
        assert stated["effect"] == pytest.approx(widest, abs=5e-7)
        assert stated["detects_the_papers_bar"] is (widest <= bar), (
            f"'{metric}' claims detects_the_papers_bar={stated['detects_the_papers_bar']} at a "
            f"measured width of {widest} against a bar of {bar}"
        )


# --- Re-measurements. A repair that changes what the plugin builds is measured against 10.0.

REMEASUREMENTS: Final[Path] = BASELINE_DIR / "remeasurements"


def _remeasurements() -> list[tuple[Path, dict[str, Any]]]:
    """Every committed re-measurement, as `(directory, its own statement)`."""
    return [
        (directory, json.loads((directory / "remeasurement.json").read_text(encoding="utf-8")))
        for directory in sorted(REMEASUREMENTS.glob("after-*"))
        if (directory / "remeasurement.json").exists()
    ]


def test_every_remeasurement_is_comparable_to_the_baseline_it_is_measured_against(
    records: dict[str, tuple[RunRecord, ...]],
) -> None:
    """The phase's own instruction — *"each re-measured against 10.0"* — is only meaningful if
    the two are comparable, which is `weft_cli.eval_commands._incomparable_reasons`' three facts.
    A re-measurement taken on a different corpus, a different embedder or a different installed
    set is a number about something else, and `weft eval compare` would refuse it outright.
    """
    # Arrange
    baseline = records["raptor-baseline"][0]

    # Assert
    for directory, statement in _remeasurements():
        for run_id in statement["runs"]:
            record = load_run_record(directory / f"{run_id}.json")
            assert record.corpus == baseline.corpus, f"{directory.name}: corpus differs"
            assert record.model_versions == baseline.model_versions, f"{directory.name}: models"
            assert record.active_distributions == baseline.active_distributions, (
                f"{directory.name}: the installed distribution set differs"
            )


def test_every_remeasurement_states_the_numbers_its_own_records_produce() -> None:
    """The same staleness floor the baseline itself carries, one directory over: a statement a
    reader quotes must be the one its committed runs say, or a later phase argues from a number
    nothing produced.
    """
    for directory, statement in _remeasurements():
        # Arrange
        repetitions = tuple(
            load_run_record(directory / f"{run_id}.json") for run_id in statement["runs"]
        )

        # Act
        measured = {
            name: fmean(
                [
                    outcome.value.mean
                    for record in repetitions
                    if isinstance(outcome := record.metrics.get(name), Produced)
                ]
            )
            for name in statement["arm_mean"]
        }

        # Assert
        assert statement["arm_mean"] == pytest.approx(measured, abs=5e-7), directory.name
        assert statement["spread_width"] == pytest.approx(_spread_widths(repetitions), abs=5e-7), (
            directory.name
        )


def test_a_pooled_spread_is_the_one_both_its_directories_produce() -> None:
    """A re-measurement may pool with another whose configuration is retrieval-identical, and
    the pooled width is the number a later phase will plan against.

    `10.4`'s statement does exactly that, and it is the one number in this artefact that
    contradicts `measurement.json`: six repetitions of one configuration span more than twice
    what three of them did, which puts `10.0`'s reported improvement back inside the noise. A
    figure that important is not left as prose — it is recomputed here from the runs in both
    directories, so it cannot drift from them or quietly lose one.
    """
    for directory, statement in _remeasurements():
        pooled_with = statement.get("pooled_with")
        if pooled_with is None:
            continue

        # Arrange
        sibling = REMEASUREMENTS / pooled_with
        sibling_statement = json.loads((sibling / "remeasurement.json").read_text("utf-8"))
        repetitions = tuple(
            load_run_record(directory / f"{run_id}.json") for run_id in statement["runs"]
        ) + tuple(
            load_run_record(sibling / f"{run_id}.json") for run_id in sibling_statement["runs"]
        )

        # Assert
        assert len(repetitions) > len(statement["runs"]), (
            f"{directory.name} claims to pool with '{pooled_with}' and gained no repetitions"
        )
        assert statement["pooled_spread_width"] == pytest.approx(
            _spread_widths(repetitions), abs=5e-7
        ), f"{directory.name}'s pooled width is not what its two directories' runs span"


# --- Phase 10's Exit measurement — ledger task 10.13.

EXIT: Final[Path] = BASELINE_DIR / "exit"


@pytest.fixture(scope="module")
def exit_statement() -> dict[str, Any]:
    return json.loads((EXIT / "exit-measurement.json").read_text(encoding="utf-8"))


def test_the_exit_measured_three_arms_on_the_documents_this_project_ships(
    exit_statement: dict[str, Any],
) -> None:
    """`01` → Phase 10 → *Exit* asks for leaves-only, the shipped one-level tree and the
    multi-level tree — and the arms have to be the **shipped** documents, or the measurement is
    about something nobody can run. Each extends one of them and replaces only the extractor and
    the embedder.
    """
    # Arrange
    arms = exit_statement["arms"]
    extends = exit_statement["arms_extend"]

    # Assert
    assert set(exit_statement["arms_are"].values()) == set(arms)
    assert extends["exit-one"] == "index-with-raptor"
    assert extends["exit-deep"] == "index-with-deep-raptor"
    for name, parent in extends.items():
        resolved = {stage.use for stage in _arm_records(arms, name)[0].resolved_pipeline.stages}
        assert "openai-embeddings" in resolved, f"{name} did not run against a real embedder"
        assert "hash" not in resolved, f"{name} ran against `hash`, so {parent} measured nothing"


def _arm_records(arms: dict[str, Any], name: str) -> tuple[RunRecord, ...]:
    return tuple(load_run_record(EXIT / f"{run_id}.json") for run_id in arms[name]["runs"])


def test_the_multi_level_arm_actually_built_a_second_level(
    exit_statement: dict[str, Any],
) -> None:
    """The Exit's first clause is a tree of **at least two levels**, so the arm that claims one
    has to have built one in every run — a measurement of a deep rung that silently built one
    level is a measurement of the one-level rung under another name.
    """
    # Arrange
    deep = exit_statement["arms"]["exit-deep"]

    # Assert
    assert all(count >= 1 for count in deep["level_two"]), (
        f"a run of the multi-level arm produced no level-2 node: {deep['level_two']}"
    )
    assert all(count >= 1 for count in deep["level_one"])
    assert all(count == 0 for count in exit_statement["arms"]["exit-leaves"]["level_one"]), (
        "the leaves arm produced summaries, so it is not a leaves-only control"
    )


def test_every_exit_arm_was_repeated_enough_to_estimate_its_own_spread(
    exit_statement: dict[str, Any],
) -> None:
    """`L10.17`: a width over three repetitions is an estimate with more spread than the thing it
    estimates, and 10.13's own line requires more than three or a statement that it could not
    separate its effect. The arms where a model writes the content are repeated six times.
    """
    # Assert
    for name in ("exit-one", "exit-deep"):
        runs = exit_statement["arms"][name]["runs"]
        assert len(runs) > 3, (
            f"{name} was repeated {len(runs)} times, which L10.17 measured as too few"
        )
        assert len(set(runs)) == len(runs), f"{name} lists a run id twice"


def test_the_exit_verdicts_are_the_ones_its_own_records_produce(
    exit_statement: dict[str, Any],
) -> None:
    """The statement against the runs. Every arm mean, every spread, the minimum detectable
    effect and every verdict recomputed — because this is the artefact `01`'s Exit criterion is
    discharged by, and a number in it that its own records do not produce would discharge nothing.
    """
    # Arrange
    arms = exit_statement["arms"]
    measured = {name: _spread_widths(_arm_records(arms, name)) for name in arms}
    metrics = sorted(measured["exit-leaves"])

    # Assert — the per-arm figures first.
    for name, body in arms.items():
        records = _arm_records(arms, name)
        assert body["spread_width"] == pytest.approx(measured[name], abs=5e-7), name
        means = {
            metric: fmean(
                [
                    outcome.value.mean
                    for record in records
                    if isinstance(outcome := record.metrics.get(metric), Produced)
                ]
            )
            for metric in body["arm_mean"]
        }
        assert body["arm_mean"] == pytest.approx(means, abs=5e-7), name

    # The minimum detectable effect, and then every verdict that rests on it.
    mde = {
        metric: max(measured["exit-one"][metric], measured["exit-deep"][metric])
        for metric in metrics
    }
    assert exit_statement["minimum_detectable_effect"] == pytest.approx(mde, abs=5e-7)

    pairs = {
        "one_level_vs_leaves": ("exit-leaves", "exit-one"),
        "multi_level_vs_leaves": ("exit-leaves", "exit-deep"),
        "multi_level_vs_one_level": ("exit-one", "exit-deep"),
    }
    for name, (left, right) in pairs.items():
        for metric in metrics:
            difference = arms[right]["arm_mean"][metric] - arms[left]["arm_mean"][metric]
            assert exit_statement["comparisons"][name][metric] == pytest.approx(
                difference, abs=5e-7
            ), f"{name}/{metric}"
            expected = "outside" if abs(difference) > mde[metric] else "inside"
            assert exit_statement["verdicts"][name][metric] == expected, (
                f"{name}/{metric}: stated {exit_statement['verdicts'][name][metric]!r} for a "
                f"difference of {difference} against a minimum detectable effect of {mde[metric]}"
            )
