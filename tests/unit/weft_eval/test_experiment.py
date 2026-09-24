"""`weft_eval.experiment` — ledger task **38.0**: an experiment is a document.

Every experiment in this tree so far has been a script with its own record shape. The document
states what a script leaves implicit — the arms, the question set, the repetitions, the metrics
read, and the minimum detectable effect **before** any run — so the same file can be run by
`weft eval experiment` and read back by whatever builds its table. A file on disk is data at rest,
so it carries a version marker from its first release.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from weft_eval.experiment import (
    EXPERIMENT_SCHEMA_VERSION,
    ExperimentDocumentError,
    ExperimentSchemaError,
    load_experiment,
)
from weft_kernel.errors import WeftError

_DOCUMENT = """[experiment]
schema = {schema}
name = "dense-against-rung"
questions = "questions"
corpus = "corpus"
repeats = 3
top_k = 5
metrics = ["precision@5", "recall@5"]
minimum_detectable_effect = 0.05

[[arm]]
name = "dense"
pipeline = "index-text"

[[arm]]
name = "rung"
pipeline = "index-text"
query_pipeline = "hybrid-then-generate"
"""


def _write(directory: Path, body: str, *, name: str = "experiment.toml") -> Path:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


def test_a_document_states_its_arms_repetitions_metrics_and_effect_before_any_run(
    tmp_path: Path,
) -> None:
    # Arrange
    path = _write(tmp_path, _DOCUMENT.format(schema=EXPERIMENT_SCHEMA_VERSION))

    # Act
    experiment = load_experiment(path)

    # Assert
    assert experiment.name == "dense-against-rung"
    assert experiment.repeats == 3
    assert experiment.top_k == 5
    assert set(experiment.metrics) == {"precision@5", "recall@5"}
    assert experiment.minimum_detectable_effect == 0.05
    assert [arm.name for arm in experiment.arms] == ["dense", "rung"]
    assert experiment.arms[0].query_pipeline is None
    assert experiment.arms[1].query_pipeline == "hybrid-then-generate"
    assert experiment.manifest is None


def test_paths_resolve_against_the_documents_own_directory_not_the_callers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The file is committed and run from anywhere, the way `corpus/manifest.toml`'s paths are."""
    # Arrange
    home = tmp_path / "eval" / "experiments"
    home.mkdir(parents=True)
    body = _DOCUMENT.format(schema=EXPERIMENT_SCHEMA_VERSION).replace(
        'corpus = "corpus"', 'corpus = "../../corpus"\nmanifest = "../../corpus/manifest.toml"'
    )
    _write(home, body)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    # Act
    experiment = load_experiment(Path("..") / "eval" / "experiments" / "experiment.toml")

    # Assert
    assert experiment.corpus == (tmp_path / "corpus").resolve()
    assert experiment.questions == (home / "questions").resolve()
    assert experiment.manifest == (tmp_path / "corpus" / "manifest.toml").resolve()


def test_an_arm_may_name_its_own_corpus_and_questions_and_otherwise_inherits_them(
    tmp_path: Path,
) -> None:
    # Arrange
    body = _DOCUMENT.format(schema=EXPERIMENT_SCHEMA_VERSION) + (
        '\n[[arm]]\nname = "elsewhere"\npipeline = "index-text"\ncorpus = "other"\n'
        'questions = "other.toml"\n'
    )
    path = _write(tmp_path, body)

    # Act
    experiment = load_experiment(path)

    # Assert
    dense, _, elsewhere = experiment.arms
    assert experiment.corpus_for(dense) == experiment.corpus
    assert experiment.questions_for(dense) == experiment.questions
    assert experiment.corpus_for(elsewhere) == (tmp_path / "other").resolve()
    assert experiment.questions_for(elsewhere) == (tmp_path / "other.toml").resolve()


