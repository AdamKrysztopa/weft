"""A resolved pipeline has a stable identity — ledger task `9.17`'s half in the kernel.

`9.17` requires that re-indexing an unchanged file *with a different parser, or the same parser and
a different model,* is **visible** rather than silent. Visible against what? `SourceRecord.pipeline`
holds the document's *name*, and a name does not move when the plugin behind a stage does — an
operator who swaps `pdf-text` for `pdf-layout` inside `index-text`, or changes an embedder's
`with: model:`, still writes `pipeline="index-text"` and nothing anywhere records that the corpus
was built two different ways.

So the comparable thing is a digest over what actually ran. `ResolvedPipeline` is already the
fully-explicit form — `02` §3: resolution "did the hard part" — and `weft_cli.pipeline_diff` already
compares two of them field by field with `==`. This is that comparison reduced to one string a
`SourceRecord` can carry.

**What must move it, and what must not.** A different plugin at a stage, a different `with:` value,
a stage added, removed or reordered: all of those change what the corpus is and must change the
identity. The pipeline's *name* must not — renaming a document does not re-parse a corpus, and an
identity that moved on a rename would report a reparse that did not happen, which is worse than
silence because someone would act on it.
"""

import pytest
from pydantic import BaseModel

from weft_kernel.resolution import ResolvedPipeline, ResolvedStage, pipeline_identity


def _stage(stage_id: str, use: str, config: dict[str, object] | None = None) -> ResolvedStage:
    return ResolvedStage(
        id=stage_id,
        contract="Extractor",
        contract_version="1.0.0",
        use=use,
        config=config or {},
        distribution="weft-rag",
        provenance="base",
    )


def _pipeline(name: str = "index-text", *stages: ResolvedStage) -> ResolvedPipeline:
    return ResolvedPipeline(name=name, stages=stages or (_stage("extract", "text"),))


def test_the_same_pipeline_has_the_same_identity_every_time() -> None:
    """Deterministic, or a re-index would report a change on every run."""
    # Act / Assert
    assert pipeline_identity(_pipeline()) == pipeline_identity(_pipeline())


def test_a_different_plugin_at_a_stage_changes_the_identity() -> None:
    """9.17's own words: *a different parser*. This is the case the task exists for."""
    # Act
    text = pipeline_identity(_pipeline("p", _stage("extract", "text")))
    layout = pipeline_identity(_pipeline("p", _stage("extract", "pdf-layout")))

    # Assert
    assert text != layout


def test_a_different_config_value_changes_the_identity() -> None:
    """9.17's other half: *the same parser and a different model*. A model is a `with:` value."""
    # Act
    small = pipeline_identity(_pipeline("p", _stage("embed", "openai", {"model": "small"})))
    large = pipeline_identity(_pipeline("p", _stage("embed", "openai", {"model": "large"})))

    # Assert
    assert small != large


def test_adding_a_stage_changes_the_identity() -> None:
    # Act
    one = pipeline_identity(_pipeline("p", _stage("extract", "text")))
    two = pipeline_identity(
        _pipeline("p", _stage("extract", "text"), _stage("clean", "whitespace"))
    )

    # Assert
    assert one != two


def test_reordering_two_stages_changes_the_identity() -> None:
    """Order is what a pipeline *is*; two orderings of the same stages are two corpora."""
    # Arrange
    first, second = _stage("a", "text"), _stage("b", "whitespace")

    # Act / Assert
    assert pipeline_identity(_pipeline("p", first, second)) != pipeline_identity(
        _pipeline("p", second, first)
    )


def test_renaming_the_pipeline_does_not_change_the_identity() -> None:
    """The one thing that must *not* move it — see the module docstring.

    A rename that reported a reparse would be a false positive an operator acts on, and a false
    positive in a change detector is worse than no detector: it teaches people to ignore it.
    """
    # Act / Assert
    assert pipeline_identity(_pipeline("index-text")) == pipeline_identity(_pipeline("renamed"))


def test_the_identity_is_a_short_stable_string() -> None:
    """The pipeline identity is a digest a caller can persist and print.

    It is persisted in a `SourceRecord` column and printed to an operator, so it is neither a
    Python object nor a paragraph. Asserted as the facts a caller depends on rather than as a
    length — a digest's width is a choice, its shape is not.
    """
    # Act
    identity = pipeline_identity(_pipeline())

    # Assert
    assert isinstance(identity, str)
    assert identity
    assert identity.strip() == identity
    assert "\n" not in identity


def test_two_pipelines_that_differ_only_in_an_unapplied_operator_are_the_same_corpus() -> None:
    """`unapplied_operators` and `unplaced_contributions` record what resolution *could not* do.

    They are diagnostics about the document, not part of what ran, so a corpus built with one is
    the same corpus. Including them would make the identity move on a fact that changed no bytes.
    """
    # Arrange
    plain = _pipeline()
    noisy = plain.model_copy(update={"unapplied_operators": ("insert:missing",)})

    # Act / Assert
    assert pipeline_identity(plain) == pipeline_identity(noisy)


