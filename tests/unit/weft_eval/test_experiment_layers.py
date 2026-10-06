"""`weft_eval.experiment` — ledger task **44.55a**: an arm may name the layers it reads.

A RAPTOR rung retrieves from a layer `weft index --layers` builds after the base run, so an arm
comparing it names that layer. Every arm over one pipeline and corpus shares one target (ledger task
**20.11**), and a layer once built stays there for every arm after it: `vector-top-k` does not
filter derived nodes out. So an arm naming fewer layers than an earlier arm over the same pipeline
and corpus would read summaries it never named, and the document is refused at load, before
anything is indexed or paid for.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from weft_eval.experiment import (
    EXPERIMENT_SCHEMA_VERSION,
    ExperimentDocumentError,
    load_experiment,
)

_HEAD = f"""[experiment]
schema = {EXPERIMENT_SCHEMA_VERSION}
name = "layered"
questions = "questions.toml"
corpus = "corpus"
repeats = 2
top_k = 5
metrics = ["precision@5"]
minimum_detectable_effect = 0.05
"""


def _arm(name: str, extra: str = "", *, pipeline: str = "index-with-graph") -> str:
    return f'\n[[arm]]\nname = "{name}"\npipeline = "{pipeline}"\n{extra}'


def _write(directory: Path, arms: str) -> Path:
    path = directory / "experiment.toml"
    path.write_text(_HEAD + arms, encoding="utf-8")
    return path


def test_an_arm_may_name_layers_and_an_arm_naming_none_reads_none(tmp_path: Path) -> None:
    # Arrange
    path = _write(
        tmp_path,
        _arm("dense")
        + _arm("raptor", 'layers = ["enrich-with-raptor-corpus"]\nquery_pipeline = "r"\n'),
    )

    # Act
    experiment = load_experiment(path)

    # Assert
    dense, raptor = experiment.arms
    assert dense.layers == ()
    assert raptor.layers == ("enrich-with-raptor-corpus",)


def test_an_arm_naming_fewer_layers_than_an_earlier_arm_is_refused_naming_both(
    tmp_path: Path,
) -> None:
    """A layer built for one arm stays in the shared target, so a later arm would read it."""
    # Arrange
    path = _write(
        tmp_path,
        _arm("raptor", 'layers = ["enrich-with-raptor-corpus"]\n') + _arm("dense"),
    )

    # Act
    with pytest.raises(ExperimentDocumentError) as caught:
        load_experiment(path)

    # Assert
    message = str(caught.value)
    assert "'dense'" in message
    assert "'raptor'" in message
    assert "enrich-with-raptor-corpus" in message
    assert "share one target" in message


def test_an_arm_over_another_pipeline_may_name_fewer_layers(tmp_path: Path) -> None:
    """A layer is built into its own pipeline's target, which an arm over another never reads."""
    # Arrange
    path = _write(
        tmp_path,
        _arm("raptor", 'layers = ["enrich-with-raptor-corpus"]\n')
        + _arm("dense", pipeline="index-text"),
    )

    # Act
    experiment = load_experiment(path)

    # Assert
    assert [arm.layers for arm in experiment.arms] == [("enrich-with-raptor-corpus",), ()]


def test_layers_that_only_grow_in_document_order_are_accepted(tmp_path: Path) -> None:
    # Arrange
    path = _write(
        tmp_path,
        _arm("dense")
        + _arm("one", 'layers = ["enrich-a"]\n')
        + _arm("both", 'layers = ["enrich-b", "enrich-a"]\n')
        + _arm("both-again", 'layers = ["enrich-a", "enrich-b"]\n'),
    )

    # Act
    experiment = load_experiment(path)

    # Assert
    assert [set(arm.layers) for arm in experiment.arms] == [
        set(),
        {"enrich-a"},
        {"enrich-a", "enrich-b"},
        {"enrich-a", "enrich-b"},
    ]


def test_an_arm_replaying_a_pool_may_not_name_layers(tmp_path: Path) -> None:
    """A replay reads a captured pool and no index, so a layer it names would never be read."""
    # Arrange
    path = _write(
        tmp_path,
        _arm("dense")
        + _arm("replay", 'pool = "pool.json"\nquery_pipeline = "r"\nlayers = ["enrich-a"]\n'),
    )

    # Act
    with pytest.raises(ExperimentDocumentError) as caught:
        load_experiment(path)

    # Assert
    message = str(caught.value)
    assert "'replay'" in message
    assert "pool" in message
    assert "layers" in message


def test_an_arm_naming_one_layer_twice_is_refused_naming_it(tmp_path: Path) -> None:
    # Arrange
    path = _write(tmp_path, _arm("dense") + _arm("raptor", 'layers = ["enrich-a", "enrich-a"]\n'))

    # Act
    with pytest.raises(ExperimentDocumentError) as caught:
        load_experiment(path)

    # Assert
    assert "enrich-a" in str(caught.value)
    assert "'raptor'" in str(caught.value)


@pytest.mark.parametrize("written", ['"enrich-with-raptor-corpus"', "3", "true"])
def test_layers_written_as_anything_but_a_list_is_refused_saying_so(
    tmp_path: Path, written: str
) -> None:
    # Arrange — R44.20: a bare string was split into characters and refused as "names layer 'e'
    # more than once", which blamed the layer rather than the spelling.
    path = _write(tmp_path, _arm("dense") + _arm("raptor", f"layers = {written}\n"))

    # Act / Assert
    with pytest.raises(ExperimentDocumentError, match=r"layers must be a list.*\[\"raptor\"\]"):
        load_experiment(path)