def test_the_digest_is_over_the_documents_bytes(tmp_path: Path) -> None:
    """A committed experiment file digests the same on every checkout, whatever its path.

    Not over the resolved model: a resolved path names this machine, and the same committed
    file must digest the same wherever it is checked out.
    """
    # Arrange
    body = _DOCUMENT.format(schema=EXPERIMENT_SCHEMA_VERSION)
    here = _write(tmp_path, body)
    there_dir = tmp_path / "a" / "b"
    there_dir.mkdir(parents=True)
    there = _write(there_dir, body)
    edited = _write(tmp_path, body.replace("0.05", "0.03"), name="edited.toml")

    # Act
    digests = [load_experiment(path).digest for path in (here, there, edited)]

    # Assert
    assert digests[0] == hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert digests[0] == digests[1]
    assert digests[0] != digests[2]


@pytest.mark.parametrize(
    ("edit", "fragment"),
    [
        (("repeats = 3", "repeats = 1"), "repeats"),
        (
            ("minimum_detectable_effect = 0.05", "minimum_detectable_effect = 0.0"),
            "minimum_detectable_effect",
        ),
        (("minimum_detectable_effect = 0.05\n", ""), "minimum_detectable_effect"),
        (('metrics = ["precision@5", "recall@5"]', "metrics = []"), "metrics"),
        (('name = "rung"', 'name = "dense"'), "dense"),
        (("top_k = 5", "top_k = 5\ntemperature = 0.2"), "temperature"),
        (("top_k = 5", "top_k = []"), "top_k"),
        (("top_k = 5", "top_k = [0, 5]"), "top_k"),
    ],
    ids=[
        "one-repetition",
        "a-zero-effect",
        "no-effect-stated",
        "no-metric",
        "two-arms-one-name",
        "an-unknown-key",
        "no-cutoff",
        "a-zero-cutoff",
    ],
)
def test_a_document_that_cannot_be_run_as_stated_is_refused_naming_file_and_field(
    tmp_path: Path, edit: tuple[str, str], fragment: str
) -> None:
    # Arrange
    body = _DOCUMENT.format(schema=EXPERIMENT_SCHEMA_VERSION).replace(*edit)
    path = _write(tmp_path, body)

    # Act
    with pytest.raises(ExperimentDocumentError) as caught:
        load_experiment(path)

    # Assert
    assert isinstance(caught.value, WeftError)
    assert "experiment.toml" in str(caught.value)
    assert fragment in str(caught.value)


def test_a_document_with_one_arm_is_refused_because_there_is_nothing_to_compare(
    tmp_path: Path,
) -> None:
    # Arrange
    body = _DOCUMENT.format(schema=EXPERIMENT_SCHEMA_VERSION)
    body = body[: body.index('[[arm]]\nname = "rung"')]
    path = _write(tmp_path, body)

    # Act
    with pytest.raises(ExperimentDocumentError) as caught:
        load_experiment(path)

    # Assert
    assert "arm" in str(caught.value)


def test_a_document_naming_no_schema_is_refused(tmp_path: Path) -> None:
    # Arrange
    body = _DOCUMENT.format(schema=EXPERIMENT_SCHEMA_VERSION).replace(
        f"schema = {EXPERIMENT_SCHEMA_VERSION}\n", ""
    )
    path = _write(tmp_path, body)

    # Act
    with pytest.raises(ExperimentDocumentError) as caught:
        load_experiment(path)

    # Assert
    assert "schema" in str(caught.value)


def test_a_document_written_by_a_newer_schema_is_refused_naming_both_versions(
    tmp_path: Path,
) -> None:
    # Arrange
    newer = EXPERIMENT_SCHEMA_VERSION + 1
    path = _write(tmp_path, _DOCUMENT.format(schema=newer))

    # Act
    with pytest.raises(ExperimentSchemaError) as caught:
        load_experiment(path)

    # Assert
    message = str(caught.value)
    assert isinstance(caught.value, ExperimentDocumentError)
    assert str(newer) in message
    assert str(EXPERIMENT_SCHEMA_VERSION) in message
    assert "upgrade weft-rag" in message


def test_a_missing_document_is_refused_naming_its_path(tmp_path: Path) -> None:
    # Act
    with pytest.raises(ExperimentDocumentError) as caught:
        load_experiment(tmp_path / "absent.toml")

    # Assert
    assert "absent.toml" in str(caught.value)