def test_a_pipeline_with_no_stages_still_has_an_identity() -> None:
    """The edge case: resolution can produce one, so this must not raise."""
    # Act / Assert
    assert pipeline_identity(ResolvedPipeline(name="empty"))


@pytest.mark.parametrize("field", ["contract", "contract_version", "distribution"])
def test_a_stages_contract_facts_are_part_of_the_identity(field: str) -> None:
    """Guards `pipeline_identity` against missing a contract change behind the same plugin name.

    A plugin answering a different contract, or a contract at a different version, is a
    different pipeline even where the plugin name is unchanged — G9's whole point about a
    published version meaning something.
    """
    # Arrange
    base = _stage("extract", "text")
    changed = base.model_copy(update={field: "changed"})

    # Act / Assert
    assert pipeline_identity(_pipeline("p", base)) != pipeline_identity(_pipeline("p", changed))


# --- Repair R34.1: only a contract's major moves the identity ------------------------------------


@pytest.mark.parametrize("later", ["1.1.0", "1.0.1", "1.9.3"])
def test_a_contract_minor_or_patch_does_not_move_the_identity(later: str) -> None:
    """A contract's minor version says nothing about how a corpus was built.

    A minor is additive under G9 and cannot change what an existing plugin does, so it says
    nothing about how a corpus was built. Hashing it re-parsed every corpus on every store-contract
    bump — found running a 2.8.0-written store under 2.9.0 (ledger `34.2`).
    """
    # Arrange
    base = _stage("extract", "text")
    later_stage = base.model_copy(update={"contract_version": later})

    # Act / Assert
    assert later_stage.contract_version != base.contract_version
    assert pipeline_identity(_pipeline("p", base)) == pipeline_identity(_pipeline("p", later_stage))


def test_a_contract_major_still_moves_the_identity() -> None:
    # Arrange
    base = _stage("extract", "text")
    major = base.model_copy(update={"contract_version": "2.0.0"})

    # Act / Assert
    assert pipeline_identity(_pipeline("p", base)) != pipeline_identity(_pipeline("p", major))


# --- Repair R32.0: a validated `config_model` is hashed by its fields, not by its printed text --


class _ChunkConfig(BaseModel):
    size: int = 512
    overlap: int = 50


class _ChunkConfigReordered(BaseModel):
    overlap: int = 50
    size: int = 512


class _ChunkConfigPrintedDifferently(_ChunkConfig):
    def __str__(self) -> str:
        return f"<chunk config {self.size}/{self.overlap}>"


def _chunk_stage(config: object) -> ResolvedStage:
    return ResolvedStage(
        id="chunk",
        contract="Chunker",
        contract_version="1.0.0",
        use="fixed-size",
        config=config,
        distribution="weft-rag",
        provenance="base",
    )


def test_a_config_model_hashes_as_its_fields_with_their_keys_sorted() -> None:
    """`pipeline_identity`'s docstring: *"`config` with its keys sorted"*.

    `_ChunkConfig` declares `size` before `overlap`, so a digest following declaration order and one
    following sorted keys disagree — the mapping written in sorted order is what the docstring
    promises.
    """
    # Arrange
    as_model = _pipeline("p", _chunk_stage(_ChunkConfig()))
    as_fields = _pipeline("p", _chunk_stage({"overlap": 50, "size": 512}))

    # Act / Assert
    assert pipeline_identity(as_model) == pipeline_identity(as_fields)


def test_reordering_a_config_models_fields_does_not_move_the_identity() -> None:
    """Nothing a stage runs changed, so no corpus may be re-derived."""
    # Act / Assert
    assert pipeline_identity(_pipeline("p", _chunk_stage(_ChunkConfig()))) == pipeline_identity(
        _pipeline("p", _chunk_stage(_ChunkConfigReordered()))
    )


def test_how_a_config_model_prints_itself_does_not_move_the_identity() -> None:
    """A pydantic release changing `__str__` is the other trigger the repair names."""
    # Act / Assert
    assert pipeline_identity(_pipeline("p", _chunk_stage(_ChunkConfig()))) == pipeline_identity(
        _pipeline("p", _chunk_stage(_ChunkConfigPrintedDifferently()))
    )


def test_a_different_value_in_a_config_model_still_moves_the_identity() -> None:
    """Hashing by fields must not collapse every model to one digest."""
    # Act / Assert
    assert pipeline_identity(_pipeline("p", _chunk_stage(_ChunkConfig()))) != pipeline_identity(
        _pipeline("p", _chunk_stage(_ChunkConfig(size=1024)))
    )