# --- Repair R38.2.


def test_a_document_may_bound_the_index_batch_and_otherwise_does_not(tmp_path: Path) -> None:
    # Arrange
    body = _DOCUMENT.format(schema=EXPERIMENT_SCHEMA_VERSION)
    bounded = _write(tmp_path, body.replace("top_k = 5", "top_k = 5\nindex_batch_size = 50"))
    unbounded = _write(tmp_path, body, name="unbounded.toml")

    # Act / Assert
    assert load_experiment(bounded).index_batch_size == 50
    assert load_experiment(unbounded).index_batch_size is None


@pytest.mark.parametrize("schema", ["true", "0"], ids=["a-boolean", "zero"])
def test_a_schema_no_release_wrote_is_refused_without_advice_to_upgrade(
    tmp_path: Path, schema: str
) -> None:
    # Arrange
    body = _DOCUMENT.format(schema=EXPERIMENT_SCHEMA_VERSION).replace(
        f"schema = {EXPERIMENT_SCHEMA_VERSION}", f"schema = {schema}"
    )
    path = _write(tmp_path, body)

    # Act
    with pytest.raises(ExperimentDocumentError) as caught:
        load_experiment(path)

    # Assert
    assert not isinstance(caught.value, ExperimentSchemaError)
    assert "schema" in str(caught.value)
    assert "upgrade" not in str(caught.value)


# --- Task 38.13 — an arm whose results cannot vary is not repeated.


def test_an_arm_may_declare_its_own_repetitions_and_otherwise_inherits_the_documents(
    tmp_path: Path,
) -> None:
    """An arm with no model call runs once; an arm reaching a model keeps its `repeats`.

    `38.5`'s repetitions 2–3 were 65% of its query time and identical to repetition 1: retrieval
    with no model call cannot vary, so its author runs it once. An arm reaching a model keeps the
    document's `repeats`.
    """
    # Arrange
    body = _DOCUMENT.format(schema=EXPERIMENT_SCHEMA_VERSION).replace(
        'name = "dense"\npipeline = "index-text"\n',
        'name = "dense"\npipeline = "index-text"\nrepeats = 1\n',
    )
    path = _write(tmp_path, body)

    # Act
    experiment = load_experiment(path)

    # Assert
    dense, rung = experiment.arms
    assert experiment.repeats_for(dense) == 1
    assert experiment.repeats_for(rung) == 3


def test_an_arm_declaring_no_repetitions_at_all_is_refused_naming_the_field(tmp_path: Path) -> None:
    # Arrange
    body = _DOCUMENT.format(schema=EXPERIMENT_SCHEMA_VERSION).replace(
        'name = "dense"\npipeline = "index-text"\n',
        'name = "dense"\npipeline = "index-text"\nrepeats = 0\n',
    )
    path = _write(tmp_path, body)

    # Act
    with pytest.raises(ExperimentDocumentError) as caught:
        load_experiment(path)

    # Assert
    assert "repeats" in str(caught.value)


# --- Task 40.1 — one ranking, every declared cutoff.


def test_a_document_may_declare_several_cutoffs_and_the_ranking_is_read_to_the_largest(
    tmp_path: Path,
) -> None:
    # Arrange
    body = _DOCUMENT.format(schema=EXPERIMENT_SCHEMA_VERSION).replace(
        "top_k = 5", "top_k = [10, 1, 5]"
    )

    # Act
    experiment = load_experiment(_write(tmp_path, body))

    # Assert
    assert experiment.cutoffs == (1, 5, 10)
    assert experiment.top_k == 10


def test_a_bare_top_k_is_a_set_of_one_cutoff(tmp_path: Path) -> None:
    # Act
    experiment = load_experiment(
        _write(tmp_path, _DOCUMENT.format(schema=EXPERIMENT_SCHEMA_VERSION))
    )

    # Assert
    assert (experiment.cutoffs, experiment.top_k) == ((5,), 5)
